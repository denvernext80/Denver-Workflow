#!/usr/bin/env python3
"""dw-vault MCP 자가 부트스트랩 런처 — 셸 비의존(순수 Python).

**왜 Python 인가**(2.14.0): 종전 런처는 `#!/bin/sh` POSIX 스크립트였다(`dirname`,
`CDPATH= cd`, `case` 글롭, `$HOME` 전개, `.venv/bin/` 하드코딩). plugin.json 의
`mcpServers.command` 는 셸을 경유하지 않고 **직접 spawn** 되므로, POSIX 셸이 없는 환경에서는
런처 자체가 실행되지 않고 dw-vault MCP 11 도구가 **아예 기동하지 않는다** — 플러그인 핵심이
죽는다. 서버 본체(`dw-mcp-server.py`)는 이미 이식 가능하다(POSIX 도구를 subprocess 로 부르는
곳 0 건).

⚠️ **주장 범위**: 이 파일이 없앤 것은 "POSIX 셸 의존"(구조적)이다. **Windows 실기 미검증** —
   판정 절차는 `docs/windows-smoke-checklist.md`. 전제(인터프리터 이름 해석 등)는 README
   「5. 플랫폼」 참조.

**기반 로직은 `dw_runtime.py` 가 정본**이다(2.15.0). vault 해석·venv 부트스트랩·`mcp<2` 핀을
CLI(`dw.py`)와 공유한다 — 사본을 늘리면 신규 venv 에서만 발현하는 조용한 불일치가 난다.
이 파일에 남은 책임은 셋뿐이다:
  1. ROOT 확정 — `CLAUDE_PLUGIN_ROOT`(env) > 이 파일의 상위 디렉터리.
  2. 부트스트랩된 venv 인터프리터 확보.
  3. 서버 기동 — `dw-mcp-server.py --vault <vault>`.

**stdout 은 JSON-RPC 채널이다.** 부트스트랩(venv/pip) 출력이 stdout 으로 한 줄이라도 새면
클라이언트의 프로토콜 파싱이 깨진다 — `dw_runtime.run_quiet` 가 그것을 막는다.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import dw_runtime


def launch(py: Path, server: Path, vault: Path, os_name: str = os.name,
           execv=os.execv, run=subprocess.run) -> int:
    """서버 프로세스로 넘긴다. POSIX 는 `execv`, Windows 는 자식 + 종료코드 전달.

    근거: Windows 의 `os.execv` 는 프로세스를 **교체하지 않는다** — 새 프로세스를 만들고
    원래 PID 를 종료시킨다. MCP 클라이언트는 자기가 spawn 한 PID 를 붙들고 있으므로 그
    종료를 "서버가 죽었다" 로 읽는다(stdio 파이프도 그 시점에 오해될 수 있다). 그래서
    Windows 만 자식 프로세스로 돌리고 종료코드를 전달한다.
    POSIX 는 종전 `.sh` 와 **동일한** exec 의미를 유지한다 — 실기로 검증 가능한 플랫폼의
    동작을 바꾸지 않는 쪽이 회귀 위험이 낮다.
    """
    argv = [str(py), str(server), "--vault", str(vault)]
    if os_name == "nt":
        return run(argv).returncode
    execv(str(py), argv)
    return 0  # execv 성공 시 도달 불가


def main(argv: list[str] | None = None, env: dict | None = None) -> int:
    env = os.environ if env is None else env
    root = dw_runtime.plugin_root(env, fallback=Path(__file__).resolve().parent.parent)

    vault = dw_runtime.resolve_vault(env)
    py = dw_runtime.ensure_venv(root / ".venv")
    server = root / "_build" / "dw-mcp-server.py"
    if not server.exists():
        print(f"denver-workflow: MCP 서버 없음 ({server}) — 플러그인 설치가 깨졌다.",
              file=sys.stderr)
        return 1
    return launch(py, server, vault)


if __name__ == "__main__":  # 임포트(자기검사)로는 부트스트랩·exec 가 일어나지 않는다
    sys.exit(main())
