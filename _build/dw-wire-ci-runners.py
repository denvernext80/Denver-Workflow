#!/usr/bin/env python3
"""OrbStack VM 안 GitHub Actions self-hosted 러너들에 job-completed prune 훅을 멱등 배선.

**무엇을**: ① 플러그인의 `ci-runner/job-completed-prune.sh` 를 VM 의 `$HOME/.dw-runner-hooks/`
로 복사(755) ② VM 안 systemd 유닛(`actions.runner.*.service`)을 자동 탐지해 각 러너 디렉토리의
`.env` 에 `ACTIONS_RUNNER_HOOK_JOB_COMPLETED=<그 경로>` 를 멱등 upsert(같으면 no-op·다르면 교체·
없으면 append).

**왜 `/dw-install` 과 분리**: `install-project` 는 아무 머신에서나 프로젝트별로 돈다. 이 배선은
`orbctl … <VM>` 이라는 **단일 호스트 외부 의존**이라, 없는 머신에서 install 이 조용히 실패하거나
낯설게 동작하면 안 된다. Makefile 의 `plugin-scope-*`·`verifier-scope` 처럼 **민감·머신특정 작업은
명시적 별도 타깃**이라는 관례를 따른다. orbctl/VM 부재 시 시끄럽게 중단한다(exit 2).

**러너 자동 탐지(범용 원칙)**: 특정 프로젝트/서비스 이름을 코드에 박지 않는다. VM 안
`/etc/systemd/system/actions.runner.*.service` 의 `WorkingDirectory=` 를 읽어 (유닛, 러너 디렉토리)
쌍을 발견한다 — 러너를 추가/이동해도 stale 되지 않고, 어느 팀 호스트에서나 동작한다.

**활성화 시점(중요)**: 러너는 `.env` 를 **서비스 시작 시에만** 읽는다(`Runner.Listener` 가 내부에서
로드). 따라서 `.env` 를 써도 실행 중 러너에는 즉시 반영되지 않고 **다음 재시작 때** 활성화된다.
`--restart-idle` 를 주면, `Runner.Worker`(=활성 잡) 프로세스가 없는 러너만 골라 systemd 재시작해
즉시 활성화한다(활성 잡 있는 러너는 절대 건드리지 않는다 — 재시작=실행 중 잡 사망).

경계 정책(`dw-install-registered.py` 와 동형): 러너별 실패는 계속 진행·끝에 모아 보고·하나라도
실패면 exit 1. 부분 실패를 성공으로 넘기지 않는다.

usage: dw-wire-ci-runners.py --machine <VM 이름> [--dry-run] [--restart-idle]
표준 라이브러리만 사용.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from shutil import which

BUILD = Path(__file__).resolve().parent
ROOT = BUILD.parent
HOOK_SRC = ROOT / "ci-runner" / "job-completed-prune.sh"

HOOK_SUBDIR = ".dw-runner-hooks"               # VM 홈 아래 훅 설치 디렉토리(러너 디렉토리 밖 → 러너 자동갱신 무영향)
HOOK_NAME = "job-completed-prune.sh"
ENV_KEY = "ACTIONS_RUNNER_HOOK_JOB_COMPLETED"


class VM:
    """orbctl 로 접근하는 OrbStack VM 핸들. 명령은 VM 사용자(로그인 셸)로 돈다."""

    def __init__(self, machine: str) -> None:
        self.machine = machine

    def sh(self, script: str, stdin: str | None = None) -> subprocess.CompletedProcess:
        _flush()
        return subprocess.run(["orbctl", "run", "-m", self.machine, "bash", "-lc", script],
                              input=stdin, capture_output=True, text=True, timeout=120)


def _flush() -> None:
    sys.stdout.flush()
    sys.stderr.flush()


def preflight(vm: VM) -> str | None:
    """orbctl·VM·훅 소스 가용성 확인. 문제 있으면 사람이 읽을 사유 문자열 반환."""
    if not HOOK_SRC.is_file():
        return f"훅 소스 없음: {HOOK_SRC}"
    if which("orbctl") is None:
        return "orbctl 없음 — 이 배선은 OrbStack VM 이 있는 머신에서만 동작한다"
    try:
        r = vm.sh("true")
    except (OSError, subprocess.SubprocessError) as e:
        return f"orbctl run -m {vm.machine} 실행 실패: {type(e).__name__}: {e}"
    if r.returncode != 0:
        return f"VM 접근 불가 (orbctl run -m {vm.machine}) — {(r.stderr or r.stdout).strip()[:200]}"
    return None


def resolve_hook_dst(vm: VM) -> str | None:
    """VM 홈을 실측해 훅 설치 절대경로를 만든다(~ 하드코딩 금지). 실패 시 None."""
    r = vm.sh('printf "%s" "$HOME"')
    home = (r.stdout or "").strip()
    if r.returncode != 0 or not home.startswith("/"):
        return None
    return f"{home}/{HOOK_SUBDIR}/{HOOK_NAME}"


def discover_runners(vm: VM) -> tuple[list[tuple[str, str]], str | None]:
    """VM 안 systemd 에서 (유닛서비스명, 러너디렉토리) 쌍을 자동 발견. 특정 이름 하드코딩 없음.

    `actions.runner.*.service` 의 `WorkingDirectory=` 를 읽는다. 반환 `(pairs, error)`.
    """
    script = (
        "grep -H '^WorkingDirectory=' /etc/systemd/system/actions.runner.*.service 2>/dev/null || true"
    )
    r = vm.sh(script)
    pairs: list[tuple[str, str]] = []
    for line in (r.stdout or "").splitlines():
        # 형식: /etc/systemd/system/<unit>.service:WorkingDirectory=/path/to/runner
        if ":" not in line or "WorkingDirectory=" not in line:
            continue
        unit_path, kv = line.split(":", 1)
        unit = Path(unit_path).name  # <unit>.service
        _, _, wd = kv.partition("=")
        wd = wd.strip()
        if unit and wd.startswith("/"):
            pairs.append((unit, wd))
    if not pairs:
        return [], ("actions.runner.*.service 유닛을 찾지 못했다 — 이 VM 에 self-hosted 러너가 "
                    "systemd 서비스로 설치돼 있는지 확인하라")
    return pairs, None


def install_hook_script(vm: VM, hook_dst: str, dry_run: bool) -> tuple[bool, str]:
    """훅 스크립트를 VM 경로로 복사(755). 소스를 stdin 으로 파이프 → 공유 FS 비의존."""
    if dry_run:
        return True, f"(dry-run) 훅 복사 생략 → {hook_dst}"
    src = HOOK_SRC.read_text(encoding="utf-8")
    # cat > tmp && chmod && mv : 같은 dir tmp → 원자적 rename. VM 사용자 소유로 떨어진다.
    # (`install -m755 /dev/stdin` 은 orbctl 의 stdin 파이프에서 Permission denied 로 실패 — 실측.)
    tmp = f"{hook_dst}.tmp.$$"
    r = vm.sh(
        f'mkdir -p "$(dirname "{hook_dst}")" && cat > "{tmp}" && chmod 755 "{tmp}" '
        f'&& mv "{tmp}" "{hook_dst}"',
        stdin=src)
    if r.returncode != 0:
        return False, f"훅 복사 실패: {(r.stderr or r.stdout).strip()[:200]}"
    chk = vm.sh(f'test -x "{hook_dst}" && echo OK')
    if "OK" not in chk.stdout:
        return False, f"훅 복사 후 실행권한 확인 실패: {hook_dst}"
    return True, f"훅 설치: {hook_dst} (755)"


def _env_upsert_script(env_path: str, hook_dst: str) -> str:
    r"""VM 안에서 실행할 멱등 upsert 셸 스크립트를 생성.

    - 같은 값 이미 있음 → SKIP
    - 다른 값 있음 → 그 줄 교체(REPLACED)
    - 없음 → append(ADDED) — 파일 끝 개행 보장 후 붙인다(DW_GATE_HARD=1ACTIONS_… 사고 방지)
    교체는 «대상과 같은 디렉토리»에 tmp 를 만들어 mv → 원자적 rename(모드 보존).
    🔴 bare `mktemp` 는 /tmp(tmpfs)에 떨어지는데 러너 .env 는 홈(별도 블록장치) 이라 fs 가 달라
       mv 가 copy+unlink(비원자적)가 된다(실측). tmp 를 대상 dir 에 두어야 진짜 atomic 이다.
    """
    key = ENV_KEY
    line = f"{key}={hook_dst}"
    return f'''
f="{env_path}"
touch "$f"
cur="$(grep -E "^{key}=" "$f" || true)"
if [ "$cur" = "{line}" ]; then
  echo "SKIP"
elif [ -n "$cur" ]; then
  tmp="$(mktemp "$(dirname "$f")/.env.XXXXXX")"
  grep -vE "^{key}=" "$f" > "$tmp" || true
  printf '%s\\n' "{line}" >> "$tmp"
  chmod --reference="$f" "$tmp" 2>/dev/null || true
  mv "$tmp" "$f"
  echo "REPLACED"
else
  [ -s "$f" ] && [ "$(tail -c1 "$f")" != "" ] && printf '\\n' >> "$f" || true
  printf '%s\\n' "{line}" >> "$f"
  echo "ADDED"
fi
'''


def wire_env(vm: VM, runner_dir: str, hook_dst: str, dry_run: bool) -> tuple[bool, str]:
    env_path = f"{runner_dir}/.env"
    if dry_run:
        r = vm.sh(f'grep -E "^{ENV_KEY}=" "{env_path}" 2>/dev/null || echo "(미설정)"')
        return True, f"(dry-run) {env_path} 현재: {r.stdout.strip()}"
    r = vm.sh(_env_upsert_script(env_path, hook_dst))
    out = (r.stdout or "").strip().splitlines()
    state = out[-1] if out else ""
    if r.returncode != 0 or state not in ("SKIP", "REPLACED", "ADDED"):
        return False, f"{env_path}: upsert 실패 rc={r.returncode} — {(r.stderr or r.stdout).strip()[:200]}"
    vf = vm.sh(f'grep -cxF "{ENV_KEY}={hook_dst}" "{env_path}"')
    n = (vf.stdout or "0").strip()
    if n != "1":
        return False, f"{env_path}: 검증 실패 — 기대 라인 개수 1, 실제 {n}"
    return True, f"{env_path}: {state}"


def restart_idle(vm: VM, runner_dir: str, service: str) -> tuple[bool, str]:
    """활성 잡(Runner.Worker) 없는 러너만 재시작. check+restart 를 한 명령으로(TOCTOU 최소화)."""
    # 🔴 `[R]unner` 트릭: pgrep -f 는 «자신을 실행하는 래퍼 프로세스의 argv»(=이 패턴 문자열을
    #    그대로 담고 있다)까지 매칭해 전부 BUSY 로 오판한다(실측). 패턴에 문자클래스 `[R]` 를 넣으면
    #    래퍼 argv 의 리터럴 `[R]unner` 는 정규식 `[R]unner`(=`Runner`)에 안 맞아 자기매칭이 끊긴다.
    script = (
        f'if pgrep -f "{runner_dir}/bin.*[R]unner.Worker" >/dev/null 2>&1; then '
        f'echo "BUSY"; '
        f'else sudo -n systemctl restart "{service}" && echo "RESTARTED" || echo "RESTART_FAIL"; fi'
    )
    r = vm.sh(script)
    state = (r.stdout or "").strip().splitlines()[-1] if r.stdout.strip() else ""
    if state == "BUSY":
        return True, f"{service}: 활성 잡 있음 — 재시작 안 함(다음 자연 재시작 시 활성화)"
    if state == "RESTARTED":
        return True, f"{service}: 재시작 완료 — 훅 즉시 활성화"
    return False, f"{service}: 재시작 실패 — {(r.stderr or r.stdout).strip()[:200]}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--machine", "-m", required=True,
                    help="러너가 사는 OrbStack VM 이름(예: orbctl list 로 확인)")
    ap.add_argument("--dry-run", action="store_true", help="쓰기 없이 현재 상태만 조회")
    ap.add_argument("--restart-idle", action="store_true",
                    help="활성 잡 없는 러너만 재시작해 즉시 활성화(활성 잡 있는 러너는 건드리지 않음)")
    args = ap.parse_args()

    vm = VM(args.machine)
    reason = preflight(vm)
    if reason:
        print(f"[wire-ci] 중단: {reason}", file=sys.stderr)
        return 2

    hook_dst = resolve_hook_dst(vm)
    if not hook_dst:
        print(f"[wire-ci] 중단: VM 홈($HOME) 해석 실패 (orbctl run -m {vm.machine})", file=sys.stderr)
        return 2

    runners, err = discover_runners(vm)
    if err:
        print(f"[wire-ci] 중단: {err}", file=sys.stderr)
        return 2

    print(f"[wire-ci] VM '{vm.machine}' 에서 러너 {len(runners)}개 발견 · job-completed prune 훅 배선"
          + (" (dry-run)" if args.dry_run else ""))
    for unit, rdir in runners:
        print(f"    발견: {unit} → {rdir}")

    ok, msg = install_hook_script(vm, hook_dst, args.dry_run)
    print(f"  {'✓' if ok else '✗'} {msg}")
    if not ok:
        return 1

    failed: list[str] = []
    for _unit, rdir in runners:
        good, m = wire_env(vm, rdir, hook_dst, args.dry_run)
        print(f"  {'✓' if good else '✗'} {m}")
        if not good:
            failed.append(m)

    if args.restart_idle and not args.dry_run:
        print("[wire-ci] 활성 잡 없는 러너 재시작(즉시 활성화):")
        for unit, rdir in runners:
            good, m = restart_idle(vm, rdir, unit)
            print(f"  {'✓' if good else '✗'} {m}")
            if not good:
                failed.append(m)

    if not args.dry_run and not args.restart_idle:
        print("[wire-ci] .env 설정됨 — 각 러너의 **다음 자연 재시작** 때 활성화된다"
              " (즉시 활성화: --restart-idle, 단 활성 잡 없는 러너만).")

    if failed:
        print(f"[wire-ci] 실패 {len(failed)}건 — 위 참조", file=sys.stderr)
        return 1
    print("[wire-ci] 완료.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
