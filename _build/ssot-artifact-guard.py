#!/usr/bin/env python3
"""SSOT 산출물 위치 가드 — Claude Code PostToolUse 훅(Write|Edit).

durable 분석/스펙/계획/설계 문서를 product repo 의 docs/ 등에만 두면 worktree 청소·브랜치 삭제 시
휘발한다. 이 워크스페이스 규율은 'durable 한 건 전부 vault SSOT'(specs/ via ssot_write_spec,
학습은 memory/ via ssot_write_memory). vault-guard 는 vault *내부* .md 만 보므로, 이 가드는
vault *밖*(product repo)의 durable 문서 쓰기를 잡아 vault 로 유도한다(차단 아님 — additionalContext).

발화 조건: Denver-governed 프로젝트(.claude/ssot-config.json 존재)에서, vault 밖 .md 를 쓰는데
경로/이름이 durable 문서로 보일 때. README·CHANGELOG·코드인접 문서는 제외(오탐 방지).
표준 라이브러리만.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# durable 지식 문서 신호(경로 또는 파일명) — 분석/스펙/계획/설계/결정/감사/리뷰/제안 등.
DURABLE = re.compile(
    r"(^|/)docs/|analysis|spec|plan|design|gaps?|proposal|rfc|adr|decision|architecture"
    r"|audit|review|roadmap|설계|계획|분석|스펙|명세|제안|감사",
    re.IGNORECASE)
# 제외(코드-인접·관례 문서는 repo 에 남는다)
EXCLUDE = re.compile(r"(^|/)(README|CHANGELOG|LICENSE|NOTICE|CONTRIBUTING|CODEOWNERS)", re.IGNORECASE)


def _vault_root(project: Path) -> Path | None:
    cfg = project / ".claude" / "ssot-config.json"
    if cfg.exists():
        try:
            v = json.loads(cfg.read_text(encoding="utf-8")).get("vault_root")
            if v and Path(v).is_dir():
                return Path(v)
        except (json.JSONDecodeError, OSError):
            pass
    # stored vault_root 부재/stale(이동된 경로) 자가치유 — 런처와 동일 규약(env > ~/denver-agent-vault)
    env = os.environ.get("DENVER_VAULT_DIR")
    if env and Path(env).is_dir():
        return Path(env)
    conv = Path.home() / "denver-agent-vault"
    if conv.is_dir():
        return conv
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if payload.get("hook_event_name") not in (None, "PostToolUse"):
        return 0
    fp = (payload.get("tool_input") or {}).get("file_path")
    if not fp or not fp.endswith(".md"):
        return 0

    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())
    vault = _vault_root(project)
    if vault is None:
        return 0  # Denver-governed 프로젝트 아님
    fpath = Path(fp).resolve()
    # vault 내부 .md 는 vault-guard 담당 — 여기선 vault '밖' durable 문서만.
    try:
        fpath.relative_to(vault.resolve())
        return 0
    except ValueError:
        pass
    try:
        rel = fpath.relative_to(project.resolve()).as_posix()
    except ValueError:
        rel = fpath.name
    if rel.startswith(".claude/") or EXCLUDE.search(rel) or not DURABLE.search(rel):
        return 0

    out = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext":
           f"SSOT 산출물 가드: '{rel}' 는 durable 분석/스펙/계획 문서로 보입니다. "
           "repo docs/ 는 worktree 청소·브랜치 삭제 시 휘발합니다 — 이 워크스페이스 규율상 durable 한 건 "
           "**vault SSOT** 가 단일 출처입니다. `ssot_write_spec`(계획·스펙·설계) 또는 `ssot_write_memory`"
           "(학습)로 vault 에 기록하세요. repo 사본은 코드 경로 링크용으로만 두고, 정본은 vault 에 둡니다."}}
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
