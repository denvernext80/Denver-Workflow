#!/usr/bin/env python3
"""dw-graphify-gate — PreToolUse 훅: dw_search / 코드 Grep 직전 graphify 우선 리마인더(등록 시에만).

graphify 가 프로젝트 `.mcp.json` 에 등록돼 있으면 두 경우에 graphify 그래프 우선 탐색을
additionalContext 로 주입한다(차단 아님 — self-correct 유도):
  - `dw_search`(substring 지식 검색): 항상 nudge(지식은 graphify 가 대체 가능).
  - `Grep`(코드 구조 탐색): 패턴이 **심볼형**(식별자·점경로)일 때만 nudge. 리터럴 문자열·정규식·구절
    (에러메시지·설정키·주석)은 AST 그래프가 답 못 하니 침묵 — grep 이 맞다. 과다발화로 무시당하는 것 방지.

graphify 미등록이면 조용히 통과(옵셔널 불변식 — 미설치 프로젝트 무영향). dw_read(원문 확정)는 매처에서
제외 — 정상 흐름 방해 방지.

hooks.json 의 PreToolUse matcher `mcp__plugin_denver-workflow_dw-vault__dw_search` 와 `Grep` 로 배선.
표준 라이브러리만. 출력: PreToolUse additionalContext JSON 또는 무출력.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_NUDGE = (
    "🕸 graphify 활성 — 이 substring `dw_search` 전에 graphify 그래프로 먼저 발견했는가? "
    "지식/문서는 `query_graph`·`get_neighbors`·`shortest_path`(기본 그래프), 특정 레포 코드는 "
    "`project_path=<repo 절대경로>`. graphify 로 관련 노드를 아직 못 잡았으면 그걸 먼저 하라 — "
    "`dw_search` 는 graphify 미탐색 시 폴백. (원문 확정·인용은 이후 `dw_read`.)"
)

_GREP_NUDGE = (
    "🕸 graphify 활성 — 코드 **구조**(정의·호출자·의존)를 찾는 grep 으로 보인다. raw grep·graphify "
    "CLI 셸아웃 대신 **세션 graphify MCP**로: `query_graph`·`get_neighbors`(`project_path=<repo 절대경로>`). "
    "grep 은 리터럴 문자열(에러메시지·설정키·주석·비코드 파일)에만 쓰라 — 심볼·함수·클래스 구조는 그래프가 정확하다."
)

# 심볼형 패턴만: 식별자/점경로(handleSubmit·foo.bar·User_model). 공백·정규식 메타·따옴표가 있으면
# 리터럴/정규식 검색이라 제외(그래프가 답 못 함 → 침묵). 선두는 문자/밑줄(숫자 리터럴 제외).
_SYMBOLISH = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


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

    tool = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") or {}
    if tool == "Grep":
        # 코드 구조 탐색으로 보이는 심볼형 패턴만 nudge. 리터럴/정규식은 침묵.
        pattern = str(tool_input.get("pattern") or "")
        if not _SYMBOLISH.match(pattern):
            return 0
        nudge = _GREP_NUDGE
    else:
        # dw_search(및 그 외 배선된 매처) — substring 지식 검색.
        nudge = _NUDGE

    print(json.dumps(
        {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": nudge}},
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
