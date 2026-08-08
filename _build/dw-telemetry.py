#!/usr/bin/env python3
"""dw 워크플로우 텔레메트리 — 비파괴 PostToolUse 훅.

의도한 규율 대비 '실제 도구 사용 분포'를 관측한다. 서버를 건드리지 않고 훅 레이어에서
모든 관련 도구 호출을 <vault>/.dw-state/access.jsonl 에 한 줄(JSON)씩 남긴다.

측정 목표(진단에서 나온 두 가설):
  1) graphify-우선 규율이 실제로 지켜지나 — graphify vs dw_search vs Grep 분포.
  2) 쓰기가 dw_write 로만 되나 — dw_write_* vs vault 파일 직접 Edit/Write(bypass).
  3) 읽기가 dw_read 로 되나 — dw_read vs vault 파일 직접 Read(bypass).
  + 절차·memory 재사용(read 0회 = archive 후보) 실측.

설계 원칙: 계측은 결코 도구 호출을 막지 않는다(항상 exit 0, 모든 예외 삼킴).
vault CONTENT_DIRS 밖(.dw-state/)에만 기록. 표준 라이브러리만.

Claude Code PostToolUse 훅으로 배선(matcher 는 아래 도구들을 포함하도록). stdin=훅 payload JSON.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path

import dw_runtime


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


def _classify(tool: str, ti: dict):
    """(kind, sub, target) 반환. kind: vault|graphify|grep|file|other."""
    low = tool.lower()
    if "dw-vault__" in tool or (tool.startswith("dw_")):
        sub = tool.split("dw-vault__")[-1] if "dw-vault__" in tool else tool
        target = ti.get("name") or ti.get("query") or ti.get("title") or ti.get("note_type") or ""
        return "vault", sub, target
    if "graphify" in low:
        sub = tool.split("__")[-1]
        target = ti.get("query") or ti.get("node") or ti.get("symbol") or ti.get("start") or ""
        return "graphify", sub, str(target)[:120]
    if tool == "Grep":
        return "grep", "Grep", ti.get("pattern", "")
    if tool in ("Read", "Edit", "Write", "MultiEdit"):
        return "file", tool, ti.get("file_path", "")
    return "other", tool, ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        tool = payload.get("tool_name") or ""
        ti = payload.get("tool_input") or {}
        kind, sub, target = _classify(tool, ti)
        if kind == "other":
            return 0

        project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())
        vault = _vault_root(project)
        if vault is None:
            return 0
        vroot = vault.resolve()

        inside_vault = None
        resolved = None
        if kind == "file" and target:
            try:
                rel = Path(target).resolve().relative_to(vroot)
                inside_vault = True
                resolved = str(rel)
            except Exception:
                inside_vault = False
            # vault 밖 코드 파일 Read/Edit 는 노이즈 → 기록하지 않는다(Grep 은 코드탐색이라 유지).
            if not inside_vault:
                return 0

        rec = {
            "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "session": payload.get("session_id") or "",
            "kind": kind,
            "tool": sub,
            "target": str(target)[:200],
        }
        if resolved is not None:
            rec["resolved"] = resolved
        d = vroot / ".dw-state"
        d.mkdir(exist_ok=True)
        with open(d / "access.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
