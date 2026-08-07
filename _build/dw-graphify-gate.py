#!/usr/bin/env python3
"""dw-graphify-gate v2 — PreToolUse 훅: graphify 우선을 '조언'에서 '게이트(ask)'로 강화.

배경: v1 은 additionalContext 넛지만 줬고, graphify 가 발화돼도 에이전트가 무시하고 dw_search/
grep 로 직행했다(직접편집 bypass 와 같은 실패 모드 — 조언은 라우팅당한다). v2 는 **이번 세션에
graphify 를 아직 한 번도 안 썼으면 dw_search/심볼-Grep 직전에 ask 로 차단**한다. graphify 를 한 번
쓰면(텔레메트리 로그로 판별) 그 세션에선 다시 조언 모드로 내려간다 — self-releasing.

의존: dw-telemetry.py 가 <vault>/.dw-state/access.jsonl 에 session 별 graphify 이벤트를 남긴다.
로그가 없거나 graphify 미등록이면 v1 과 동일하게 (조언 또는 침묵) 동작 — 안전 폴백.

정책:
  - graphify 미등록(project .mcp.json) → 침묵 통과(옵셔널 불변식).
  - 이번 세션 graphify 사용 기록 있음 → v1 넛지(additionalContext)만.
  - 사용 기록 없음 → permissionDecision "ask" (override 가능). dw_read 는 매처에서 제외.
표준 라이브러리만. 결코 예외로 안 터진다(실패 시 통과).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_SYMBOLISH = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")

_NUDGE = (
    "🕸 graphify 활성 — 이 substring `dw_search` 전에 graphify 그래프로 먼저 발견했는가? "
    "지식/문서는 `query_graph`·`get_neighbors`·`shortest_path`(기본 그래프), 특정 레포 코드는 "
    "`project_path=<repo 절대경로>`. (원문 확정·인용은 이후 `dw_read`.)"
)
_GREP_NUDGE = (
    "🕸 graphify 활성 — 코드 **구조**(정의·호출자·의존) grep 으로 보인다. raw grep 대신 "
    "**세션 graphify MCP**: `query_graph`·`get_neighbors`(`project_path=<repo 절대경로>`). "
    "grep 은 리터럴(에러메시지·설정키·주석)에만."
)
_ASK = (
    "🕸 graphify 게이트: 이번 세션에 graphify 그래프를 **아직 한 번도** 쓰지 않았다. 규율은 "
    "graphify 우선(코드·지식 탐색) — `query_graph`/`get_neighbors`/`shortest_path` 로 먼저 발견한 뒤 "
    "`dw_search`/grep 은 폴백으로만 쓴다. graphify 로 먼저 탐색하라."
)


def _vault_root(project: Path):
    cfg = project / ".claude" / "dw-config.json"
    if cfg.exists():
        try:
            v = json.loads(cfg.read_text(encoding="utf-8")).get("vault_root")
            if v and Path(v).is_dir():
                return Path(v)
        except Exception:
            pass
    env = os.environ.get("DW_VAULT_DIR")
    if env:
        env = os.path.expandvars(os.path.expanduser(env))
        if Path(env).is_dir():
            return Path(env)
    conv = Path.home() / "denver-workflow-vault"
    if conv.is_dir():
        return conv
    if (project / "_build" / "dw-compile.py").exists():
        return project
    return None


# automode(auto/dontAsk/bypassPermissions)에선 ask 가 무력화 → deny 로 상향(훅 deny 는 항상 차단).
# dw_search/Grep 은 edit 이 아니므로 acceptEdits 는 hard 에 넣지 않는다. DW_GATE_HARD 로 오버라이드.
def _hard(payload) -> bool:
    env = os.environ.get("DW_GATE_HARD", "").lower()
    if env in ("1", "deny", "hard", "true"):
        return True
    if env in ("0", "ask", "soft", "false"):
        return False
    return str(payload.get("permission_mode") or "") in {"auto", "dontAsk", "bypassPermissions"}


def _graphify_registered(project: Path) -> bool:
    try:
        p = project / ".mcp.json"
        if not p.exists():
            return False
        servers = json.loads(p.read_text(encoding="utf-8")).get("mcpServers", {})
        return isinstance(servers, dict) and "graphify" in servers
    except Exception:
        return False


def _graphify_used_this_session(vault: Path, session: str) -> bool:
    """텔레메트리 로그 tail 에서 이번 세션의 graphify 이벤트 유무. 로그 없으면 False(→ ask)."""
    if not session:
        return False
    log = vault / ".dw-state" / "access.jsonl"
    if not log.is_file():
        return False
    try:
        lines = log.read_text(encoding="utf-8").splitlines()[-4000:]  # tail 만
    except Exception:
        return False
    for line in reversed(lines):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("session") == session and r.get("kind") == "graphify":
            return True
    return False


def _emit_ctx(text: str):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "additionalContext": text}}, ensure_ascii=False))


def _emit_gate(text: str, hard: bool):
    tail = " (automode → 차단.)" if hard else " (그래도 이 검색이 필요하면 override.)"
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny" if hard else "ask",
        "permissionDecisionReason": text + tail}}, ensure_ascii=False))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        if payload.get("hook_event_name") not in (None, "PreToolUse"):
            return 0
        project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())
        if not _graphify_registered(project):
            return 0

        tool = str(payload.get("tool_name") or "")
        ti = payload.get("tool_input") or {}
        is_grep = tool == "Grep"
        if is_grep and not _SYMBOLISH.match(str(ti.get("pattern") or "")):
            return 0  # 리터럴 grep 은 그래프가 답 못 함 → 침묵

        vault = _vault_root(project)
        session = payload.get("session_id") or ""
        used = _graphify_used_this_session(vault, session) if vault else False
        if used:
            _emit_ctx(_GREP_NUDGE if is_grep else _NUDGE)  # 이미 썼으면 부드럽게
        else:
            _emit_gate(_ASK, _hard(payload))  # 아직 안 썼으면 게이트(automode=deny, else ask)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
