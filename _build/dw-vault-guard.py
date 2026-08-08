#!/usr/bin/env python3
"""SSOT vault 가드 — Claude Code PostToolUse 훅.

에이전트가 (대상 프로젝트 세션에서든 vault 세션에서든) Obsidian vault 의 `.md` 를
편집할 때 frontmatter 계약을 검사하고, '복종 경로'(rule/guidance)를 에이전트가 stable 로
승격하려 하면 알린다. 차단하지 않는다(PostToolUse 한계 + 검증자는 단독 게이트 아님) —
additionalContext 로 피드백한다.

핵심 설계(어드바이저 반영):
  - 메모리·계약 = 라이브 직접 읽기/쓰기, 비컴파일 → 에이전트가 draft 로 자유 기록
  - 규칙·원칙 = 컴파일/stable/사람 비준 → 에이전트는 draft 제안만, stable 승격은 사람
  - draft 는 '가시성'이 아니라 '컴파일'을 게이트한다. 진짜 비준 게이트는 `make install` 을
    돌리며 draft→stable 로 올리는 사람이다.

vault 위치: $CLAUDE_PROJECT_DIR/.claude/dw-config.json 의 vault_root, 없으면 프로젝트가
_build/dw-compile.py 를 가지면 그 프로젝트를 vault 로 본다. 표준 라이브러리만 사용.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import dw_runtime

SKIP_DIRS = {".git", ".venv", "node_modules", ".bkit", "__pycache__",
             ".obsidian", ".claude", "build", "_templates",
             "commands", "hooks", ".claude-plugin", "skills"}  # 플러그인 저작물·번들 스킬 — SSOT 노트 아님
FM_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)

# type 별 필수 필드(가드는 '존재'만 본다 — 의미 검증은 컴파일러 몫).
REQUIRED = {
    "rule": ["type", "scope", "status", "enforced-by", "compiles-to"],
    "guidance": ["type", "scope", "status", "compiles-to"],
    "procedure": ["type", "scope", "status", "compiles-to"],
    "skill-manifest": ["type", "scope", "skill-name", "skill-description"],
    "memory": ["type", "status", "title"],
    "contract": ["type", "status"],
    "spec": ["type", "status"],
    "agent": ["type"],
    "decision": ["type"],
    "reference": ["type"],
    "repo-map": ["type", "status", "title"],
}
# 에이전트가 stable 로 승격하면 '사람 비준 영역'이라 알릴 type
HUMAN_RATIFIED = {"rule", "guidance"}


def _vault_root(project: Path):
    """vault 위치 — 정본은 `dw_runtime.find_vault`(2.16.0). 없으면 None(훅은 no-op 한다).

    해석 순서: `DW_VAULT_DIR`(env) > `<project>/.claude/dw-config.json` 의 `vault_root`(조상·git
    본체 레포까지 탐색) > 규약 경로 > 이 레포가 플러그인 본체면 자기 자신.

    ⚠️ 2.16.0 에서 **우선순위가 뒤집혔다** — 종전 사본은 config 를 env 보다 먼저 봤다. 같은
    머신에서 도구별로 다른 vault 를 가리킬 수 있던 상태를 없애는 대가로, "프로젝트가 config 로
    vault B 에 묶였는데 env 는 A 를 말한다" 면 이제 A 를 지킨다. 그 상태는 조용히 넘기지 않고
    SessionStart 다이제스트가 경고한다(`dw_runtime.vault_conflict_note`) — 노출이 이 전환의
    전제조건이다. 워크트리 대응(조상 탐색)과 리터럴 홈 접두 확장은 유지된다.
    """
    return dw_runtime.find_vault(project, require="dir", ancestors=8, git_probe=True,
                                 self_repo_fallback=True)


def _parse_frontmatter(text: str) -> dict | None:
    m = FM_RE.match(text)
    if not m:
        return None
    fm: dict = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip("'\"")
    return fm


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
    file_path = Path(fp)

    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())

    # (b) vault 단일 정책 강제: deprecated 된 .claude/agent-memory/ 쓰기를 vault 로 유도.
    try:
        amrel = file_path.resolve().relative_to((project / ".claude" / "agent-memory").resolve())
        if amrel.suffix == ".md" and amrel.name != "MEMORY.md":
            out = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext":
                   ".claude/agent-memory/ 는 deprecated 입니다 — 메모리 SSOT는 vault `memory/` 입니다. "
                   "이 학습을 vault memory/ 에 type:memory, status:draft 로 기록하세요."}}
            print(json.dumps(out, ensure_ascii=False))
            return 0
    except ValueError:
        pass

    vault = _vault_root(project)
    if vault is None:
        return 0
    # vault 자신의 세션 = 사람 큐레이션 → draft 게이트(stable 알림) 끔.
    # 타깃 repo(대상 프로젝트)에서 에이전트가 vault 로 쓸 때만 게이트 적용.
    is_vault_session = project.resolve() == vault.resolve()
    try:
        rel = file_path.resolve().relative_to(vault.resolve())
    except ValueError:
        return 0  # vault 밖 파일은 이 가드 대상 아님
    if any(part in SKIP_DIRS for part in rel.parts):
        return 0
    # vault 루트의 .md 는 문서/설정(README·BOOTSTRAP·MEMORY 등) — SSOT 노트가 아니다.
    # SSOT 노트는 하위 폴더(rules/·guidance/·memory/·contracts/ 등)에 산다.
    if len(rel.parts) == 1:
        return 0
    # CC auto-memory 인덱스(MEMORY.md)는 검사 제외 — CC 가 관리하는 파일.
    if file_path.name == "MEMORY.md":
        return 0
    if not file_path.exists():
        return 0
    try:
        text = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0

    fm = _parse_frontmatter(text)
    notes: list[str] = []

    if fm is None:
        notes.append(f"{rel}: frontmatter(--- 블록)가 없음 — SSOT 노트는 type 등 frontmatter 필수")
    else:
        ntype = fm.get("type", "")
        # CC auto-memory 포맷(name+description+metadata.type) 수용 — vault 가 자동 캡처도 받는다.
        if not ntype and fm.get("name") and fm.get("description"):
            return 0
        if not ntype:
            notes.append(f"{rel}: frontmatter 에 type 없음")
        elif ntype not in REQUIRED:
            notes.append(f"{rel}: 알 수 없는 type '{ntype}' (rule/guidance/memory/contract/agent/decision/skill-manifest/reference)")
        else:
            missing = [k for k in REQUIRED[ntype] if not fm.get(k)]
            if missing:
                notes.append(f"{rel}: type:{ntype} 필수 필드 누락 — {', '.join(missing)}")
            # draft 게이트(권고): 복종 경로를 stable 로 쓰면 사람 비준 영역임을 알림.
            # vault 자신 세션(사람 큐레이션)에서는 끔.
            if not is_vault_session and ntype in HUMAN_RATIFIED and fm.get("status") == "stable":
                notes.append(
                    f"{rel}: type:{ntype} 을 status:stable 로 작성함. stable 승격은 사람 비준 행위다 "
                    "— 에이전트 제안이라면 status:draft 로 두면 사람이 `make install` 시 비준한다"
                )

    if not notes:
        return 0
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "SSOT vault 가드:\n  - " + "\n  - ".join(notes),
        }
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
