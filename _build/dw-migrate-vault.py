#!/usr/bin/env python3
"""dw-migrate-vault — 1.x vault 콘텐츠를 2.0 이름 체계로 이전(타깃 치환).

무엇을 하나: 1.x(denver-agent) 시절 vault(팀 지식을 모아두는 Obsidian 폴더)에 쌓인 노트에서
**도구 식별자만** 새 이름으로 바꾼다 — 에이전트·커맨드·MCP 도구·산출물·env 이름
(`ssot_*`, `ssot-<도구명>`, `DENVER_VAULT_DIR`, `denver-agent*`). 개념어 "SSOT"(단일 진실
원천)와 기록 제목 속 일반 표현(예: `contract-ssot`, "단일 ssot")은 건드리지 않는다.

파일명도 동일 패턴으로 치환해 위키링크 정합을 유지한다(내용 속 링크와 파일명이 함께 바뀜).

사용:
  python3 dw-migrate-vault.py --vault <경로>           # dry-run — 바꿀 내용 미리보기(쓰기 없음)
  python3 dw-migrate-vault.py --vault <경로> --apply   # 실제 적용 — 백업(tar.gz) 자동 생성

원칙: 표준 라이브러리만, *.md 만 처리, `.git`/`.obsidian`/`.trash` 제외. 적용 전 vault 전체를
`<vault 옆>/<vault명>-pre-2.0-backup-<시각>.tar.gz` 로 백업한다(실수해도 되돌릴 수 있게).
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


def main() -> int:
    ap = argparse.ArgumentParser(description="1.x vault 를 2.0 이름 체계로 이전(타깃 치환)")
    ap.add_argument("--vault", required=True, help="vault 절대경로")
    ap.add_argument("--apply", action="store_true", help="실제 적용(기본은 dry-run 미리보기)")
    args = ap.parse_args()

    vault = Path(args.vault).expanduser()
    if not vault.is_dir():
        print(f"에러: vault 폴더가 없습니다 — {vault}", file=sys.stderr)
        return 1

    renames, content_changes = plan(vault)
    if not renames and not content_changes:
        print("변경 없음 — 이미 2.0 이름 체계입니다.")
        return 0

    print(f"대상 vault: {vault}")
    print(f"내용 치환 대상: {len(content_changes)}개 파일")
    print(f"파일명 변경 대상: {len(renames)}개")
    for old, new in renames:
        print(f"  {old.relative_to(vault)} → {new.name}")

    if not args.apply:
        print("\n(dry-run — 아직 아무것도 바꾸지 않았습니다. 적용하려면 --apply)")
        return 0

    arc = backup(vault)
    print(f"\n백업 생성: {arc}")
    renamed, changed = apply(vault)
    print(f"적용 완료: 내용 {changed}개 파일 치환, 파일명 {renamed}개 변경")
    print("다음: strict 컴파일로 검증하세요 — make dry-run (에러 0 이어야 함)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
