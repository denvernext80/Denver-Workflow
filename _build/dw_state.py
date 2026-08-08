#!/usr/bin/env python3
"""dw 엔진 상태 — 스캔·설치 대상 프로젝트 레지스트리의 **단일 정본**.

`<vault>/.dw-state/projects.json` = "이 vault 가 지배하는 레포" 목록.
`make install-project`(wire-hook.py)가 설치 시 등록하고, dw-ratify(검사 스캔)와
dw-install-registered(설치 전파)가 읽는다. 소비자가 셋이라 계약을 여기 한 곳에 둔다.

위치 규약: vault CONTENT_DIRS **밖**(.dw-state/) — 검색·graphify·컴파일을 오염시키지 않는다
(dw_access_log.py 와 동일 규약). 표준 라이브러리만 사용.
"""
from __future__ import annotations

import json
from pathlib import Path

STATE_DIR = ".dw-state"
PROJECTS_JSON = "projects.json"


def registry_path(vault: Path) -> Path:
    return Path(vault) / STATE_DIR / PROJECTS_JSON


def read_registry(vault: Path) -> list[str]:
    """**원문** 등록 항목(존재하지 않는 경로도 그대로). 사라진 등록을 감지해야 하는
    호출자는 이걸 쓴다 — registered_projects() 는 그것들을 걸러내므로 구분이 사라진다."""
    f = registry_path(vault)
    if not f.is_file():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [str(x) for x in (data.get("projects") or [])]


def registered_projects(vault: Path) -> list[Path]:
    """실재하는 디렉터리만 절대경로로. 스캔·설치 대상."""
    out = []
    for s in read_registry(vault):
        p = Path(s).expanduser()
        if p.is_dir():
            out.append(p.resolve())
    return out


def register_project(vault: Path, project: Path, remove: bool = False) -> str:
    """프로젝트를 멱등 등록/해제하고 사람이 읽을 결과 문자열을 돌려준다.

    실패해도 호출자(설치)를 막지 않는다 — 다만 **조용히 넘기지 않고** 사유를 돌려준다.
    """
    f = registry_path(vault)
    target = str(Path(project).expanduser().resolve())
    try:
        cur = read_registry(vault)
        new = sorted(set(cur) - {target}) if remove else sorted(set(cur) | {target})
        if new == sorted(set(cur)):
            return f"레지스트리 변화 없음(멱등): {f}"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"projects": new}, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
        verb = "등록 해제" if remove else "등록"
        return f"비준 스캔·설치 대상 {verb}: {target} → {f} (총 {len(new)}개)"
    except (OSError, json.JSONDecodeError) as e:
        return (f"⚠️ 레지스트리 등록 실패({type(e).__name__}: {e}) — "
                f"dw-ratify 가 이 레포를 스캔·설치하지 못한다")
