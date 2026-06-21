#!/usr/bin/env python3
"""SSOT worktree 격리 가드 — Claude Code PreToolUse 훅(Agent/Task spawn 시점).

worktree 격리는 '파일을 어떻게 썼나'(내용)가 아니라 '서브에이전트를 어떻게 spawn 했나'
(오케스트레이션)의 속성이다 — grep 할 파일 자국이 없어 PostToolUse 린터·vault 가드가
구조적으로 못 잡는다. 그래서 spawn 그 순간(PreToolUse)에 끼어드는 유일한 강제 지점이다.

키는 subagent_type 이 파일을 변경할 수 있는데(=읽기전용 화이트리스트 밖) worktree 증거가
없을 때다. 증거 = Agent 도구의 isolation:"worktree" 파라미터 OR prompt 본문의 워크트리 경로
언급(.claude/worktrees·worktree·워크트리 — 수동 워크트리 관행 수용). 둘 다 없으면 공유
체크아웃 작업으로 보고 ask(차단 아님 — 단일세션·머지 등 공유 체크아웃이 정당한 경우 사람이 승인).

근거: 2026-06-14 cross-repo near-miss — Travel-One general-purpose 에이전트들이 공유
체크아웃 feature 브랜치에서 작업, 커밋이 main 에 잠깐 올라갔다 reset --hard 로 복구.
출처 vault: memory/2026-06-14-...isolationworktree-필수..., guidance/worktree-isolation.md

차단이 아니라 ask 다(어드바이저 반영): 우리 시스템의 비-MCP 레이어는 'feedback not block'.
표준 라이브러리만 사용.
"""
from __future__ import annotations

import json
import re
import sys

# 명백히 읽기 전용이거나 in-place 검증만 하는 에이전트 — worktree 불요.
# (구현·커밋하는 에이전트만 게이트 대상. 화이트리스트는 소문자 비교.)
READONLY = {
    "explore", "plan", "general-purpose-readonly",
    "code-review", "design-review", "security-qa", "code-analyzer",
    "design-validator", "gap-detector", "qa-strategist", "qa-test-planner",
    "report-generator", "statusline-setup", "claude-code-guide",
    "ssot-governed",  # 하네스 자신은 spawn 대상이 아니라 세션 에이전트
}
# prompt 본문에서 워크트리 작업 증거로 인정할 마커(수동 워크트리 관행 수용).
WT_MARKERS = re.compile(r"worktree|워크트리|/worktrees", re.IGNORECASE)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if payload.get("hook_event_name") not in (None, "PreToolUse"):
        return 0
    if payload.get("tool_name") not in ("Agent", "Task"):
        return 0

    ti = payload.get("tool_input") or {}
    subtype = str(ti.get("subagent_type", "")).strip().lower()
    isolation = str(ti.get("isolation", "")).strip().lower()
    prompt = str(ti.get("prompt", "")) + " " + str(ti.get("description", ""))

    # 읽기전용/검증 에이전트 → 통과.
    if subtype in READONLY:
        return 0
    # 명시적 격리 파라미터 → 통과.
    if isolation == "worktree":
        return 0
    # prompt 가 워크트리 작업을 지시 → 통과(수동 워크트리 관행).
    if WT_MARKERS.search(prompt):
        return 0

    label = subtype or "(미지정)"
    reason = (
        f"worktree 격리 미확인: subagent_type='{label}' 는 파일을 변경/커밋할 수 있는데 "
        "isolation:'worktree' 파라미터도, prompt 내 워크트리 경로 지시도 없습니다 → 공유 체크아웃 작업으로 보입니다. "
        "공유 체크아웃에서 브랜치 작업은 동시성·브랜치-튐으로 main 오염 위험입니다"
        "(2026-06-14 Travel-One near-miss: 커밋이 main 에 올라갔다 reset --hard 복구). "
        "권장: Agent 를 isolation:'worktree' 로 재호출하거나, prompt 에 격리 워크트리 경로를 명시하세요. "
        "단일 세션·머지 등 공유 체크아웃이 의도된 작업이면 승인하세요. "
        "출처: vault guidance/worktree-isolation.md"
    )
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
