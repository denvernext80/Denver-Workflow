#!/usr/bin/env python3
"""등록된 모든 프로젝트에 컴파일 산출물을 설치한다(멱등).

`dw-ratify.py` 는 스스로 "status 만 바꾼다 — 실제 컴파일·설치는 **호출자**가 한다" 고 적어놨는데,
정작 호출자(`make ratify`)는 안내문만 출력했다(2026-08-07 실측: 승격 후 사람이 손으로
`make install-project` 를 4번 돌려야 검사가 14→15건이 됐다). **책임을 위임했는데 아무도 하지
않던 그 자리**를 이 스크립트가 채운다.

대상은 `<vault>/.dw-state/projects.json` 레지스트리(= `make install-project` 가 등록).

경계 정책(의도적으로 이렇게 골랐다):
  - 레지스트리가 **비었다** → 경고만, exit 0. 요청된 일이 없으므로 실패가 아니다.
  - 등록 경로가 **사라졌다** → 경고 + 제거 방법 안내, exit 0. 삭제된 레포 하나가 매일 빨간
    실행을 만들면 로그를 아무도 안 보게 된다(= 게이트가 의미를 잃는 그 형태). 자동 제거는
    상태를 조용히 바꾸므로 하지 않는다 — 매 실행 보고서에 계속 보이게 한다.
  - 설치가 **실패했다** → 남은 프로젝트를 계속 처리하고, 끝에 모아 보고하고, **exit 1**.
    부분 실패를 성공으로 넘기지 않는다.

usage: dw-install-registered.py --vault /abs/vault [--project /abs/p ...] [--dry-run]
표준 라이브러리만 사용.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import dw_state

BUILD = Path(__file__).resolve().parent


def install_one(vault: Path, project: Path, dry_run: bool = False) -> tuple[bool, str]:
    """한 프로젝트에 설치. 반환 `(성공, 메시지)`. `make install-project` 와 동일한 절차."""
    if dry_run:
        return True, f"(dry-run) 설치 생략: {project}"
    cmds = [
        [sys.executable, str(BUILD / "dw-compile.py"),
         "--vault", str(vault),
         "--out", str(project / ".claude" / "skills"),
         "--checks-out", str(project / ".claude" / "dw-checks.json"),
         "--agents-out", str(project / ".claude" / "agents"),
         "--digest-out", str(project / ".claude" / "dw-session-digest.md")],
        [sys.executable, str(BUILD / "wire-hook.py"), str(project), str(vault), "--config-only"],
    ]
    for cmd in cmds:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.SubprocessError) as e:
            return False, f"{project}: 실행 실패 {type(e).__name__}: {e}"
        if r.returncode != 0:
            tail = (r.stderr or r.stdout or "").strip().splitlines()
            return False, f"{project}: {Path(cmd[1]).name} exit={r.returncode} — {tail[-1] if tail else '출력 없음'}"
    return True, f"{project}: 설치 완료(skills·agents·dw-checks.json·digest)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True, type=Path)
    ap.add_argument("--project", action="append", default=[], type=Path,
                    help="레지스트리 대신 이 경로들에만 설치")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="성공 라인 생략(훅용)")
    args = ap.parse_args()
    vault = args.vault.expanduser().resolve()

    if not (vault / "governance").is_dir():
        print(f"[install] vault 없음: {vault} — 설치할 수 없다(/dw-setup 으로 준비).")
        return 1

    if args.project:
        targets = [p.expanduser().resolve() for p in args.project]
        missing: list[str] = [str(p) for p in targets if not p.is_dir()]
        targets = [p for p in targets if p.is_dir()]
        src = "--project 인자"
    else:
        raw = dw_state.read_registry(vault)
        targets = dw_state.registered_projects(vault)
        alive = {str(p) for p in targets}
        missing = [s for s in raw if str(Path(s).expanduser().resolve()) not in alive]
        src = f"{dw_state.STATE_DIR}/{dw_state.PROJECTS_JSON} 레지스트리"

    if not targets and not missing:
        print(f"[install] 설치 대상 0개 ({src}) — 설치할 곳이 없다. "
              f"`/dw-install` 로 레포를 등록하라. (실패 아님)")
        return 0

    ok: list[str] = []
    failed: list[str] = []
    for p in targets:
        good, msg = install_one(vault, p, args.dry_run)
        (ok if good else failed).append(msg)
        if good and not args.quiet:
            print(f"  ✓ {msg}")

    print(f"[install] 대상 {len(targets)}개({src}) · 성공 {len(ok)} · 실패 {len(failed)}"
          + (f" · 사라진 등록 {len(missing)}" if missing else ""))
    for m in missing:
        print(f"  ⚠️ 등록 경로 없음(건너뜀): {m}\n"
              f"      → 레포를 옮겼다면 새 경로에서 `/dw-install`, 없앴다면 "
              f"{dw_state.registry_path(vault)} 에서 이 항목을 지워라.")
    for m in failed:
        print(f"  ✗ {m}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
