#!/usr/bin/env python3
"""런처·CLI·훅이 공유하는 런타임 기반 — vault 경로 해석 + venv 자가 부트스트랩.

**왜 별 모듈인가**: 이 기반 로직의 소비자가 많다 —
  1. `dw-mcp-launch.py` (dw-vault MCP 런처, CC 가 직접 spawn)
  2. `dw.py` (이식 가능 CLI, 슬래시 커맨드가 호출)
  3. `Makefile` (개발자 인터페이스 — 위 CLI 에 위임하므로 자기 사본을 갖지 않는다)
  4. 훅 6 개(`dw-doctor`·`dw-vault-guard`·`dw-artifact-guard`·`dw-telemetry`·
     `dw-graphify-gate`·`dw-vault-write-guard`·`dw-ratify-session`) + `dw-graphify-register`

2.14.0 시점엔 `mcp<2` 핀이 `Makefile` 과 런처 **두 곳**에 리터럴로 있었다(CHANGELOG 에 그
이중화를 명시했다). CLI 까지 세 번째 사본을 만들면 신규 venv 에서만 발현하는 조용한 불일치가
난다 — 그래서 **핀·venv 레이아웃·vault 해석의 정본을 이 파일 하나로 모았다**.
`_build/dw-selftest.py` 가 "핀 리터럴·vault 해석이 다른 파일에 재등장하지 않는다" 를 검사한다.

2.16.0 에서 vault 해석 **11 곳**을 여기로 모았다. 그것들은 복제가 아니라 **시맨틱이 갈려 있었다**
(우선순위 2 종·확장 규칙 3 종·존재 요구 4 종) — 매트릭스는 CHANGELOG 참조. 통합 원칙:
  * **우선순위 정본**: `DW_VAULT_DIR`(env) > `<project>/.claude/dw-config.json` 의 `vault_root`
    > 규약 `<home>/denver-workflow-vault`. env 가 머신 전역 단일 답이고, config 는 env 를 못 받는
    컨텍스트의 마지막 안전망이다(규약 경로가 없는 머신에선 그것뿐이다).
  * **차이는 파라미터로 보존**한다(존재 요구 `require`, 조상 탐색 `ancestors`, git 본체 레포 탐색
    `git_probe`, 자기 레포 폴백 `self_repo_fallback`). "일관성" 을 이유로 호출자의 관측 동작을
    조용히 바꾸지 않는다.
  * **출처가 갈리면 드러낸다** — `vault_conflict_note()`. 결정론적으로 하나를 고르는 것만으로는
    "vault 는 하나" 를 보증하지 못한다(두 곳을 가리키는 상태가 오류 없이 지나간다).

파일명에 하이픈이 없는 이유: `import dw_runtime` 로 임포트되기 때문이다(`dw_state.py`·
`dw_verify.py` 와 같은 규약). 스크립트 실행 시 `sys.path[0]` 이 스크립트 디렉터리라 `_build/`
안의 형제 모듈은 그대로 임포트된다.

표준 라이브러리만 사용한다 — 이 모듈이 pyyaml·mcp 를 설치하는 주체이므로, 스스로 그것들에
의존할 수 없다. **`subprocess` 는 함수 안에서 임포트한다** — 이 모듈은 SessionStart/PostToolUse
훅 경로(timeout 10~15s)에서 임포트되고, `subprocess` 는 3.9.6 에서 임포트 비용 8.6ms 로 이
모듈 전체 비용의 대부분이었다. `dw-selftest.py` 가 그 부재를 불변식으로 고정한다.
"""
from __future__ import annotations

import collections
import os
import sys
import sysconfig                      # 테스트가 `mod.sysconfig` 를 패치한다 — 모듈 속성 유지
from pathlib import Path

# ── venv 의존성 핀 (정본 — 여기 한 곳) ────────────────────────────────────────────
# mcp<2 핀: 2.0.0 은 `mcp.server.fastmcp` 를 제거해 dw-mcp-server.py 가 임포트에서 즉사한다
# (신규 venv 에서만 발현 — 기존 venv 는 1.x 를 들고 있어 무증상). 서버를 2.x API 로
# 마이그레이션한 뒤에만 핀을 풀어라.
DEPS = ("pyyaml", "mcp<2")

CONVENTIONAL_VAULT = "denver-workflow-vault"

# 설치가 프로젝트에 남기는 vault 포인터(wire-hook.py 가 쓴다).
CONFIG_REL = (".claude", "dw-config.json")
CONFIG_KEY = "vault_root"
VAULT_ENV = "DW_VAULT_DIR"
PROJECT_ENV = "CLAUDE_PROJECT_DIR"


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

# 리터럴 홈 접두 — settings.json 의 `env` 값이나 dw-config.json 에 홈 기반으로 적힐 수 있다.
# `%USERPROFILE%` 가 **명시 목록에 있는 이유**: `os.path.expandvars` 는 posix 에서 `%VAR%` 를
# 모른다(실측 3.9.6·3.14.6 — `posixpath.expandvars('%USERPROFILE%/v')` 는 원문 그대로).
# 종전 doctor·가드 5 개가 `expandvars` 로 그것을 처리한다고 **주석에 적었지만 Windows 에서만
# 참**이었다. 여기서 접두를 명시하면 두 플랫폼에서 같은 답이 나온다.
HOME_PREFIXES = ("~/", "~\\", "$HOME/", "$HOME\\", "%USERPROFILE%/", "%USERPROFILE%\\")


def expand_home_prefix(value: str, home: str) -> str:
    """리터럴 홈 **접두만** 확장한다(`~/`·`$HOME/`·`%USERPROFILE%\\` + 각 구분자 변형).

    `os.path.expanduser`/`expandvars` 를 쓰지 않는 이유: 저 둘은 경로 **중간**의 `~`·`$VAR`
    까지 건드린다 — 범위를 늘리면 공백·`$` 가 든 실제 경로를 잘못 변형한다(미정의 `$VAR` 는
    빈 문자열로 지워져 **엉뚱한 존재하는 경로**가 되기도 한다: `make` 의 종전 `eval echo` 가
    `/x/$NOPE/v` 를 `/x//v` 로 만들었다). 여기서 필요한 건 "홈 기반으로 적힐 수 있다" 는
    한 가지 규약뿐이다.
    """
    value = value.strip()
    for prefix in HOME_PREFIXES:
        if value.startswith(prefix):
            return str(Path(home) / value[len(prefix):])
    return value


class VaultSource(collections.namedtuple("VaultSource", "name origin raw path")):
    """vault 위치를 **선언한** 출처 하나.

    필드: `name`("env"|"config") · `origin`(사람이 읽는 출처 — env 변수명 또는 config 절대경로)
    · `raw`(확장 전 원문) · `path`(홈 접두를 확장한 값 — 존재 여부는 무관).

    `typing.NamedTuple` 을 쓰지 않는 이유: `typing` 임포트가 3.9.6 에서 1.3ms 이고 이 모듈은
    훅 경로에서 임포트된다. `collections` 는 `json`/`pathlib` 가 이미 끌어온다(실측 — 비용 0).
    """
    __slots__ = ()


def project_dir(env: dict | None = None, fallback: Path | None = None) -> Path | None:
    """작업 중인 프로젝트 — `CLAUDE_PROJECT_DIR`(env) > 호출자가 준 폴백 > None.

    **cwd 를 몰래 쓰지 않는다.** 이 모듈의 vault 해석은 전부 주입된 `env` 로만 결정돼야
    테스트가 밀폐된다(실측: cwd 폴백을 넣으면 자기검사가 개발 머신의 실제 `.claude/
    dw-config.json` 을 읽어 실물 vault 를 잡는다 — 픽스처 격리가 조용히 깨진다).
    cwd 를 쓰고 싶은 호출자는 `project=Path.cwd()` 를 **명시**한다.
    """
    env = os.environ if env is None else env
    raw = (env.get(PROJECT_ENV) or "").strip()
    if raw:
        return Path(raw)
    return fallback


def config_dirs(project: Path | None, ancestors: int = 8, git_probe: bool = False) -> list[Path]:
    """`dw-config.json` 을 찾을 후보 디렉터리 — project → 조상 → (옵션) git 본체 레포.

    do-er 서브에이전트는 git worktree 에서 돈다. 워크트리는 `.claude/` 가 gitignore 라 체크아웃
    되지 않아 `<worktree>/.claude/dw-config.json` 이 **없다** — 조상·본체 레포 탐색이 그 구멍을
    메운다(2.9.x 에서 가드가 조용히 무력화된 결함의 교정).

    `ancestors` 는 project 자신을 포함한 단계 수(1 = project 만). `git_probe` 는 `git rev-parse`
    **서브프로세스**를 쓴다 — 훅 예산 규율상 그것을 감당할 호출자만 켠다(가드 5 개가 켠다,
    `dw-doctor` 는 끈다: "파일/폴더 존재 검사만" 이 그 파일의 계약이다).
    """
    if project is None:
        return []
    out: list[Path] = []
    try:
        cur = Path(project).resolve()
    except (OSError, ValueError):        # NUL 이 박힌 경로는 OSError 가 아니라 ValueError 다
        return []
    for _ in range(max(ancestors, 0)):
        out.append(cur)
        if cur.parent == cur:
            break
        cur = cur.parent
    if git_probe:
        try:
            import subprocess          # 지연 임포트 — 훅 경로의 임포트 비용을 늘리지 않는다
            r = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=str(project),
                               capture_output=True, text=True, timeout=3)
            if r.returncode == 0 and r.stdout.strip():
                cp = Path(r.stdout.strip())
                if not cp.is_absolute():
                    cp = (Path(project) / cp).resolve()
                out.append(cp.parent)          # 본체 레포 루트
        except Exception:                      # noqa: BLE001 — 훅은 어떤 이유로도 죽지 않는다
            pass
    return out


def config_source(project: Path | None, home: str, *, ancestors: int = 8,
                  git_probe: bool = False) -> VaultSource | None:
    """첫 번째로 발견되는 `dw-config.json` 의 `vault_root` 선언. 없으면 None.

    파싱 실패·읽기 실패는 **다음 후보로 넘어간다**(조용히 죽지 않지만 훅을 깨지도 않는다).
    """
    for d in config_dirs(project, ancestors=ancestors, git_probe=git_probe):
        cfg = Path(d, *CONFIG_REL)
        if not cfg.is_file():
            continue
        try:
            import json                # 지연 임포트 — json 이 필요 없는 호출자에게 비용 0
            data = json.loads(cfg.read_text(encoding="utf-8"))
        except (OSError, ValueError):   # ValueError ⊃ json.JSONDecodeError
            continue
        # ⚠️ dict 확인은 필수다. 종전 사본 7 곳도 전부 `.get` 을 바로 불러 **`[]`·`"x"` 같은
        #    최상위 값이면 AttributeError** 였다 — 훅에서 그건 세션·가드 파손이다(자기검사가 잡음).
        if not isinstance(data, dict):
            continue
        raw = data.get(CONFIG_KEY)
        if raw and isinstance(raw, str):
            return VaultSource("config", str(cfg), str(raw),
                               Path(expand_home_prefix(str(raw), home)))
    return None


def conventional_vault(home: str) -> Path:
    return Path(home) / CONVENTIONAL_VAULT


def vault_sources(project: Path | None = None, env: dict | None = None, home: str | None = None,
                  *, ancestors: int = 8, git_probe: bool = False) -> list[VaultSource]:
    """**선언된** 출처를 정본 우선순위대로: env > config. 규약 경로는 선언이 아니라 폴백이라 제외.

    존재 검사를 하지 않는다 — 불일치 보고가 "선언은 있는데 폴더가 없다" 도 말해야 한다.
    """
    env = os.environ if env is None else env
    home = home_dir(env) if home is None else home
    out: list[VaultSource] = []
    raw = (env.get(VAULT_ENV) or "").strip()
    if raw:
        out.append(VaultSource("env", f"{VAULT_ENV}(env)", raw,
                               Path(expand_home_prefix(raw, home))))
    cfg = config_source(project, home, ancestors=ancestors, git_probe=git_probe)
    if cfg:
        out.append(cfg)
    return out


def _usable(p: Path, require: str | None) -> bool:
    """`require`: "dir"(폴더 존재) | "governance"(vault 다움) | None(선언만으로 채택).

    `ValueError` 도 잡는다 — 경로에 NUL 이 박히면 `is_dir()` 이 `OSError` 가 아니라 `ValueError`
    를 던진다. 이 함수는 훅 경로에 있고 계약은 "어떤 입력에도 예외 없음" 이다.
    """
    try:
        if require is None:
            return True
        if require == "governance":
            return (p / "governance").is_dir()
        return p.is_dir()
    except (OSError, ValueError):        # 권한·잘못된 경로·NUL — 훅에서 예외를 올리지 않는다
        return False


def find_vault(project: Path | None = None, env: dict | None = None, home: str | None = None, *,
               require: str | None = "dir", ancestors: int = 8, git_probe: bool = False,
               self_repo_fallback: bool = False, warn=None) -> Path | None:
    """**정본** vault 해석. 못 찾으면 `None` — 예외를 올리지 않는다(훅 안전).

    순서: `DW_VAULT_DIR`(env) > `<project>/.claude/dw-config.json` 의 `vault_root` > 규약 경로.
    `self_repo_fallback` 은 "이 레포가 플러그인 본체면 자기 자신을 vault 로 본다"(가드 4 개의
    종전 동작 — `dw-artifact-guard` 는 갖고 있지 않아 기본값이 False 다).
    """
    env = os.environ if env is None else env
    home = home_dir(env) if home is None else home
    for src in vault_sources(project, env, home, ancestors=ancestors, git_probe=git_probe):
        if _usable(src.path, require):
            return src.path
        if warn:
            warn(f"denver-workflow: {src.origin}='{src.path}' 폴더 없음 — 다음 출처 시도")
    conv = conventional_vault(home)
    if _usable(conv, require):
        return conv
    if self_repo_fallback and project is not None:
        try:
            if (Path(project) / "_build" / "dw-compile.py").exists():
                return Path(project)
        except OSError:
            pass
    return None


def vault_target(env: dict | None = None, home: str | None = None, *,
                 project: Path | None = None, ancestors: int = 8) -> Path:
    """vault 가 **있어야 할** 경로 — 존재를 요구하지 않는다(`require=None`).

    `scaffold-vault`(아직 없는 vault 를 만드는 일)처럼 "어디에 만들까" 만 필요한 경로용.
    그래서 `DW_VAULT_DIR` 가 없는 폴더를 가리켜도 **그 값을 그대로** 돌려준다(만들 자리다).
    `resolve_vault` 와 **같은 우선순위**를 쓴다 — 두 함수가 다른 자리를 말하면 "만든 곳" 과
    "읽는 곳" 이 갈린다.
    """
    env = os.environ if env is None else env
    return find_vault(project_dir(env, project), env, home, require=None, ancestors=ancestors) \
        or conventional_vault(home_dir(env) if home is None else home)


def resolve_vault(env: dict | None = None, home: str | None = None, warn=None, *,
                  project: Path | None = None, ancestors: int = 8) -> Path:
    """실재하는 vault. 없으면 `SystemExit(1)` — 조용히 빈 지식으로 동작하지 않는다.

    ⚠️ `env`·`home`·`warn` 의 **위치 인자 순서는 계약**이다(자기검사가 positional 로 부른다).
    `project` 는 keyword-only 로 추가했다 — 위치에 끼우면 기존 호출의 `home` 이 조용히
    `project` 로 먹힌다.

    `project` 를 주지 않으면 `CLAUDE_PROJECT_DIR`(env) 를 본다. MCP 런처가 그 env 를 실제로
    받는다(실측 2026-08-08: 살아있는 서버 프로세스 환경에 `CLAUDE_PROJECT_DIR`·`DW_VAULT_DIR`
    둘 다 존재) — 그래서 env 가 비어도 config 안전망이 남는다.
    """
    env = os.environ if env is None else env
    home = home_dir(env) if home is None else home
    warn = warn or (lambda msg: print(msg, file=sys.stderr))
    found = find_vault(project_dir(env, project), env, home, require="dir",
                       ancestors=ancestors, warn=warn)
    if found is not None:
        return found
    warn(
        f"denver-workflow: vault 없음 ({conventional_vault(home)}). "
        f"'/dw-setup' 으로 준비하거나 {VAULT_ENV} 를 설정하세요."
    )
    raise SystemExit(1)


# ── 출처 불일치 노출 ──────────────────────────────────────────────────────────────
# 결정론적으로 하나를 고르는 것만으로는 "vault 는 하나" 를 보증하지 못한다 — 출처들이 서로 다른
# 값을 말하는데 조용히 하나를 고르면 **두 곳을 가리키는 상태가 오류 없이 지나간다**. 특히 우선
# 순위가 env-first 로 통일된 뒤엔 "프로젝트는 config 로 vault B 에 묶였는데 가드는 env 의 vault A
# 를 지킨다" 는 새 실패 모드가 생긴다 — 그래서 노출은 이 통합의 **전제조건**이다.
#
# hard-fail 하지 않는 이유: 이 판정을 쓰는 곳이 SessionStart 훅(timeout 15s)과 가드다. 세션·훅을
# 깨뜨리는 편이 "가드가 엉뚱한 vault 를 지키는" 것보다 나쁘고(훅 예외 금지 규율), 채택되는 값은
# 어느 쪽이든 결정론적이다. 그래서 **사람이 실제로 읽는 두 채널**로 시끄럽게만 만든다 —
# SessionStart 다이제스트(매 세션 주입)와 `make doctor`/`dw doctor`. 새 채널은 만들지 않는다.

def vault_conflict_note(project: Path | None = None, env: dict | None = None,
                        home: str | None = None, *, require: str | None = "dir",
                        ancestors: int = 8, git_probe: bool = False) -> str:
    """출처들이 다른 vault 를 말하면 사람이 읽을 경고 문단, 아니면 빈 문자열.

    예외를 올리지 않는다(훅에서 부른다).
    """
    try:
        env = os.environ if env is None else env
        home = home_dir(env) if home is None else home
        srcs = vault_sources(project, env, home, ancestors=ancestors, git_probe=git_probe)
        if len(srcs) < 2:
            return ""

        def norm(p: Path) -> str:
            try:
                return str(p.resolve())
            except OSError:
                return str(p)

        if len({norm(s.path) for s in srcs}) < 2:
            return ""
        chosen = find_vault(project, env, home, require=require, ancestors=ancestors,
                            git_probe=git_probe)
        lines = [f"⚠️ denver-workflow: vault 를 말하는 출처가 **서로 다른 경로**를 가리킨다 "
                 f"(vault 는 하나여야 한다)."]
        for s in srcs:
            marks = []
            if chosen is not None and norm(s.path) == norm(chosen):
                marks.append("사용 중")
            if not _usable(s.path, require):
                marks.append("폴더 없음")
            suffix = f"  ← {', '.join(marks)}" if marks else ""
            lines.append(f"   · {s.origin} = {s.path}{suffix}")
        if chosen is not None and all(norm(s.path) != norm(chosen) for s in srcs):
            lines.append(f"   · 규약 경로 = {chosen}  ← 사용 중(선언된 출처가 전부 쓸 수 없다)")
        cfg = next((s for s in srcs if s.name == "config"), None)
        lines.append(
            f"   해소: 하나로 맞추라 — {VAULT_ENV}(전역, `~/.claude/settings.json` 의 `env`)를 "
            f"맞추거나, `/dw-install`(= `python3 _build/dw.py install-project`)로 "
            f"{cfg.origin if cfg else 'dw-config.json'} 를 다시 쓰라. "
            f"정본 우선순위는 {VAULT_ENV}(env) > dw-config.json 의 {CONFIG_KEY} > 규약 경로다."
        )
        return "\n".join(lines)
    except Exception:                   # noqa: BLE001 — 경고 계산이 호출자를 죽이면 안 된다
        return ""


def cross_project_conflicts(vault: Path, env: dict | None = None,
                            home: str | None = None) -> list[str]:
    """등록된 프로젝트들의 `dw-config.json` 이 서로 다른 vault 를 말하면 그 목록.

    **on-demand 전용**(`dw doctor`) — 레지스트리에 등록된 레포 수만큼 파일을 읽으므로 훅 예산
    (SessionStart timeout 15s)에 넣지 않는다. 훅은 이 세션의 출처만 O(1) 로 본다.
    """
    try:
        import dw_state
        env = os.environ if env is None else env
        home = home_dir(env) if home is None else home
        seen: dict[str, list[str]] = {}
        for proj in dw_state.registered_projects(vault):
            src = config_source(proj, home, ancestors=1, git_probe=False)
            if src is None:
                continue
            seen.setdefault(str(src.path), []).append(str(proj))
        if len(seen) < 2:
            return []
        return [f"{path}  ← {', '.join(projects)}" for path, projects in sorted(seen.items())]
    except Exception:                   # noqa: BLE001
        return []


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
    import subprocess              # 지연 임포트 — 모듈 docstring 「훅 경로」 참조(3.9.6 8.6ms)
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
