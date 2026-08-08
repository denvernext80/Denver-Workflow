#!/usr/bin/env python3
"""세션 시작 시 자동 비준 — Claude Code SessionStart 훅.

**왜 이 시점인가.** 승격은 제안한 에이전트의 턴 **밖**에서 일어나야 한다(규칙은 다른
에이전트의 게이트를 규율한다 — 제안자가 자기 규칙을 그 자리에서 강제로 만들면 경계가 무너진다).
그리고 승격 결과가 실제로 필요해지는 순간은 **다음 세션이 컴파일 산출물을 읽는 바로 그때**다.
호스트 스케줄러(launchd/cron/Task Scheduler)를 쓰지 않는 이유: 이 플러그인의 훅은 전부
`python3 <script>` 형태의 **플랫폼 중립**이고, 스케줄러를 정본으로 삼으면 OS 의존이 새로 생긴다.

**예산 규율(SessionStart 훅 timeout=15s).** 세션 시작을 느리게 하거나 막지 않는다:
  1) draft 유무를 먼저 값싸게 본다(200 노트 0.013s 실측 — 헤더 400바이트만 읽는다).
     draft 0 이고 산출물이 최신이면 **아무 것도 하지 않고 끝난다**(대부분의 세션).
  2) draft 가 있으면 비준을 돌린다(0.07s). **승격이 있을 때만** 등록 레포 전체에 설치한다.
  3) 승격이 없고 이 레포 산출물만 낡았으면 **이 레포 하나만** 설치한다(0.56s).
  4) 어떤 예외도 세션을 막지 않는다 — 전부 삼키고 exit 0. 단 **조용히 죽지는 않는다**:
     결과를 additionalContext(모델이 본다) + 로그 파일 양쪽에 남긴다.

stdin: 훅 JSON. stdout: SessionStart additionalContext(있을 때만). 항상 exit 0.
표준 라이브러리만 사용.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import dw_runtime

BUILD = Path(__file__).resolve().parent
OBEY_DIRS = ("governance/rules", "governance/guidance", "governance/procedures")
HEAD_BYTES = 400          # status 는 프론트매터 머리에 있다 — 전문을 읽지 않는다
LOG_MAX_BYTES = 1_000_000  # 넘으면 .1 로 1세대 회전(상한 ≈ 2MB, 과설계 회피)
BUDGET_S = 11.0            # 훅 timeout 15s 보다 짧게 — 초과 시 설치를 다음 세션으로 넘긴다


def _log(vault: Path, line: str) -> None:
    """`<vault>/.dw-state/ratify.log` 에 append(+1세대 회전). 실패는 무시(로깅이 세션을 막지 않는다)."""
    try:
        d = vault / ".dw-state"
        d.mkdir(parents=True, exist_ok=True)
        f = d / "ratify.log"
        if f.exists() and f.stat().st_size > LOG_MAX_BYTES:
            f.replace(d / "ratify.log.1")
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with f.open("a", encoding="utf-8") as fh:
            fh.write(f"[{stamp}] {line}\n")
    except OSError:
        pass


def _resolve_vault(payload: dict) -> Path | None:
    """vault 위치 — 정본은 `dw_runtime.find_vault`(2.16.0). 없으면 None(비준을 건너뛴다).

    이 호출자만의 두 가지를 **파라미터로 보존**한다:
      * `require="governance"` — 폴더 존재만으로는 부족하다(비준은 `governance/` 를 읽는다).
      * `ancestors=1` — 종전부터 조상 탐색을 하지 않는다. 가드와 같은 8 로 올리면 워크트리에서
        조상 config 를 새로 보게 되는 **행동 변경**이라, "일관성" 을 이유로 바꾸지 않는다.
    """
    return dw_runtime.find_vault(_project_dir(payload), require="governance",
                                 ancestors=1, git_probe=False)


def _project_dir(payload: dict) -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())


def _draft_count(vault: Path) -> int:
    """OBEY draft 개수 — 헤더만 읽는 값싼 스캔."""
    n = 0
    for d in OBEY_DIRS:
        base = vault / d
        if not base.is_dir():
            continue
        for p in base.rglob("*.md"):
            if "archive" in p.relative_to(base).parts:
                continue
            try:
                with p.open("rb") as fh:
                    head = fh.read(HEAD_BYTES)
            except OSError:
                continue
            if re.search(rb"^status:\s*draft\s*$", head, re.MULTILINE):
                n += 1
    return n


def _vault_mtime(vault: Path) -> float:
    newest = 0.0
    for d in OBEY_DIRS + ("governance/_skills", "governance/agents"):
        base = vault / d
        if not base.is_dir():
            continue
        for p in base.rglob("*.md"):
            try:
                newest = max(newest, p.stat().st_mtime)
            except OSError:
                continue
    return newest


def _is_stale(project: Path, vault_mtime: float) -> bool:
    """이 레포의 설치 산출물이 vault 보다 낡았나(사람이 Obsidian 에서 stable 을 고친 경우 포함)."""
    marker = project / ".claude" / "dw-checks.json"
    if not marker.is_file():
        return False   # dw 설치본이 아닌 레포 — 우리가 손댈 곳이 아니다
    try:
        return marker.stat().st_mtime < vault_mtime
    except OSError:
        return False


def _run(cmd: list[str], timeout: float) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except (OSError, subprocess.SubprocessError) as e:
        return 1, f"{type(e).__name__}: {e}"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    vault = _resolve_vault(payload)
    if vault is None:
        return 0  # vault 없음 — 이 훅이 할 일이 없다(세션은 그대로 진행)

    import time
    t0 = time.monotonic()
    project = _project_dir(payload)
    notes: list[str] = []

    drafts = _draft_count(vault)
    vmtime = _vault_mtime(vault)
    stale = _is_stale(project, vmtime)

    if drafts == 0 and not stale:
        _log(vault, f"draft 0 · 산출물 최신 → 무작업 ({time.monotonic()-t0:.3f}s) [{project.name}]")
        return 0

    promoted = held = 0
    if drafts:
        rc, out = _run([sys.executable, str(BUILD / "dw-ratify.py"), "--vault", str(vault)],
                       timeout=max(2.0, BUDGET_S - (time.monotonic() - t0)))
        m = re.search(r"승격\(draft→stable\)\s*(\d+)건", out)
        promoted = int(m.group(1)) if m else 0
        m = re.search(r"hold\(판단 필요, draft 유지\)\s*(\d+)건", out)
        held = int(m.group(1)) if m else 0
        if rc not in (0, 10):
            notes.append(f"⚠️ 비준기 비정상 종료(exit={rc}) — 승격이 반영되지 않았을 수 있다")
            _log(vault, f"비준기 exit={rc} :: {out.strip()[-300:]}")
        else:
            _log(vault, f"비준: draft {drafts} → 승격 {promoted} · hold {held} [{project.name}]")
        if held:
            notes.append(f"비준 hold {held}건 — 판단이 필요하다(`/dw-review` 로 사유 확인)")

    # 설치: 승격이 있었으면 등록 레포 전체, 아니면 낡은 이 레포만.
    left = BUDGET_S - (time.monotonic() - t0)
    if promoted and left > 1.0:
        rc, out = _run([sys.executable, str(BUILD / "dw-install-registered.py"),
                        "--vault", str(vault), "--quiet"], timeout=left)
        _log(vault, f"설치(승격 {promoted}건 전파): exit={rc} :: {out.strip()[-300:]}")
        notes.append(f"규칙 {promoted}건이 승격돼 등록 레포에 설치했다"
                     + (" (일부 실패 — 로그 확인)" if rc != 0 else ""))
    elif stale and left > 1.0:
        rc, out = _run([sys.executable, str(BUILD / "dw-install-registered.py"),
                        "--vault", str(vault), "--project", str(project), "--quiet"], timeout=left)
        _log(vault, f"설치(이 레포 산출물 갱신): exit={rc} [{project.name}] :: {out.strip()[-200:]}")
        if rc != 0:
            notes.append("⚠️ 이 레포 산출물 갱신 실패 — `/dw-install` 로 수동 설치하라")
    elif (promoted or stale) and left <= 1.0:
        _log(vault, f"예산 초과({time.monotonic()-t0:.1f}s) — 설치를 다음 세션으로 넘김")
        notes.append("비준 예산 초과로 설치를 건너뛰었다 — `/dw-install` 로 수동 설치하라")

    if notes:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "[dw 자동 비준] " + " / ".join(notes),
        }}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # 어떤 예외도 세션 시작을 막지 않는다 — 다만 흔적은 남긴다
        try:
            sys.stderr.write(f"[dw-ratify-session] 무시된 예외: {type(e).__name__}: {e}\n")
        except Exception:
            pass
        sys.exit(0)
