#!/usr/bin/env python3
"""dw MCP 재사용 계측 — 비파괴 append-only 접근 로거.

dw_read / dw_search 호출을 <vault>/.dw-state/access.jsonl 에 한 줄(JSON)씩 기록한다.
목적: "실제로 pull 되는 절차·memory" 를 데이터로 관측해, 쓰기 전용으로만 쌓이는
노트(archive 후보)를 orphan(위키링크) 추정이 아니라 실측으로 식별하기 위함.

설계 원칙(중요):
- 계측은 결코 본 기능을 막지 않는다 — 모든 예외를 삼키는 best-effort.
- vault 의 CONTENT_DIRS 밖(.dw-state/)에 기록 → 검색·graphify 그래프를 오염시키지 않는다.
- 표준 라이브러리만 사용(외부 의존 0).
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path


def _state_dir(vault: Path) -> Path:
    d = Path(vault) / ".dw-state"
    d.mkdir(exist_ok=True)
    return d


def log_access(tool: str, name: str, vault, *, resolved=None, surfaced=None) -> None:
    """접근 1건을 <vault>/.dw-state/access.jsonl 에 append.

    tool: "dw_read" | "dw_search"
    name: 호출 인자(read=요청 name, search=query)
    resolved: dw_read 가 실제로 연 노트의 vault 상대경로(못 찾으면 None)
    surfaced: dw_search 가 돌려준 후보 경로 리스트
    실패 시 조용히 무시한다(호출자 보호).
    """
    try:
        rec = {
            "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "tool": tool,
            "name": name,
            "pid": os.getpid(),
        }
        if resolved is not None:
            rec["resolved"] = resolved
        if surfaced is not None:
            rec["surfaced"] = surfaced
        line = json.dumps(rec, ensure_ascii=False)
        with open(_state_dir(Path(vault)) / "access.jsonl", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass  # 계측은 결코 MCP 호출을 깨지 않는다
