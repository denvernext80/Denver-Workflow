#!/usr/bin/env python3
"""dw-vault-write-guard — PreToolUse 훅: OBEY 노트(rule/guidance/procedure) 직접편집 차단(ask).

문제: 에이전트가 dw_write_* 를 잘못 써 실패하면 파일을 직접 열어 Edit/Write 로 고치며 SSOT 를
우회한다. dw-vault-guard(PostToolUse)는 구조적으로 차단 불가(조언만) — 그래서 **PreToolUse** 에서
차단한다(worktree-guard 와 동일 패턴).

정책(사용자 비준 모델과 일치):
  - OBEY = rule/guidance/procedure  → 컴파일/사람비준 대상. 직접편집 **ask 로 차단**,
    올바른 경로(dw_propose_rule / dw_write_procedure / vault 에서 사람 편집)로 유도.
    ⚠️ ask 는 **금지가 아니라 사용자 결정 요청**이다. 사용자가 승인하면 편집은 그대로 진행된다.
    메시지 문구가 이 사실을 감추면 에이전트가 사용자 지시까지 거절한다(2026-08-07 실측).
    hard(automode 등)에서만 deny 로 상향돼 실제 차단이 된다.
  - LIVE = memory/contract/spec/decision/backlog/reference → 직접 쓰기 허용(통과).
  - vault 밖 코드 파일 → 통과.
OBEY 판정: 파일 존재 시 frontmatter `type`, 없으면(신규) 경로 프리픽스(governance/rules|guidance|procedures).

출력: PreToolUse permissionDecision(ask/allow) JSON. 결코 예외로 터지지 않는다(실패 시 allow).
표준 라이브러리만.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import dw_runtime

FM_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
OBEY = {"rule", "guidance", "procedure"}
OBEY_DIRS = ("governance/rules", "governance/guidance", "governance/procedures")
TOOL_HINT = {
    "rule": "dw_propose_rule 로 draft 규칙을 제안하라(stable 승격은 사람).",
    "procedure": "dw_write_procedure 로 draft 절차를 기록하라(비준되면 스킬로 로드).",
    # guidance 만 전용 dw_write_* 도구가 없다(rule=propose, procedure=write). 출구 없이 "금지" 로만
    # 끝내면 에이전트가 사용자의 명시적 지시까지 거절한다 — 2026-08-07 실제 발생(왕복 1회 낭비).
    # 승인 이야기는 여기 두지 마라 — TOOL_HINT 는 모드 무관이라 automode(승인자 부재)에서
    # "사용자 승인을 받아라 / (automode → 차단)" 이라는 자기모순 문구가 된다. 모드별 문구는 tail.
    "guidance": "guidance 는 전용 쓰기 도구가 없다 — 원칙은 사람이 vault 에서 저작한다.",
}


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


def _fm_type(path: Path):
    try:
        m = FM_RE.match(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not m:
        return None
    for line in m.group(1).splitlines():
        if line.startswith("type:"):
            return line.split(":", 1)[1].strip().strip("'\"")
    return None


# automode(무인 실행)에서는 ask 가 auto-approve 로 폴백돼 무력화된다 → deny 로 상향.
# 훅의 deny 는 bypassPermissions 에서도 항상 차단(훅이 권한모드보다 상위). Edit/Write 를 가드하므로
# 그것을 자동승인하는 acceptEdits 도 hard 로 취급. DW_GATE_HARD env 로 명시 오버라이드 가능.
_HARD_MODES = {"auto", "dontAsk", "bypassPermissions", "acceptEdits"}


def _hard(payload) -> bool:
    env = os.environ.get("DW_GATE_HARD", "").lower()
    if env in ("1", "deny", "hard", "true"):
        return True
    if env in ("0", "ask", "soft", "false"):
        return False
    return str(payload.get("permission_mode") or "") in _HARD_MODES


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # 파싱 실패 = 침묵(차단 안 함)
    try:
        if payload.get("hook_event_name") not in (None, "PreToolUse"):
            return 0
        ti = payload.get("tool_input") or {}
        fp = ti.get("file_path")
        if not fp or not str(fp).endswith(".md"):
            return 0
        project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())
        vault = _vault_root(project)
        if vault is None:
            return 0
        try:
            rel = Path(fp).resolve().relative_to(vault.resolve())
        except Exception:
            return 0  # vault 밖 = 통과
        rels = str(rel).replace("\\", "/")

        # OBEY 판정: type(있으면) 우선, 없으면 경로 프리픽스.
        p = Path(fp)
        ty = _fm_type(p) if p.exists() else None
        is_obey = (ty in OBEY) if ty else any(rels.startswith(d + "/") for d in OBEY_DIRS)
        if not is_obey:
            return 0  # LIVE·기타 = 통과(직접 쓰기 허용)

        kind = ty or next((d.split("/")[-1].rstrip("s") for d in OBEY_DIRS if rels.startswith(d + "/")), "rule")
        kind = {"rule": "rule", "guidance": "guidance", "procedure": "procedure",
                "guidanc": "guidance", "procedure ": "procedure"}.get(kind, kind)
        hint = TOOL_HINT.get(kind, "dw 쓰기 도구를 사용하라.")
        hard = _hard(payload)
        # soft 는 ask 다 — 최종 결정권자는 사용자다. 종전 문구("…override.")는 주체가 없어
        # 에이전트가 "나는 못 한다" 로 읽었다. 누가 푸는지 명시한다.
        tail = ("automode → 실제 차단. 승인자가 없으니 올바른 경로로 재시도하라." if hard
                else "ask 다 — 사용자가 승인하면 그대로 진행된다. 사용자 지시가 있었다면 "
                     "'못 한다' 가 아니라 '승인해 주시면 넣겠다' 로 요청하라.")
        reason = (f"🔒 SSOT 가드: '{rels}' 는 OBEY 노트({kind})다 — 직접편집은 컴파일·비준을 우회한다. "
                  f"{hint} ({tail})")
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny" if hard else "ask",
            "permissionDecisionReason": reason,
        }}, ensure_ascii=False))
    except Exception:
        return 0  # 어떤 실패도 차단으로 이어지지 않는다
    return 0


if __name__ == "__main__":
    sys.exit(main())
