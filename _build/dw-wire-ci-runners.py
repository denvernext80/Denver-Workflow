#!/usr/bin/env python3
"""OrbStack VM 안 GitHub Actions self-hosted 러너들에 CI 유지보수를 멱등 배선.

**두 축을 배선한다**(둘 다 멱등·재무장, VM 마다 1회):
  (A) job-completed prune 훅 — CI `services:` 컨테이너의 익명 docker 볼륨 누수 회수.
  (B) serve-stale 포워딩 리졸버(unbound) — 호스트 Wi-Fi uplink 블립 시 checkout 이
      codeload 를 못 찾아 실패하는 egress 트랜션트를 완화(R2, 2026-09-11).

**(A) 무엇을**: ① 플러그인의 `ci-runner/job-completed-prune.sh` 를 VM 의 `$HOME/.dw-runner-hooks/`
로 복사(755) ② VM 안 systemd 유닛(`actions.runner.*.service`)을 자동 탐지해 각 러너 디렉토리의
`.env` 에 `ACTIONS_RUNNER_HOOK_JOB_COMPLETED=<그 경로>` 를 멱등 upsert(같으면 no-op·다르면 교체·
없으면 append).

**(B) 무엇을**: ① unbound 설치(guard: 이미 있으면 SKIP) ② root.key 시드(unbound-helper, 멱등)
③ `ci-runner/serve-stale-resolver.conf` 를 `/etc/unbound/unbound.conf.d/zz-dw-ci-resolver.conf`
로 설치(`zz-` = include-toplevel 병합 마지막 → 패키지 기본값 덮음) ④ `unbound-checkconf` 로
검증(실패 시 드롭인 롤백 + resolv.conf 미변경 — 안전) ⑤ 재무장 스크립트/유닛
(`dw-resolv-repoint.sh`·`.service`)을 설치·enable(만일 OrbStack 가 부팅 시 resolv.conf 심링크를
다시 쓰면 대비해 부팅마다 127.0.0.1 로 재지정 — 실측상 부팅 재생성은 미확인, belt-and-suspenders)
⑥ unbound 헬스체크(active + :53 listen) 통과 시에만 resolv.conf 를 즉시 재지정. 리졸버는
「러너 재시작」이 아니라 「VM 부팅」에 재무장된다(별 축).

🔴 설계 근거(로컬 unbound 1.19 시뮬 실측): serve-expired 는 상류 «실패»(타임아웃/SERVFAIL)에만
발동하고 NXDOMAIN 은 정상응답이라 그대로 통과한다. OrbStack 프록시는 블립을 NXDOMAIN 으로
번역하므로, `.` 존은 프록시를 «우회»해 퍼블릭 리졸버로 보낸다(블립 때 정직하게 타임아웃 →
serve-expired 발동). `orb.local` 만 프록시 유지. 상세는 serve-stale-resolver.conf 헤더 참조.

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
표준 라이브러리만 사용. dw-ci·dw-deploy **둘 다** 배선해야 한다(VM 마다 1회).
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

# ── (B) serve-stale 포워딩 리졸버 payload/경로 (R2: egress 트랜션트 완화) ─────────────
RESOLVER_CONF_SRC = ROOT / "ci-runner" / "serve-stale-resolver.conf"
RESOLVER_CONF_DST = "/etc/unbound/unbound.conf.d/zz-dw-ci-resolver.conf"
REPOINT_SRC = ROOT / "ci-runner" / "dw-resolv-repoint.sh"
REPOINT_DST = "/usr/local/sbin/dw-resolv-repoint"
REPOINT_UNIT_SRC = ROOT / "ci-runner" / "dw-resolv-repoint.service"
REPOINT_UNIT_DST = "/etc/systemd/system/dw-resolv-repoint.service"
REPOINT_UNIT_NAME = "dw-resolv-repoint.service"
UNBOUND_HELPER = "/usr/libexec/unbound-helper"   # root.key 시드(패키지 unbound.service ExecStartPre 와 동일 경로)
APT_TIMEOUT = 300                                # apt-get install 은 기본 120s 를 넘을 수 있다

# 127.0.0.1(unbound)에 «직접» 질의하는 판별검사 — getent 는 폴백 nameserver 로 성공해 unbound 가
# 답했는지 증명 못 하므로 raw UDP 로 로컬 리졸버를 직접 때린다(unbound 사망 시 ECONNREFUSED → 예외).
# 표준 라이브러리만. stdin 으로 파이프해 실행한다.
_DIRECT_QUERY_PY = r'''
import socket, struct
def q(server, name, timeout=3.0):
    hdr = struct.pack(">HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0)
    qd = b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00" + struct.pack(">HH", 1, 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(timeout)
    try:
        s.sendto(hdr + qd, (server, 53)); data, _ = s.recvfrom(4096)
        return (data[3] & 0x0f), struct.unpack(">H", data[6:8])[0]
    finally:
        s.close()
try:
    rc, an = q("127.0.0.1", "github.com")
    print("rc=%d an=%d" % (rc, an))
    print("DIRECT_OK" if rc == 0 and an >= 1 else "DIRECT_FAIL")
except Exception as e:
    print("DIRECT_FAIL %s: %s" % (type(e).__name__, e))
'''


class VM:
    """orbctl 로 접근하는 OrbStack VM 핸들. 명령은 VM 사용자(로그인 셸)로 돈다."""

    def __init__(self, machine: str) -> None:
        self.machine = machine

    def sh(self, script: str, stdin: str | None = None,
           timeout: int = 120) -> subprocess.CompletedProcess:
        _flush()
        return subprocess.run(["orbctl", "run", "-m", self.machine, "bash", "-lc", script],
                              input=stdin, capture_output=True, text=True, timeout=timeout)


def _flush() -> None:
    sys.stdout.flush()
    sys.stderr.flush()


def preflight(vm: VM) -> str | None:
    """orbctl·VM·모든 payload 소스 가용성 확인. 문제 있으면 사람이 읽을 사유 문자열 반환."""
    for src in (HOOK_SRC, RESOLVER_CONF_SRC, REPOINT_SRC, REPOINT_UNIT_SRC):
        if not src.is_file():
            return f"payload 소스 없음: {src}"
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


# ── (B) serve-stale 포워딩 리졸버 배선 ────────────────────────────────────────────────

def _install_sudo_file(vm: VM, src: Path, dst: str, mode: str) -> tuple[bool, str]:
    """payload 를 VM 의 sudo 경로(/etc·/usr/local)로 설치. 내용비교로 SKIP/CHANGED 판정.

    소스를 stdin 으로 파이프(공유 FS 비의존) → 사용자 쓰기가능 tmp 로 받고 → 같으면 no-op,
    다르면 `sudo -n install -m<mode>` 로 원자적 반영. `install` 은 존재하지 않는 상위 dir 을
    만들지 않으므로(드롭인 dir 은 unbound 패키지가 만든다) 실패는 시끄럽게 보고한다.
    반환 상태 문자열은 "SKIP"(무변경) | "CHANGED"(반영).
    """
    text = src.read_text(encoding="utf-8")
    tmp = f"/tmp/dw-wire.{Path(dst).name}.$$"
    script = (
        f'cat > "{tmp}" && '
        f'if [ -f "{dst}" ] && cmp -s "{tmp}" "{dst}"; then rm -f "{tmp}"; echo SKIP; '
        f'else sudo -n install -m {mode} "{tmp}" "{dst}" && rm -f "{tmp}" && echo CHANGED '
        f'|| {{ rm -f "{tmp}"; echo INSTALL_FAIL; }}; fi'
    )
    r = vm.sh(script, stdin=text)
    state = (r.stdout or "").strip().splitlines()[-1] if r.stdout.strip() else ""
    if r.returncode != 0 or state not in ("SKIP", "CHANGED"):
        return False, f"{dst}: 설치 실패 — {(r.stderr or r.stdout).strip()[:200]}"
    return True, state


def _unbound_healthy(vm: VM) -> bool:
    """unbound 가 active 이고 127.0.0.1:53 에서 listen 중인지 — resolv.conf 재지정 전 안전 게이트.

    resolv.conf 를 죽은 리졸버로 가리키면 VM 전체 DNS 가 끊긴다. 그래서 «살아있음»을 확인한
    뒤에만 재지정한다(그리고 재지정 후에도 폴백 nameserver 로 프록시를 남긴다).
    """
    r = vm.sh('a=$(systemctl is-active unbound 2>/dev/null); '
              'l=$(ss -H -lun 2>/dev/null | grep -c "127.0.0.1:53"); '
              'echo "$a $l"')
    parts = (r.stdout or "").strip().split()
    return len(parts) == 2 and parts[0] == "active" and parts[1] != "0"


def wire_resolver(vm: VM, dry_run: bool) -> tuple[bool, list[str]]:
    """serve-stale 포워딩 리졸버(unbound)를 멱등 배선 + 부팅 재무장 + 즉시 재지정.

    반환 `(ok, msgs)`. 실패해도 prune-훅 축과 독립 — main 의 failed 리스트에 합류한다.
    dry-run 은 **읽기전용**(apt·/etc·systemctl write 없음).
    """
    if dry_run:
        # 읽기전용 상태 조회. 따옴표 지옥을 피하려 각 줄을 독립 명령으로 둔다.
        script = "\n".join([
            'printf "unbound: "; dpkg -s unbound >/dev/null 2>&1 && echo INSTALLED || echo ABSENT',
            'printf "resolv symlink -> "; readlink -f /etc/resolv.conf 2>/dev/null || echo "(none)"',
            'printf "resolv nameservers: "; grep -E "^nameserver" /etc/resolv.conf 2>/dev/null | tr "\\n" " "; echo',
            f'printf "dropin: "; test -f {RESOLVER_CONF_DST} && echo present || echo absent',
            f'printf "repoint unit: "; systemctl is-enabled {REPOINT_UNIT_NAME} 2>/dev/null; true',
            'printf "unbound active: "; systemctl is-active unbound 2>/dev/null; true',
        ])
        r = vm.sh(script)
        body = (r.stdout or "").strip().replace("\n", "\n      ")
        return True, ["(dry-run) 리졸버 현재 상태:\n      " + body]

    msgs: list[str] = []

    # ① unbound 설치 (guard). apt 는 긴 timeout.
    chk = vm.sh('dpkg -s unbound >/dev/null 2>&1 && echo INSTALLED || echo ABSENT')
    if "INSTALLED" not in (chk.stdout or ""):
        inst = vm.sh('sudo -n DEBIAN_FRONTEND=noninteractive apt-get update -qq && '
                     'sudo -n DEBIAN_FRONTEND=noninteractive apt-get install -y -qq unbound',
                     timeout=APT_TIMEOUT)
        if inst.returncode != 0:
            return False, [f"unbound 설치 실패: {(inst.stderr or inst.stdout).strip()[:200]}"]
        msgs.append("unbound 설치")
    else:
        msgs.append("unbound 이미 설치됨(SKIP)")

    # ② root.key 시드 (패키지 unbound.service ExecStartPre 와 동일; 멱등, 실패 무시).
    #    이게 없으면 root-auto-trust-anchor-file.conf 때문에 checkconf 가 FATAL 난다.
    vm.sh(f'sudo -n {UNBOUND_HELPER} root_trust_anchor_update >/dev/null 2>&1 || true')

    # ③ 드롭인 설치. checkconf 실패 대비 기존 파일을 백업(없으면 «부재»로 기록)해 롤백 가능케 한다.
    bak = f"{RESOLVER_CONF_DST}.dw-bak"
    vm.sh(f'if [ -f "{RESOLVER_CONF_DST}" ]; then sudo -n cp -p "{RESOLVER_CONF_DST}" "{bak}"; '
          f'else sudo -n rm -f "{bak}"; fi')
    ok, st = _install_sudo_file(vm, RESOLVER_CONF_SRC, RESOLVER_CONF_DST, "0644")
    if not ok:
        vm.sh(f'sudo -n rm -f "{bak}"')   # 설치 실패 경로에서도 백업 잔재 남기지 않는다.
        return False, [st]
    conf_changed = (st == "CHANGED")
    msgs.append(f"드롭인 {RESOLVER_CONF_DST}: {st}")

    # ④ checkconf — 실패 시 방금 설치한 드롭인을 «롤백»(백업 복원 or 제거)하고 중단. 깨진 드롭인을
    #    디스크에 남기면 resolv.conf 는 이미 127.0.0.1 인데 다음 unbound 재시작(재부팅·패키지 업글)에서
    #    기동 실패 → serve-stale 이 조용히 사라진다. 롤백으로 그 시한폭탄을 없앤다.
    cc = vm.sh('sudo -n unbound-checkconf 2>&1')
    if cc.returncode != 0:
        vm.sh(f'if [ -f "{bak}" ]; then sudo -n mv "{bak}" "{RESOLVER_CONF_DST}"; '
              f'else sudo -n rm -f "{RESOLVER_CONF_DST}"; fi')
        return False, [f"unbound-checkconf 실패 — 드롭인 롤백·resolv.conf 미변경(안전): {(cc.stdout or cc.stderr).strip()[:300]}"]
    vm.sh(f'sudo -n rm -f "{bak}"')   # 통과 — 백업 제거.
    msgs.append("unbound-checkconf: OK")

    # ⑤ 재무장 스크립트 + systemd 유닛 설치.
    ok, st1 = _install_sudo_file(vm, REPOINT_SRC, REPOINT_DST, "0755")
    if not ok:
        return False, [st1]
    ok, st2 = _install_sudo_file(vm, REPOINT_UNIT_SRC, REPOINT_UNIT_DST, "0644")
    if not ok:
        return False, [st2]
    unit_changed = (st2 == "CHANGED")
    msgs.append(f"재무장 스크립트 {REPOINT_DST}: {st1} · 유닛 {REPOINT_UNIT_NAME}: {st2}")

    # ⑥ daemon-reload(유닛 변경 시) · 유닛 enable · unbound enable+(변경 시)restart.
    if unit_changed:
        vm.sh('sudo -n systemctl daemon-reload')
    en = vm.sh(f'sudo -n systemctl enable {REPOINT_UNIT_NAME} >/dev/null 2>&1 && echo OK || echo FAIL')
    if "OK" not in (en.stdout or ""):
        return False, [f"{REPOINT_UNIT_NAME} enable 실패 — {(en.stderr or en.stdout).strip()[:200]}"]
    ube = vm.sh('sudo -n systemctl enable unbound >/dev/null 2>&1; '
                + ('sudo -n systemctl restart unbound 2>&1; ' if conf_changed else
                   'sudo -n systemctl start unbound 2>&1; ')
                + 'sleep 1; systemctl is-active unbound 2>/dev/null')
    msgs.append(f"unbound {'restart' if conf_changed else 'start'}·enable · repoint 유닛 enable")

    # ⑦ 헬스체크 — 살아있을 때만 재지정.
    if not _unbound_healthy(vm):
        return False, ["unbound 헬스체크 실패(active/:53 listen) — resolv.conf 재지정 생략(안전). "
                       f"is-active 출력: {(ube.stdout or '').strip()[:120]}"]
    msgs.append("unbound 헬스체크: active + 127.0.0.1:53 listen")

    # ⑧ 즉시 재지정(부팅 재무장은 유닛이, 지금 즉시분은 이 호출이).
    rp = vm.sh(f'sudo -n {REPOINT_DST} 2>&1')
    if rp.returncode != 0:
        return False, [f"resolv.conf 재지정 실패 — {(rp.stderr or rp.stdout).strip()[:200]}"]
    msgs.append(f"resolv.conf 재지정: {(rp.stdout or '').strip().splitlines()[-1] if rp.stdout.strip() else 'done'}")

    # ⑨ 최종 검증: 127.0.0.1(unbound)에 «직접» 질의. getent 는 폴백(0.250.250.200)으로도 성공해
    #    unbound 가 실제로 답했는지 증명 못 하므로 raw UDP 로 로컬 리졸버를 직접 때린다.
    vf = vm.sh('python3 -', stdin=_DIRECT_QUERY_PY)
    if "DIRECT_OK" not in (vf.stdout or ""):
        return False, [f"최종 직접검증 실패 — 127.0.0.1 이 github.com 을 답하지 못함: "
                       f"{(vf.stdout or vf.stderr).strip().splitlines()[-1] if (vf.stdout or vf.stderr).strip() else '(무응답)'}. "
                       "폴백 nameserver 로 VM DNS 는 유지되나 리졸버 경로 재점검 필요."]
    detail = [ln for ln in (vf.stdout or "").splitlines() if ln.startswith("rc=")]
    msgs.append(f"최종 검증: 127.0.0.1 직접질의 DIRECT_OK ({detail[0] if detail else ''})")
    return True, msgs


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

    # ── (B) serve-stale 포워딩 리졸버 (러너 무관 · VM 레벨 1회) ─────────────────────
    print(f"[wire-ci] serve-stale 포워딩 리졸버 배선{' (dry-run)' if args.dry_run else ''}:")
    good, rmsgs = wire_resolver(vm, args.dry_run)
    for m in rmsgs:
        print(f"  {'✓' if good else '✗'} {m}")
    if not good:
        failed.extend(rmsgs)
    elif not args.dry_run:
        print("[wire-ci] 리졸버 재무장 유닛 enable — 부팅 시 resolv.conf 를 127.0.0.1 로 재지정(만일 "
              "OrbStack 가 심링크를 다시 쓰면 대비; 실측상 부팅 재생성 미확인).")

    if failed:
        print(f"[wire-ci] 실패 {len(failed)}건 — 위 참조", file=sys.stderr)
        return 1
    print("[wire-ci] 완료.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
