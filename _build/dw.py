#!/usr/bin/env python3
"""dw — denver-workflow 이식 가능 CLI. 슬래시 커맨드가 부르는 **로직의 단일 정본**.

**왜**(2.15.0): 슬래시 커맨드 10 개 중 7 개가 `make` 타깃을 호출했다. `make` 는 macOS/Linux 엔
사실상 항상 있지만 **Windows 에는 없다** — Git for Windows 가 `grep`·`uname`·`cp` 는 주지만
`make` 는 주지 않는다. 그래서 L3(커맨드의 make 의존)이 남은 마지막 구조적 셸/툴 의존이었다.
이 CLI 는 그 9 개 타깃을 서브커맨드로 제공한다(+ 파생 `doctor`·`bootstrap`).

⚠️ **구현을 둘로 만들지 않는다.** 이 파일이 정본이고 `Makefile` 은 **얇게 위임**한다
(`<target>: ; $(DW) <target>`). 두 구현이 갈라지면 `make X` 와 `/dw-X` 가 다르게 동작하고,
그게 이 레포에서 반복적으로 잡힌 결함 클래스다("주석·문구가 코드보다 더 주장한다").
`dw-selftest.py` 가 **모든 위임 타깃의 레시피가 실제로 위임인지** 검사한다.

⚠️ **주장 범위**: 없앤 것은 "커맨드의 make 의존"(구조적)이다. **Windows 실기 미검증** —
   판정 절차는 `docs/windows-smoke-checklist.md`.

vault 해석·venv 부트스트랩·`mcp<2` 핀은 `dw_runtime.py` 가 정본이다(MCP 런처와 공유).

usage: python3 _build/dw.py <subcommand> [options]
       python3 _build/dw.py --help
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import dw_runtime

BUILD = Path(__file__).resolve().parent
ROOT = BUILD.parent                    # 도구 루트(.venv·_build·_seed·.claude 산출물)
SEED = ROOT / "_seed"
COMPILER = BUILD / "dw-compile.py"
MCP_SERVER = BUILD / "dw-mcp-server.py"


# ── 실행 헬퍼 ─────────────────────────────────────────────────────────────────────

def _venv_py() -> Path:
    """venv 인터프리터(없으면 부트스트랩). CLI 는 stdout 이 사람용이라 안내도 stdout 으로."""
    return dw_runtime.ensure_venv(ROOT / ".venv", notify=lambda m: print(m, flush=True))


def _flush() -> None:
    """자식을 띄우기 **전에** 우리 버퍼를 비운다.

    ⚠️ 이게 없으면 출력 순서가 뒤집힌다. 파이썬 stdout 은 tty 일 때 line-buffered, **파이프일 때
    block-buffered** 다 — 자식은 같은 fd 에 즉시 쓰므로, 부모의 `print` 가 프로세스 종료 시점에야
    나가면서 자식 출력 뒤로 밀린다. 실측(2.15.0 개발 중): `dw.py doctor | cat` 이 헬스체크 헤더를
    외부 의존 목록 **뒤에** 찍었다. 에이전트가 보는 경로가 정확히 이 파이프 경로다.
    """
    sys.stdout.flush()
    sys.stderr.flush()


def _run(argv: list[str]) -> int:
    """자식 실행 — stdio 를 그대로 물려준다(사람이 진행 상황을 봐야 한다)."""
    _flush()
    return subprocess.run([str(a) for a in argv]).returncode


def _quiet(argv: list[str]) -> bool:
    """자식을 조용히 돌리고 성공 여부만 본다(doctor 의 프로브용)."""
    _flush()
    p = subprocess.run([str(a) for a in argv], capture_output=True, text=True)
    return p.returncode == 0


def _vault_required() -> Path:
    """실재하는 vault. 없으면 시끄럽게 중단(조용히 빈 지식으로 동작하지 않는다)."""
    return dw_runtime.resolve_vault()


def _project(arg: str | None) -> Path:
    """대상 프로젝트 — 생략 시 **현재 디렉토리**.

    커맨드 문서에서 `P="$(pwd)"` 같은 셸 치환을 없애기 위한 기본값이다(셸 비의존).
    """
    return Path(arg).expanduser().resolve() if arg else Path.cwd().resolve()


# ── 서브커맨드 ────────────────────────────────────────────────────────────────────

def cmd_bootstrap(args) -> int:
    """venv 를 보장한다(멱등). Makefile 의 venv 선행조건이 이걸 쓴다."""
    _venv_py()
    return 0


def _compile_workspace(extra: list[str]) -> int:
    """이 워크스페이스의 `.claude/skills` 로 컴파일. build/dry-run 공용 경로."""
    py = _venv_py()
    vault = _vault_required()
    return _run([py, COMPILER, "--vault", vault,
                 "--out", ROOT / ".claude" / "skills", *extra])


def cmd_build(args) -> int:
    """vault 를 컴파일해 `.claude/skills` 생성."""
    return _compile_workspace([])


def cmd_dry_run(args) -> int:
    """쓰기 없이 검증/요약(경고도 에러)."""
    return _compile_workspace(["--dry-run", "--strict"])


def cmd_install_project(args) -> int:
    """한 프로젝트에 설치: 스킬 + 결정론 검사 매니페스트 + 에이전트 + 세션 다이제스트."""
    py = _venv_py()
    vault = _vault_required()
    if not (vault / "governance").is_dir():
        print(f"vault 없음: {vault} — /dw-setup 으로 vault(팀 지식 폴더)를 먼저 준비하세요",
              file=sys.stderr)
        return 1
    project = _project(args.project)
    argv = [py, COMPILER, "--vault", vault, "--out", project / ".claude" / "skills"]
    if args.scopes:
        argv += ["--scopes", args.scopes]
    argv += ["--checks-out", project / ".claude" / "dw-checks.json",
             "--agents-out", project / ".claude" / "agents",
             "--digest-out", project / ".claude" / "dw-session-digest.md"]
    rc = _run(argv)
    if rc != 0:
        return rc
    rc = _run([py, BUILD / "wire-hook.py", project, vault, "--config-only"])
    if rc != 0:
        return rc
    print(f"✓ 설치 완료: {project}/.claude/{{skills,agents,dw-checks.json,dw-session-digest.md}}")
    return 0


def cmd_ratify(args) -> int:
    """draft OBEY 자동 비준 → 등록된 모든 프로젝트에 compile+install(멱등)."""
    py = _venv_py()
    vault = _vault_required()
    projects: list[str] = []
    for p in args.project or []:
        projects += ["--project", str(_project(p))]

    rc = _run([py, BUILD / "dw-ratify.py", "--vault", vault, *projects])
    # 비준기의 정상 종료코드는 0(변경 없음)과 10(승격 있음)뿐이다. 그 밖의 코드는 크래시이므로
    # 숨기지 않고 알린다 — 아래 설치는 승격 반영 없이 진행된다.
    if rc not in (0, 10):
        print(f"  ⚠️ 비준기 비정상 종료(exit={rc}) — 아래 설치는 승격 반영 없이 진행된다")
    print()
    print("→ 컴파일·설치: 등록된 프로젝트 전체(멱등) — 승격분 + 사람이 고친 stable 반영")
    return _run([py, BUILD / "dw-install-registered.py", "--vault", vault, *projects])


def cmd_review(args) -> int:
    """OBEY draft 큐(자동 비준 대상/hold) + 헬스체크.

    ⚠️ 이 커맨드는 **vault 가 없어도 끝까지 돈다** — 다른 서브커맨드와 달리 `_vault_required()`
    를 쓰지 않는다. 절반이 헬스체크이고, vault 가 없는 상황이 바로 진단이 필요한 상황이다.
    (2.15.0 개발 중 실측: `_vault_required()` 를 쓰자 신규 머신에서 헬스체크가 **아예 출력되지
    않았다** — 종전 `make review` 는 빈 큐 + 진단을 보여줬다. 진단 도구가 진단이 필요한
    상황에서 먼저 죽는 형태였다.)
    """
    py = _venv_py()
    vault = dw_runtime.vault_target()
    if (vault / "governance").is_dir():
        rc = _run([py, BUILD / "review-queue.py", "--vault", vault])
    else:
        print(f"== OBEY draft 큐 — 건너뜀: vault 없음 ({vault}) ==")
        print("  → /dw-setup 으로 vault(팀 지식 폴더)를 준비하세요. 아래 헬스체크를 함께 보십시오.")
        rc = 0
    print()
    cmd_doctor(args)          # 종전 `make review` 가 `$(MAKE) -s doctor` 를 이어 붙인 그 자리
    return rc


def cmd_doctor(args) -> int:
    """콜드스타트 헬스체크(venv·컴파일러·MCP·vault·외부 의존)."""
    py = _venv_py()
    # doctor 는 vault 가 **없는 상태도 보고**해야 하므로 존재를 요구하지 않는다.
    vault = dw_runtime.vault_target()
    print("== denver-workflow 헬스체크 ==")

    ok = _quiet([py, "-c", "import yaml, mcp"])
    print("  [ok] venv deps: pyyaml + mcp" if ok
          else "  [!!] venv 의존성 누락 -> /dw-build (또는 python3 _build/dw.py build)")

    has_vault = (vault / "governance").is_dir()
    compiled = False
    if has_vault:
        tmp = Path(tempfile.mkdtemp(prefix="dw-doctor-"))
        try:
            compiled = _quiet([py, COMPILER, "--vault", vault, "--out", tmp,
                               "--dry-run", "--strict"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print("  [ok] 컴파일러 strict 통과" if compiled
          else "  [..] vault 컴파일 실패/vault 없음 -> /dw-build 로 확인")

    print("  [ok] MCP 서버 존재" if MCP_SERVER.is_file() else "  [!!] MCP 서버 없음")
    print(f"  [ok] vault 구조: {vault}" if has_vault
          else "  [..] vault 없음 -> /dw-setup (또는 python3 _build/dw.py scaffold-vault)")

    probe = BUILD / "dw-doctor.py"
    if probe.is_file():
        _run([py, probe])
    return 0


def cmd_scaffold_vault(args) -> int:
    """빈/없는 vault 에 제네릭 seed(거버넌스 + 폴더 구조)를 복사(no-clobber)."""
    vault = dw_runtime.vault_target()      # 아직 없어도 되는 경로다
    print(f"→ vault 스캐폴드: {vault}  (기존 파일 보존 — no-clobber)")
    if not SEED.is_dir():
        print(f"seed 없음: {SEED} — 플러그인 설치가 깨졌다.", file=sys.stderr)
        return 1
    copied, kept = _copy_no_clobber(SEED, vault)
    print(f"✓ seed 복사 완료: 신규 {copied}개 / 기존 보존 {kept}개. "
          "구조: governance/(운영체계) + project/(빈 골격) + VAULT-STRUCTURE.md")
    print(f'  다음: Obsidian 으로 "{vault}" 폴더 열기(Open folder as vault) → /dw-build')
    return 0


def _copy_no_clobber(src: Path, dst: Path) -> tuple[int, int]:
    """`cp -Rn <src>/. <dst>/` 의 이식 가능 등가물. 기존 파일은 **절대** 덮지 않는다.

    `shutil.copytree(dirs_exist_ok=True)` 를 쓰지 않는 이유: 그건 기존 파일을 덮어쓴다 —
    사용자가 쌓아 둔 vault 노트를 seed 로 되돌리는 사고가 된다.
    """
    copied = kept = 0
    for s in sorted(src.rglob("*")):
        rel = s.relative_to(src)
        d = dst / rel
        if s.is_dir():
            d.mkdir(parents=True, exist_ok=True)
        elif d.exists():
            kept += 1
        else:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, d)
            copied += 1
    return copied, kept


def _scope(mode: str, project: str | None) -> int:
    argv = [_venv_py(), BUILD / "dw-plugin-scope.py", mode]
    if mode == "project" or (mode == "off" and project is not None):
        argv.append(_project(project))
    return _run(argv)


def cmd_plugin_scope_user(args) -> int:
    """플러그인을 사용자 전역 활성(모든 프로젝트)."""
    return _scope("user", None)


def cmd_plugin_scope_project(args) -> int:
    """플러그인을 이 프로젝트만 활성."""
    return _scope("project", args.project)


def cmd_plugin_scope_off(args) -> int:
    """플러그인 비활성(계정 전역, --project 를 주면 그 프로젝트도).

    ⚠️ 다른 서브커맨드와 달리 `--project` 기본값이 **없다**(cwd 로 떨어지지 않는다).
    `off` 의 프로젝트 처리는 `<project>/.claude/settings.json` 을 **쓰는** 동작이라, 어쩌다
    들어와 있는 디렉토리에 설정 파일을 조용히 만들면 안 된다. 프로젝트까지 정리하려면
    명시적으로 `--project .` 을 준다.
    """
    return _scope("off", args.project)


# ── 파서 ──────────────────────────────────────────────────────────────────────────
# 서브커맨드 이름은 Makefile 타깃과 **1:1 동일**하게 유지한다 — 위임이 눈으로 감사되고,
# 자기검사가 "타깃 ↔ 서브커맨드" 매핑을 기계적으로 고정할 수 있다.
SUBCOMMANDS = {
    "bootstrap": (cmd_bootstrap, ()),
    "build": (cmd_build, ()),
    "dry-run": (cmd_dry_run, ()),
    "install-project": (cmd_install_project, ("project", "scopes")),
    "ratify": (cmd_ratify, ("projects",)),
    "review": (cmd_review, ()),
    "doctor": (cmd_doctor, ()),
    "scaffold-vault": (cmd_scaffold_vault, ()),
    "plugin-scope-user": (cmd_plugin_scope_user, ()),
    "plugin-scope-project": (cmd_plugin_scope_project, ("project",)),
    "plugin-scope-off": (cmd_plugin_scope_off, ("project",)),
}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="dw", description="denver-workflow CLI (make 비의존 — 셸·make 없이 동작)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, (fn, opts) in SUBCOMMANDS.items():
        p = sub.add_parser(name, help=(fn.__doc__ or "").strip().splitlines()[0])
        p.set_defaults(func=fn, project=None, scopes=None)
        if "project" in opts:
            p.add_argument("--project", "-p", metavar="경로",
                           help="대상 프로젝트 절대경로(생략 = 현재 디렉토리)")
        if "projects" in opts:
            p.add_argument("--project", "-p", metavar="경로", action="append",
                           help="대상 프로젝트(반복 가능). 생략 = vault 레지스트리 전체")
        if "scopes" in opts:
            p.add_argument("--scopes", metavar="a,b", help="설치할 scope 묶음(생략 = 전체 union)")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
