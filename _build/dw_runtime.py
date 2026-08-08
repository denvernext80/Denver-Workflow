#!/usr/bin/env python3
"""런처·CLI 가 공유하는 런타임 기반 — vault 경로 해석 + venv 자가 부트스트랩.

**왜 별 모듈인가**: 이 기반 로직의 소비자가 셋이다 —
  1. `dw-mcp-launch.py` (dw-vault MCP 런처, CC 가 직접 spawn)
  2. `dw.py` (이식 가능 CLI, 슬래시 커맨드가 호출)
  3. `Makefile` (개발자 인터페이스 — 위 CLI 에 위임하므로 자기 사본을 갖지 않는다)

2.14.0 시점엔 `mcp<2` 핀이 `Makefile` 과 런처 **두 곳**에 리터럴로 있었다(CHANGELOG 에 그
이중화를 명시했다). CLI 까지 세 번째 사본을 만들면 신규 venv 에서만 발현하는 조용한 불일치가
난다 — 그래서 **핀·venv 레이아웃·vault 해석의 정본을 이 파일 하나로 모았다**.
`_build/dw-selftest.py` 가 "핀 리터럴이 Makefile·런처에 재등장하지 않는다" 를 검사한다.

파일명에 하이픈이 없는 이유: `import dw_runtime` 로 임포트되기 때문이다(`dw_state.py`·
`dw_verify.py` 와 같은 규약). 스크립트 실행 시 `sys.path[0]` 이 스크립트 디렉터리라 `_build/`
안의 형제 모듈은 그대로 임포트된다.

표준 라이브러리만 사용한다 — 이 모듈이 pyyaml·mcp 를 설치하는 주체이므로, 스스로 그것들에
의존할 수 없다.
"""
from __future__ import annotations

import os
import subprocess
import sys
import sysconfig
from pathlib import Path

# ── venv 의존성 핀 (정본 — 여기 한 곳) ────────────────────────────────────────────
# mcp<2 핀: 2.0.0 은 `mcp.server.fastmcp` 를 제거해 dw-mcp-server.py 가 임포트에서 즉사한다
# (신규 venv 에서만 발현 — 기존 venv 는 1.x 를 들고 있어 무증상). 서버를 2.x API 로
# 마이그레이션한 뒤에만 핀을 풀어라.
DEPS = ("pyyaml", "mcp<2")

CONVENTIONAL_VAULT = "denver-workflow-vault"


# ── 홈·루트 ───────────────────────────────────────────────────────────────────────

def home_dir(env: dict | None = None) -> str:
    """사용자 홈. Windows 는 HOME 이 비어 있고 USERPROFILE 만 있는 경우가 흔하다."""
    env = os.environ if env is None else env
    return env.get("HOME") or env.get("USERPROFILE") or str(Path.home())


def plugin_root(env: dict | None = None, fallback: Path | None = None) -> Path:
    """플러그인/도구 루트 — `CLAUDE_PLUGIN_ROOT`(env) > 호출자가 준 폴백(보통 `<file>/..`)."""
    env = os.environ if env is None else env
    return Path(env.get("CLAUDE_PLUGIN_ROOT") or (fallback or Path.cwd()))


# ── vault 경로 해석 (순수 함수 — 홈을 주입해 테스트로 고정) ────────────────────────

def expand_home_prefix(value: str, home: str) -> str:
    """리터럴 `~/`·`$HOME/` 접두만 확장한다(종전 `.sh` 런처의 `case` 글롭과 동일 범위).

    `os.path.expanduser`/`expandvars` 를 쓰지 않는 이유: 저 둘은 경로 **중간**의 `~`·`$VAR`
    까지 건드려 종전 동작보다 넓다. 여기서 필요한 건 "settings.json env 값이 홈 기반으로
    적힐 수 있다" 는 한 가지 규약뿐이다 — 범위를 늘리면 공백·`$` 가 든 실제 경로를 잘못
    변형할 수 있다.
    """
    for prefix in ("~/", "$HOME/"):
        if value.startswith(prefix):
            return str(Path(home) / value[len(prefix):])
    return value


def vault_target(env: dict | None = None, home: str | None = None) -> Path:
    """vault 가 **있어야 할** 경로 — 존재를 요구하지 않는다.

    `scaffold-vault`(아직 없는 vault 를 만드는 일)처럼 "어디에 만들까" 만 필요한 경로용.
    """
    env = os.environ if env is None else env
    home = home_dir(env) if home is None else home
    raw = (env.get("DW_VAULT_DIR") or "").strip()
    return Path(expand_home_prefix(raw, home)) if raw else Path(home) / CONVENTIONAL_VAULT


def resolve_vault(env: dict | None = None, home: str | None = None, warn=None) -> Path:
    """vault 위치 해석: `DW_VAULT_DIR`(env) > `~/<규약>` > **에러**. 플러그인 루트 폴백 없음.

    실패는 `SystemExit(1)` — vault 없이 뜬 서버·CLI 는 조용히 빈 지식으로 답하므로
    (조용한 실패), 기동을 거부하는 쪽이 옳다.
    """
    env = os.environ if env is None else env
    home = home_dir(env) if home is None else home
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
        "'/dw-setup' 으로 준비하거나 DW_VAULT_DIR 를 설정하세요."
    )
    raise SystemExit(1)


# ── venv 레이아웃·부트스트랩 ───────────────────────────────────────────────────────

def venv_python(venv: Path, os_name: str = os.name) -> Path:
    """venv 인터프리터 경로. `Scripts/python.exe`(nt) vs `bin/python`(posix).

    근거 — 왜 `sysconfig` 이고 왜 그 위에 `os_name` 인가:
      * 스크립트 디렉터리(`Scripts` vs `bin`)는 CPython 의 `venv/__init__.py` 가 스스로
        `sysconfig.get_path(name, scheme='venv', vars=vars)` 로 얻는다(1차 출처: 로컬
        3.14.6 `venv/__init__.py:107`). 그래서 문자열 조립 대신 같은 표준 API 를 쓴다.
      * 단 `scheme='venv'` 는 **돌고 있는** 인터프리터의 플랫폼으로 해석된다(macOS 에서
        `/X/bin`). 크로스플랫폼 분기에 쓸 수 없고 테스트로 주입할 수도 없다. 그래서
        `nt_venv`/`posix_venv` 를 **명시**해 주입 가능하게 만든다.
      * 실행 파일 이름의 `.exe` 접미는 `os_name` 으로 정한다. `sysconfig.get_config_var("EXE")`
        는 **돌고 있는** 인터프리터를 기술하므로 대상 venv 의 접미를 말해주지 않는다.
      * `nt_venv`/`posix_venv` 스킴 이름은 3.11+ 에서만 존재한다. 실측: 이 워크스테이션의
        `/usr/bin/python3` 는 3.9.6 이고 두 이름 모두 `KeyError` 다 — 배선이
        `command: "python3"` 이라 **CC 가 해석한 아무 python3** 이 이 파일을 임포트하므로
        폴백은 가정이 아니라 살아있는 경로다. CPython 과 동일한 리터럴로 폴백한다.
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


def run_quiet(cmd: list[str], what: str) -> None:
    """자식을 돌리고 stdout 오염을 원천 차단한다. 실패는 **시끄럽게** 죽는다.

    stdout 오염이 치명적인 이유: MCP 런처의 stdout 은 JSON-RPC 채널이다(한 줄만 새도 클라이언트
    파싱이 깨진다). 그래서 성공 시엔 아무것도 내지 않고, 실패 시에만 stderr 로 전문을 낸다.
    종전 `.sh` 런처는 `set -e` 로 컨텍스트 없이 죽었다 — Debian 계열의 `python3-venv` 별도
    패키지처럼 흔한 원인이 진단 없이 사라졌다.
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


def ensure_venv(venv: Path, os_name: str = os.name, run=run_quiet, notify=None) -> Path:
    """`<루트>/.venv` 를 보장하고 그 인터프리터 경로를 돌려준다(있으면 재사용 — 멱등).

    플러그인은 GitHub 에서 설치돼 `.venv` 가 없다(gitignored). 그래서 첫 실행이 곧 부트스트랩.
    venv 생성은 `sys.executable` 로 한다 — `python3` 이름을 다시 찾지 않아야 한다(이 프로세스를
    띄운 그 인터프리터가 정답이고, 이름 해석은 플랫폼마다 다르다).

    notify: 첫 실행 안내를 낼 함수(기본 stderr). MCP 런처는 stdout 을 쓸 수 없으므로 기본이
    stderr 다 — CLI 는 stdout 으로 바꿔 넘긴다.
    """
    notify = notify or (lambda msg: print(msg, file=sys.stderr))
    py = venv_python(venv, os_name)
    if py.exists():
        return py
    notify("denver-workflow: 첫 실행 — venv 부트스트랩(pyyaml + mcp) 중…")
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
