#!/usr/bin/env python3
"""dw-vault MCP 자가 부트스트랩 런처 — 셸 비의존(순수 Python).

**왜 Python 인가**(2026-08-08): 종전 런처는 `#!/bin/sh` POSIX 스크립트였다(`dirname`,
`CDPATH= cd`, `case` 글롭, `$HOME` 전개, `.venv/bin/` 하드코딩). plugin.json 의
`mcpServers.command` 는 셸을 경유하지 않고 **직접 spawn** 되므로, POSIX 셸이 없는 환경에서는
런처 자체가 실행되지 않고 dw-vault MCP 11 도구가 **아예 기동하지 않는다** — 플러그인 핵심이
죽는다. 서버 본체(`dw-mcp-server.py`)는 이미 이식 가능하다(POSIX 도구를 subprocess 로 부르는
곳 0건 — 2026-08-08 전수 확인). 따라서 셸 의존은 이 런처 한 파일에만 남아 있었다.

⚠️ **주장 범위**: 이 파일이 없앤 것은 "POSIX 셸 의존"(구조적)이다. **Windows 실기 미검증** —
   판정 절차는 `docs/windows-smoke-checklist.md`. 전제(인터프리터 이름 해석 등)는 README
   「5. Windows 전제 및 미검증 범위」 참조.

책임(종전 `.sh` 와 동일 — 동작 변경 없음):
  1. ROOT 확정 — `CLAUDE_PLUGIN_ROOT`(env) > 이 파일의 상위 디렉터리.
  2. vault 해석 — `DW_VAULT_DIR`(env) > `~/denver-workflow-vault`(규약) > 에러. **폴백 없음**.
     `DW_VAULT_DIR` 의 리터럴 `~/`·`$HOME/` 접두는 확장한다(settings.json env 규약).
  3. venv 자가 부트스트랩 — `ROOT/.venv` 가 없으면 만들고 `pyyaml` + `mcp<2` 설치(멱등).
  4. 서버 기동 — venv python 으로 `dw-mcp-server.py --vault <vault>`.

**stdout 은 JSON-RPC 채널이다.** 부트스트랩(venv/pip) 출력이 stdout 으로 한 줄이라도 새면
클라이언트의 프로토콜 파싱이 깨진다. 그래서 자식 출력은 전부 캡처하고, **실패 시에만** stderr
로 전문을 흘린다(종전 `.sh` 는 `>&2` 리다이렉트로 같은 목적을 달성했다).
"""
from __future__ import annotations

import os
import subprocess
import sys
import sysconfig
from pathlib import Path

# mcp<2 핀 — 2.0.0 은 `mcp.server.fastmcp` 를 제거해 서버가 임포트에서 즉사한다.
# ⚠️ Makefile 의 `$(VENV)/.stamp` 레시피와 **반드시 동일하게 유지**. 서버를 2.x API 로
#    마이그레이션한 뒤에만 핀을 풀어라.
DEPS = ("pyyaml", "mcp<2")

CONVENTIONAL_VAULT = "denver-workflow-vault"


# ── 경로 해석 (순수 함수 — 플랫폼/홈을 주입해 양쪽 분기를 단위 테스트로 고정) ──────────────

def expand_home_prefix(value: str, home: str) -> str:
    """리터럴 `~/`·`$HOME/` 접두만 확장한다(종전 `.sh` 의 `case` 글롭과 동일 범위).

    `os.path.expanduser`/`expandvars` 를 쓰지 않는 이유: 저 둘은 경로 **중간**의 `~`·`$VAR`
    까지 건드려 종전 동작보다 넓다. 여기서 필요한 건 "settings.json env 값이 홈 기반으로
    적힐 수 있다" 는 한 가지 규약뿐이다(spec §3) — 범위를 늘리면 공백·`$` 가 든 실제 경로를
    잘못 변형할 수 있다.
    """
    for prefix in ("~/", "$HOME/"):
        if value.startswith(prefix):
            return str(Path(home) / value[len(prefix):])
    return value


def resolve_vault(env: dict, home: str, warn=None) -> Path:
    """vault 위치 해석: `DW_VAULT_DIR`(env) > `~/<규약>` > 에러. 플러그인 루트 폴백 **없음**.

    반환 실패는 `SystemExit(1)` — vault 없이 뜬 서버는 조용히 빈 지식으로 답하므로
    (조용한 실패), 기동을 거부하는 쪽이 옳다.
    """
    warn = warn or (lambda msg: print(msg, file=sys.stderr))
    conventional = Path(home) / CONVENTIONAL_VAULT

    raw = (env.get("DW_VAULT_DIR") or "").strip()
    if raw:
        candidate = Path(expand_home_prefix(raw, home))
        if candidate.is_dir():
            return candidate
        warn(f"denver-workflow: DW_VAULT_DIR='{candidate}' 폴더 없음 — 규약 경로 시도")

    if conventional.is_dir():
        return conventional

    warn(
        f"denver-workflow: vault 없음 ({conventional}). "
        "'make scaffold-vault' 로 생성하거나 DW_VAULT_DIR 설정."
    )
    raise SystemExit(1)


def venv_python(venv: Path, os_name: str = os.name) -> Path:
    """venv 인터프리터 경로. `Scripts/python.exe`(nt) vs `bin/python`(posix).

    근거 — 왜 `sysconfig` 이고 왜 그 위에 `os_name` 인가:
      * 스크립트 디렉터리(`Scripts` vs `bin`)는 CPython 의 `venv/__init__.py` 가 스스로
        `sysconfig.get_path(name, scheme='venv', vars=...)` 로 얻는다(1차 출처: 로컬
        3.14.6 `venv/__init__.py:107`). 그래서 문자열 조립 대신 같은 표준 API 를 쓴다.
      * 단 `scheme='venv'` 는 **돌고 있는** 인터프리터의 플랫폼으로 해석된다(macOS 에서
        `/X/bin`). 크로스플랫폼 분기에 쓸 수 없고 테스트로 주입할 수도 없다. 그래서
        `nt_venv`/`posix_venv` 를 **명시**해 주입 가능하게 만든다(둘 다 실측 확인:
        `nt_venv → /X/Scripts`, `posix_venv → /X/bin`).
      * 실행 파일 이름의 `.exe` 접미는 `os_name` 으로 정한다. `sysconfig.get_config_var("EXE")`
        는 **돌고 있는** 인터프리터를 기술하므로(macOS 에서 `''`) 대상 venv 의 접미를
        말해주지 않는다.
      * `nt_venv`/`posix_venv` 스킴 이름은 3.11+ 에서만 존재한다(3.10 이하엔 `venv` 스킴
        자체가 없다). 파이썬 하한을 문서화하지 않은 플러그인이라 `KeyError` 시 CPython 과
        동일한 리터럴(`Scripts`/`bin`)로 폴백한다.
    """
    scheme = "nt_venv" if os_name == "nt" else "posix_venv"
    base = str(venv)
    try:
        scripts = Path(sysconfig.get_path("scripts", scheme=scheme, vars={
            "base": base, "platbase": base,
            "installed_base": base, "installed_platbase": base,
        }))
    except KeyError:  # py<3.11 — CPython venv 와 동일한 리터럴 레이아웃
        scripts = venv / ("Scripts" if os_name == "nt" else "bin")
    return scripts / ("python.exe" if os_name == "nt" else "python")


# ── venv 부트스트랩 ────────────────────────────────────────────────────────────────

def _run_quiet(cmd: list[str], what: str) -> None:
    """자식을 돌리고 stdout 오염을 원천 차단한다. 실패는 **시끄럽게** 죽는다.

    종전 `.sh` 는 `set -e` + `>&2` 였다. `python3 -m venv` 실패(예: Debian 계열에서
    `python3-venv` 미설치)가 컨텍스트 없는 종료로 끝나던 자리라, 여기서는 원인 지목까지 한다.
    """
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as exc:
        print(f"denver-workflow: {what} 실행 불가 — {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    if proc.returncode != 0:
        print(f"denver-workflow: {what} 실패(exit={proc.returncode}) — 명령: {' '.join(cmd)}",
              file=sys.stderr)
        for stream in (proc.stdout, proc.stderr):
            if stream and stream.strip():
                print(stream.rstrip(), file=sys.stderr)
        print("denver-workflow: venv 생성이 막히면 파이썬의 venv 모듈부터 확인하라 "
              "(Debian/Ubuntu 계열은 'python3-venv' 가 별도 패키지, "
              "Windows 는 python3 이름 해석 — README 「Windows 전제」 참조).",
              file=sys.stderr)
        raise SystemExit(1)


def ensure_venv(venv: Path, os_name: str = os.name, run=_run_quiet) -> Path:
    """`ROOT/.venv` 를 보장하고 그 인터프리터 경로를 돌려준다(있으면 재사용 — 멱등).

    플러그인은 GitHub 에서 설치돼 `.venv` 가 없다(gitignored). 그래서 첫 실행이 곧 부트스트랩.
    venv 생성은 `sys.executable` 로 한다 — `python3` 이름을 다시 찾지 않아야 한다
    (이 프로세스를 띄운 그 인터프리터가 정답이고, 이름 해석은 플랫폼마다 다르다).
    """
    py = venv_python(venv, os_name)
    if py.exists():
        return py
    print("denver-workflow: 첫 실행 — venv 부트스트랩(pyyaml + mcp) 중…", file=sys.stderr)
    run([sys.executable, "-m", "venv", str(venv)], "venv 생성")
    py = venv_python(venv, os_name)
    if not py.exists():
        print(f"denver-workflow: venv 를 만들었는데 인터프리터가 없다 ({py}) — 레이아웃 불일치.",
              file=sys.stderr)
        raise SystemExit(1)
    # pip 실행은 `<venv>/bin/pip` 대신 `python -m pip` — 스크립트 이름(`pip` vs `pip.exe`)
    # 분기를 하나 지운다.
    run([str(py), "-m", "pip", "install", "--quiet", "--upgrade", "pip"], "pip 업그레이드")
    run([str(py), "-m", "pip", "install", "--quiet", *DEPS], "의존성 설치(pyyaml, mcp<2)")
    return py


# ── 서버 기동 ─────────────────────────────────────────────────────────────────────

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
    root = Path(env.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parent.parent)
    home = env.get("HOME") or env.get("USERPROFILE") or str(Path.home())

    vault = resolve_vault(env, home)
    py = ensure_venv(root / ".venv")
    server = root / "_build" / "dw-mcp-server.py"
    if not server.exists():
        print(f"denver-workflow: MCP 서버 없음 ({server}) — 플러그인 설치가 깨졌다.",
              file=sys.stderr)
        return 1
    return launch(py, server, vault)


if __name__ == "__main__":  # 임포트(자기검사)로는 부트스트랩·exec 가 일어나지 않는다
    sys.exit(main())
