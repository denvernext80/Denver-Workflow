#!/usr/bin/env python3
"""dw-migrate-vault — 1.x vault 콘텐츠를 2.0 이름 체계로 이전(타깃 치환).

무엇을 하나: 1.x(denver-agent) 시절 vault(팀 지식을 모아두는 Obsidian 폴더)에 쌓인 노트에서
**도구 식별자만** 새 이름으로 바꾼다 — 에이전트·커맨드·MCP 도구·산출물·env 이름
(`ssot_*`, `ssot-<도구명>`, `DENVER_VAULT_DIR`, `denver-agent*`). 개념어 "SSOT"(단일 진실
원천)와 기록 제목 속 일반 표현(예: `contract-ssot`, "단일 ssot")은 건드리지 않는다.

파일명도 동일 패턴으로 치환해 위키링크 정합을 유지한다(내용 속 링크와 파일명이 함께 바뀜).

사용:
  python3 dw-migrate-vault.py --vault <경로>              # dry-run — vault 노트 미리보기(쓰기 없음)
  python3 dw-migrate-vault.py --vault <경로> --apply      # 실제 적용 — 백업(tar.gz) 자동 생성
  python3 dw-migrate-vault.py --project <레포> [--project <레포2> ...] [--apply]

`--project` 모드: 대상 레포의 **설치된 에이전트** `<레포>/.claude/agents/*.md` 안의 구 식별자를 치환한다.
왜 필요한가: 1.x 가 설치한 do-er 에이전트(예: `senior-backend-engineer.md`)는 **파일명은 멀쩡하나
`tools:` frontmatter 가 `mcp__plugin_denver-agent_ssot-vault__ssot_write_*` 같은 죽은 도구 이름**을
가리켜, 디스패치돼도 기록 도구(`dw_write_*`)를 못 써 vault 기록이 조용히 실패한다. 이런 파일은
파일명 접두(`ssot-`) 기반 정리 그물에도, vault 전용 치환에도 안 걸린다 — 이 모드가 그 공백을 메운다.
`--vault` 와 `--project` 는 함께 쓸 수 있고, 최소 하나는 있어야 한다.

원칙: 표준 라이브러리만, *.md 만 처리, `.git`/`.obsidian`/`.trash` 제외. 적용 전 대상 루트를
`<루트 옆>/<루트명>-pre-2.0-backup-<시각>.tar.gz` 로 백업한다(실수해도 되돌릴 수 있게).
사용처: /dw-setup 의 "레거시 정리" (d) 단계.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
from pathlib import Path

# 구(舊) 이름 리터럴 주의: 이 파일의 패턴은 감지·치환 대상 표기다.
# 도구 식별자 alternation — 접두 중복은 긴 것 먼저(ratifier > ratify, vault-guard > vault).
_IDENT = (
    "governed|orchestrator|ratifier|session-digest|session-context|checks|config|"
    "manifest|agents\\.json|lint|vault-guard|worktree-guard|artifact-guard|"
    "plugin-scope|compile|mcp|build|install|ratify|review|scope|vault"
)
_SUBS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"ssot_"), "dw_"),                          # MCP 도구 (ssot_read 등)
    (re.compile(rf"ssot-({_IDENT})"), r"dw-\1"),            # 도구 식별자만 — 개념 슬러그 보존
    (re.compile(r"DENVER_VAULT_DIR"), "DW_VAULT_DIR"),      # env
    (re.compile(r"denver-agent"), "denver-workflow"),        # 플러그인명·구 vault 경로 문자열
]
_SKIP_DIRS = {".git", ".obsidian", ".trash"}


def _subst(text: str) -> str:
    for pat, rep in _SUBS:
        text = pat.sub(rep, text)
    return text


def _md_files(vault: Path) -> list[Path]:
    out = []
    for p in sorted(vault.rglob("*.md")):
        if not any(part in _SKIP_DIRS for part in p.relative_to(vault).parts):
            out.append(p)
    return out


def plan(vault: Path) -> tuple[list[tuple[Path, Path]], list[Path]]:
    """(파일명 변경 목록, 내용 변경 파일 목록) — 쓰기 없음."""
    renames: list[tuple[Path, Path]] = []
    content_changes: list[Path] = []
    for p in _md_files(vault):
        new_name = _subst(p.name)
        if new_name != p.name:
            renames.append((p, p.with_name(new_name)))
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _subst(text) != text:
            content_changes.append(p)
    return renames, content_changes


def backup(vault: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = vault.parent / f"{vault.name}-pre-2.0-backup-{stamp}"
    archive = shutil.make_archive(str(base), "gztar", root_dir=vault.parent, base_dir=vault.name)
    return Path(archive)


def apply(vault: Path) -> tuple[int, int]:
    renamed = changed = 0
    for p in _md_files(vault):
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        new_text = _subst(text)
        if new_text != text:
            p.write_text(new_text, encoding="utf-8")
            changed += 1
        new_name = _subst(p.name)
        if new_name != p.name:
            p.rename(p.with_name(new_name))
            renamed += 1
    return renamed, changed


def migrate_root(root: Path, label: str, do_apply: bool) -> bool:
    """한 루트(vault 또는 프로젝트 .claude)를 치환. 변경이 하나라도 있었으면 True."""
    renames, content_changes = plan(root)
    if not renames and not content_changes:
        print(f"[{label}] 변경 없음 — 이미 2.0 이름 체계입니다. ({root})")
        return False

    print(f"[{label}] 대상: {root}")
    print(f"[{label}] 내용 치환 대상: {len(content_changes)}개 파일")
    print(f"[{label}] 파일명 변경 대상: {len(renames)}개")
    for old, new in renames:
        print(f"  {old.relative_to(root)} → {new.name}")

    if not do_apply:
        return True

    arc = backup(root)
    print(f"[{label}] 백업 생성: {arc}")
    renamed, changed = apply(root)
    print(f"[{label}] 적용 완료: 내용 {changed}개 파일 치환, 파일명 {renamed}개 변경")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="1.x 이름을 2.0(dw-*) 체계로 이전(타깃 치환)")
    ap.add_argument("--vault", help="vault 절대경로 (노트 전체 치환)")
    ap.add_argument("--project", action="append", default=[],
                    help="플러그인 소비 레포 절대경로 — <레포>/.claude 설치 아티팩트 치환 (반복 가능)")
    ap.add_argument("--apply", action="store_true", help="실제 적용(기본은 dry-run 미리보기)")
    args = ap.parse_args()

    if not args.vault and not args.project:
        print("에러: --vault 또는 --project 중 최소 하나가 필요합니다.", file=sys.stderr)
        return 1

    targets: list[tuple[Path, str]] = []
    if args.vault:
        vault = Path(args.vault).expanduser()
        if not vault.is_dir():
            print(f"에러: vault 폴더가 없습니다 — {vault}", file=sys.stderr)
            return 1
        targets.append((vault, "vault"))
    for proj in args.project:
        # agents/ 로 한정 — stale 고아 do-er 가 사는 곳. skills(재설치가 재생성)·
        # agent-memory(사용자 데이터)는 건드리지 않는다.
        agents = Path(proj).expanduser() / ".claude" / "agents"
        if not agents.is_dir():
            print(f"건너뜀: {agents} 없음 — 설치 안 됨/에이전트 없음?", file=sys.stderr)
            continue
        targets.append((agents, f"project:{Path(proj).name}"))

    any_changes = False
    for root, label in targets:
        if migrate_root(root, label, args.apply):
            any_changes = True

    if not any_changes:
        return 0
    if not args.apply:
        print("\n(dry-run — 아직 아무것도 바꾸지 않았습니다. 적용하려면 --apply)")
    else:
        print("\n다음: strict 컴파일로 검증하세요 — make dry-run (에러 0 이어야 함)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
