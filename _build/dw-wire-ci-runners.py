#!/usr/bin/env python3
"""dw-ci(OrbStack Ubuntu) 안 GitHub Actions self-hosted 러너들에 job-completed prune 훅을 멱등 배선.

**무엇을**: ① 플러그인의 `ci-runner/job-completed-prune.sh` 를 dw-ci VM 의 고정 경로
(`/home/denver/.dw-ci-hooks/job-completed-prune.sh`)로 복사(755) ② 각 러너 디렉토리의 `.env` 에
`ACTIONS_RUNNER_HOOK_JOB_COMPLETED=<그 경로>` 를 멱등 upsert(같으면 no-op·다르면 교체·없으면 append).

**왜 `/dw-install` 과 분리**: `install-project` 는 아무 머신에서나 프로젝트별로 돈다. 이 배선은
`orbctl … dw-ci` 라는 **단일 호스트 외부 의존**이라, 없는 머신에서 install 이 조용히 실패하거나
낯설게 동작하면 안 된다. Makefile 의 `plugin-scope-*`·`verifier-scope` 처럼 **민감·머신특정 작업은
명시적 별도 타깃**이라는 관례를 따른다. orbctl/dw-ci 부재 시 시끄럽게 중단한다(exit 2).

**활성화 시점(중요)**: 러너는 `.env` 를 **서비스 시작 시에만** 읽는다(`Runner.Listener` 가 내부에서
로드). 따라서 `.env` 를 써도 실행 중 러너에는 즉시 반영되지 않고 **다음 재시작 때** 활성화된다.
`--restart-idle` 를 주면, `Runner.Worker`(=활성 잡) 프로세스가 없는 러너만 골라 systemd 재시작해
즉시 활성화한다(활성 잡 있는 러너는 절대 건드리지 않는다 — 재시작=실행 중 잡 사망).

경계 정책(`dw-install-registered.py` 와 동형): 러너별 실패는 계속 진행·끝에 모아 보고·하나라도
실패면 exit 1. 부분 실패를 성공으로 넘기지 않는다.

usage: dw-wire-ci-runners.py [--dry-run] [--restart-idle]
표준 라이브러리만 사용.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

BUILD = Path(__file__).resolve().parent
ROOT = BUILD.parent
HOOK_SRC = ROOT / "ci-runner" / "job-completed-prune.sh"

MACHINE = "dw-ci"                               # OrbStack VM 이름
HOOK_DST = "/home/denver/.dw-ci-hooks/job-completed-prune.sh"  # VM 내 고정 설치 경로(러너 디렉토리 밖 → 러너 자동갱신 무영향)
ENV_KEY = "ACTIONS_RUNNER_HOOK_JOB_COMPLETED"
# 러너 디렉토리 ↔ systemd 서비스(2026-09 실측). 재시작은 이 매핑으로만 한다.
RUNNERS = {
    "/home/denver/actions-runner":      "actions.runner.denvernext80-Balipick.dw-linux-balipick.service",
    "/home/denver/actions-runner-2":    "actions.runner.denvernext80-Balipick.dw-linux-balipick-2.service",
    "/home/denver/actions-runner-3":    "actions.runner.denvernext80-Balipick.dw-linux-balipick-3.service",
    "/home/denver/actions-runner-app":  "actions.runner.denvernext80-Balipick-App.dw-linux-app.service",
    "/home/denver/actions-runner-chat": "actions.runner.denvernext80-Balipick-chat.dw-linux-chat.service",
}


def _orb(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    """dw-ci VM 안에서 명령 실행. denver 사용자로 돈다(실측: orbctl run -m dw-ci id -un → denver)."""
    return subprocess.run(["orbctl", "run", "-m", MACHINE, *cmd],
                          capture_output=True, text=True, timeout=120, **kw)


def _orb_sh(script: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    """VM 안에서 bash 스크립트 실행(로그인 셸). stdin 을 넘기면 그대로 파이프한다."""
    _flush()
    return subprocess.run(["orbctl", "run", "-m", MACHINE, "bash", "-lc", script],
                          input=stdin, capture_output=True, text=True, timeout=120)


def _flush() -> None:
    sys.stdout.flush()
    sys.stderr.flush()


def preflight() -> str | None:
    """orbctl·dw-ci·훅 소스 가용성 확인. 문제 있으면 사람이 읽을 사유 문자열 반환."""
    if not HOOK_SRC.is_file():
        return f"훅 소스 없음: {HOOK_SRC}"
    from shutil import which
    if which("orbctl") is None:
        return "orbctl 없음 — 이 배선은 dw-ci(OrbStack) 가 있는 머신에서만 동작한다"
    try:
        r = _orb(["true"])
    except (OSError, subprocess.SubprocessError) as e:
        return f"orbctl run -m {MACHINE} 실행 실패: {type(e).__name__}: {e}"
    if r.returncode != 0:
        return f"dw-ci VM 접근 불가 (orbctl run -m {MACHINE}) — {(r.stderr or r.stdout).strip()[:200]}"
    return None


def install_hook_script(dry_run: bool) -> tuple[bool, str]:
    """훅 스크립트를 VM 고정 경로로 복사(755). 소스를 stdin 으로 파이프 → 공유 FS 비의존."""
    if dry_run:
        return True, f"(dry-run) 훅 복사 생략 → {HOOK_DST}"
    src = HOOK_SRC.read_text(encoding="utf-8")
    # cat > tmp && chmod && mv : 원자적 교체. denver 소유로 떨어진다.
    # (`install -m755 /dev/stdin` 은 orbctl 의 stdin 파이프에서 Permission denied 로 실패 — 실측.)
    tmp = f"{HOOK_DST}.tmp.$$"
    r = _orb_sh(
        f'mkdir -p "$(dirname {HOOK_DST})" && cat > "{tmp}" && chmod 755 "{tmp}" '
        f'&& mv "{tmp}" "{HOOK_DST}"',
        stdin=src)
    if r.returncode != 0:
        return False, f"훅 복사 실패: {(r.stderr or r.stdout).strip()[:200]}"
    # 실효 확인: 목적지가 실행가능한지.
    chk = _orb_sh(f'test -x "{HOOK_DST}" && echo OK')
    if "OK" not in chk.stdout:
        return False, f"훅 복사 후 실행권한 확인 실패: {HOOK_DST}"
    return True, f"훅 설치: {HOOK_DST} (755, denver)"


def _env_upsert_script(env_path: str) -> str:
    r"""VM 안에서 실행할 멱등 upsert 셸 스크립트를 생성.

    - 같은 값 이미 있음 → SKIP
    - 다른 값 있음 → 그 줄 교체(REPLACED)
    - 없음 → append(ADDED) — 파일 끝 개행 보장 후 붙인다(DW_GATE_HARD=1ACTIONS_… 사고 방지)
    tmp + mv 로 원자적 교체, 모드 보존.
    """
    key = ENV_KEY
    val = HOOK_DST
    line = f"{key}={val}"
    # heredoc 없이 순수 POSIX. grep 로 현재 상태 판정 → 분기.
    return f'''
f="{env_path}"
touch "$f"
cur="$(grep -E "^{key}=" "$f" || true)"
if [ "$cur" = "{line}" ]; then
  echo "SKIP"
elif [ -n "$cur" ]; then
  tmp="$(mktemp)"; cp -p "$f" "$tmp"
  grep -vE "^{key}=" "$f" > "$tmp" || true
  printf '%s\\n' "{line}" >> "$tmp"
  chmod --reference="$f" "$tmp" 2>/dev/null || true
  mv "$tmp" "$f"
  echo "REPLACED"
else
  # 파일 끝 개행 보장 후 append
  [ -s "$f" ] && [ "$(tail -c1 "$f")" != "" ] && printf '\\n' >> "$f" || true
  printf '%s\\n' "{line}" >> "$f"
  echo "ADDED"
fi
'''


def wire_env(runner_dir: str, dry_run: bool) -> tuple[bool, str]:
    env_path = f"{runner_dir}/.env"
    if dry_run:
        r = _orb_sh(f'grep -E "^{ENV_KEY}=" "{env_path}" 2>/dev/null || echo "(미설정)"')
        return True, f"(dry-run) {env_path} 현재: {r.stdout.strip()}"
    r = _orb_sh(_env_upsert_script(env_path))
    out = (r.stdout or "").strip().splitlines()
    state = out[-1] if out else ""
    if r.returncode != 0 or state not in ("SKIP", "REPLACED", "ADDED"):
        return False, f"{env_path}: upsert 실패 rc={r.returncode} — {(r.stderr or r.stdout).strip()[:200]}"
    # 실효 재확인: 파일에 정확한 라인이 정확히 1번 있는가.
    vf = _orb_sh(f'grep -cxF "{ENV_KEY}={HOOK_DST}" "{env_path}"')
    n = (vf.stdout or "0").strip()
    if n != "1":
        return False, f"{env_path}: 검증 실패 — 기대 라인 개수 1, 실제 {n}"
    return True, f"{env_path}: {state}"


def restart_idle(runner_dir: str, service: str) -> tuple[bool, str]:
    """활성 잡(Runner.Worker) 없는 러너만 재시작. check+restart 를 한 명령으로(TOCTOU 최소화)."""
    # bin 디렉토리 패턴으로 이 러너의 Worker 만 매칭. 있으면 건드리지 않고 SKIP.
    # 🔴 `[R]unner` 트릭: pgrep -f 는 «자신을 실행하는 래퍼 프로세스의 argv»(=이 패턴 문자열을
    #    그대로 담고 있다)까지 매칭해 전부 BUSY 로 오판한다(실측). 패턴에 문자클래스 `[R]` 를 넣으면
    #    래퍼 argv 의 리터럴 `[R]unner` 는 정규식 `[R]unner`(=`Runner`)에 안 맞아 자기매칭이 끊긴다.
    script = (
        f'if pgrep -f "{runner_dir}/bin.*[R]unner.Worker" >/dev/null 2>&1; then '
        f'echo "BUSY"; '
        f'else sudo -n systemctl restart "{service}" && echo "RESTARTED" || echo "RESTART_FAIL"; fi'
    )
    r = _orb_sh(script)
    state = (r.stdout or "").strip().splitlines()[-1] if r.stdout.strip() else ""
    if state == "BUSY":
        return True, f"{service}: 활성 잡 있음 — 재시작 안 함(다음 자연 재시작 시 활성화)"
    if state == "RESTARTED":
        return True, f"{service}: 재시작 완료 — 훅 즉시 활성화"
    return False, f"{service}: 재시작 실패 — {(r.stderr or r.stdout).strip()[:200]}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="쓰기 없이 현재 상태만 조회")
    ap.add_argument("--restart-idle", action="store_true",
                    help="활성 잡 없는 러너만 재시작해 즉시 활성화(활성 잡 있는 러너는 건드리지 않음)")
    args = ap.parse_args()

    reason = preflight()
    if reason:
        print(f"[wire-ci] 중단: {reason}", file=sys.stderr)
        return 2

    print(f"[wire-ci] dw-ci 러너 {len(RUNNERS)}개에 job-completed prune 훅 배선"
          + (" (dry-run)" if args.dry_run else ""))

    ok, msg = install_hook_script(args.dry_run)
    print(f"  {'✓' if ok else '✗'} {msg}")
    if not ok:
        return 1

    failed: list[str] = []
    for rdir in RUNNERS:
        good, m = wire_env(rdir, args.dry_run)
        print(f"  {'✓' if good else '✗'} {m}")
        if not good:
            failed.append(m)

    if args.restart_idle and not args.dry_run:
        print("[wire-ci] 활성 잡 없는 러너 재시작(즉시 활성화):")
        for rdir, svc in RUNNERS.items():
            good, m = restart_idle(rdir, svc)
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
