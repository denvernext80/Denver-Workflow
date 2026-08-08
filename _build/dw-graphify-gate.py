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

import dw_runtime

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


# automode(auto/dontAsk/bypassPermissions)에선 ask 가 무력화 → deny 로 상향(훅 deny 는 항상 차단).
# dw_search/Grep 은 edit 이 아니므로 acceptEdits 는 hard 에 넣지 않는다. DW_GATE_HARD 로 오버라이드.
def _hard(payload) -> bool:
    env = os.environ.get("DW_GATE_HARD", "").lower()
    if env in ("1", "deny", "hard", "true"):
        return True
    if env in ("0", "ask", "soft", "false"):
        return False
    return str(payload.get("permission_mode") or "") in {"auto", "dontAsk", "bypassPermissions"}


def _ancestors(p: Path, limit: int = 8):
    """cwd 와 그 조상들(제한적). do-er 는 `<repo>/.claude/worktrees/<n>` 에서 돌아 위를 봐야 한다."""
    cur = p.resolve()
    for _ in range(limit):
        yield cur
        if cur.parent == cur:
            return
        cur = cur.parent


def _mcp_has_graphify(d: Path) -> bool:
    try:
        p = d / ".mcp.json"
        if not p.exists():
            return False
        servers = json.loads(p.read_text(encoding="utf-8")).get("mcpServers", {})
        return isinstance(servers, dict) and "graphify" in servers
    except Exception:
        return False


def _log_has_any_graphify(vault) -> bool:
    """이 환경에서 graphify 가 **한 번이라도** 쓰였나 = MCP 서버가 실재한다는 증거.

    훅 payload 에는 세션 MCP 목록이 없어 서버 도달성을 직접 못 읽는다. 텔레메트리 로그가 그 대리
    증거다 — 누군가 실제로 호출해 기록이 남았다면 서버는 이 환경에 있다.
    """
    if vault is None:
        return False
    log = vault / ".dw-state" / "access.jsonl"
    if not log.is_file():
        return False
    try:
        lines = log.read_text(encoding="utf-8").splitlines()[-4000:]
    except Exception:
        return False
    for line in reversed(lines):
        try:
            if json.loads(line).get("kind") == "graphify":
                return True
        except Exception:
            continue
    return False


def _graphify_applicable(project: Path, vault) -> bool:
    """이 위치에서 게이트를 걸어야 하나 — **유용하고(그래프 존재) 도달 가능할 때만**.

    ① 명시 등록: cwd 나 조상의 `.mcp.json` 에 graphify(오케스트레이터 워크스페이스 경로).
    ② 그래프 존재 + 환경 사용 증거: 조상에 `graphify-out/graph.json` 이 있고 로그에 graphify 이벤트가
       있으면 do-er 가 워크트리에서 돌아도 건다. do-er 는 세션 MCP 를 **상속**하므로
       `project_path=<repo>` 로 그 그래프를 호출할 수 있다 — 능력은 있는데 게이트만 없던 구간이다.

    둘 다 아니면 침묵. graphify 는 옵셔널 불변식이라 미설치 환경을 막으면 안 된다(fail-open).
    특히 automode 에선 이 판정이 deny 로 이어지므로, **그래프만 있고 서버가 없는 환경을 차단하지
    않도록** ②는 사용 증거를 반드시 함께 요구한다.
    """
    try:
        for d in _ancestors(project):
            if _mcp_has_graphify(d):
                return True
        for d in _ancestors(project):
            if (d / "graphify-out" / "graph.json").is_file():
                return _log_has_any_graphify(vault)
    except Exception:
        return False
    return False


def _telemetry_observing(vault) -> bool:
    """텔레메트리가 **실제로 관측 중인가** = access.jsonl 이 존재하는가.

    로그가 없으면 "graphify 를 안 썼다" 가 아니라 **"알 수 없다"** 다. 둘을 구분하지 않으면
    관측 부재를 위반으로 읽게 된다 — `_graphify_used_this_session()` 이 두 경우 모두 False 를
    돌려주므로, 호출부가 이 함수로 갈라야 한다.
    """
    try:
        return vault is not None and (vault / ".dw-state" / "access.jsonl").is_file()
    except Exception:
        return False


def _graphify_used_this_session(vault: Path, session: str) -> bool:
    """텔레메트리 로그 tail 에서 이번 세션의 graphify 이벤트 유무.

    ⚠️ 로그 부재도 False 다 — 그건 "미사용" 이 아니라 "관측 불가" 이므로, 호출부는 반드시
    `_telemetry_observing()` 으로 두 경우를 갈라야 한다(안 그러면 근거 없이 차단한다).
    """
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
        # vault 를 먼저 해석한다 — 적용 판정(② 분기)이 텔레메트리 로그를 본다.
        vault = _vault_root(project)
        if not _graphify_applicable(project, vault):
            return 0

        tool = str(payload.get("tool_name") or "")
        ti = payload.get("tool_input") or {}
        is_grep = tool == "Grep"
        if is_grep and not _SYMBOLISH.match(str(ti.get("pattern") or "")):
            return 0  # 리터럴 grep 은 그래프가 답 못 함 → 침묵

        session = payload.get("session_id") or ""
        used = _graphify_used_this_session(vault, session) if vault else False
        if used:
            _emit_ctx(_GREP_NUDGE if is_grep else _NUDGE)  # 이미 썼으면 부드럽게
        elif not _telemetry_observing(vault):
            # 🔴 **관측 불가는 위반이 아니다.** 로그가 아예 없으면 graphify 사용 여부를 알 방법이
            #    없는데, 종전 코드는 그것을 "미사용" 으로 단정해 차단했다 — automode 에선 deny 라
            #    `dw_search` 가 **영영 열리지 않는다**(2026-08-07 실측: 서브에이전트가 이 게이트에
            #    막혀 vault 를 직접 뒤져 우회했다). 텔레메트리와 이 게이트는 같은 릴리스에 실렸지만
            #    훅은 새 세션부터 로드되므로 로그가 한 번도 안 써진 창이 **반드시** 생긴다.
            #    ⇒ 관측이 없으면 조언까지만. 규율은 전하되 근거 없이 막지 않는다.
            _emit_ctx(_GREP_NUDGE if is_grep else _NUDGE)
        else:
            _emit_gate(_ASK, _hard(payload))  # 관측 중인데 미사용 → 게이트(automode=deny, else ask)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
