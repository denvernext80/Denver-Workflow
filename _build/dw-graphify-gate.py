#!/usr/bin/env python3
"""dw-graphify-gate — PreToolUse 훅: substring dw_search 직전 graphify 우선 리마인더(등록 시에만).

graphify 가 프로젝트 `.mcp.json` 에 등록돼 있으면, `dw_search`(substring 검색) 호출 직전에 graphify
그래프 우선 탐색을 additionalContext 로 주입한다(차단 아님 — self-correct 유도). graphify 미등록이면
조용히 통과(옵셔널 불변식 — 미설치 프로젝트 무영향). dw_read(원문 확정)는 매처에서 제외 — 정상 흐름 방해 방지.

hooks.json 의 PreToolUse matcher `mcp__plugin_denver-workflow_dw-vault__dw_search` 로 배선.
표준 라이브러리만. 출력: PreToolUse additionalContext JSON 또는 무출력.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_NUDGE = (
    "🕸 graphify 활성 — 이 substring `dw_search` 전에 graphify 그래프로 먼저 발견했는가? "
    "지식/문서는 `query_graph`·`get_neighbors`·`shortest_path`(기본 그래프), 특정 레포 코드는 "
    "`project_path=<repo 절대경로>`. graphify 로 관련 노드를 아직 못 잡았으면 그걸 먼저 하라 — "
    "`dw_search` 는 graphify 미탐색 시 폴백. (원문 확정·인용은 이후 `dw_read`.)"
)


def _graphify_registered(project: Path) -> bool:
    """프로젝트 .mcp.json 에 graphify MCP 서버가 등록돼 있으면 True. 실패는 조용히 False."""
    try:
        p = project / ".mcp.json"
        if not p.exists():
            return False
        servers = json.loads(p.read_text(encoding="utf-8")).get("mcpServers", {})
        return isinstance(servers, dict) and "graphify" in servers
    except Exception:
        return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if payload.get("hook_event_name") not in (None, "PreToolUse"):
        return 0
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())
    if not _graphify_registered(project):
        return 0
    print(json.dumps(
        {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": _NUDGE}},
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
