#!/usr/bin/env python3
"""dw 토큰 미터 — 비파괴 Stop/SubagentStop 훅. 트랜스크립트를 «증분» 파싱해 실토큰을 센다.

기존 텔레메트리(`dw-telemetry.py`)는 PostToolUse 기반이라 못 잡는 게 있다:
  - advisor·grep 은 tool_input 만 보고 «횟수» 만 세고 토큰은 0 으로 남는다.
  - do-er 서브에이전트(Task)는 부모 세션의 PostToolUse 로는 «내부» 호출이 안 잡힌다.
  - 애초에 «실토큰» 자체가 없다(PostToolUse payload 엔 usage 가 없다).

이 훅은 그 빈자리를 트랜스크립트 파싱으로 닫는다. Stop(메인 턴 종료)·SubagentStop(서브에이전트
종료) 에서 payload 의 `transcript_path` 를 열어, 지난번 이후 «새 줄만» 읽어 어시스턴트 턴의
`message.usage`(실토큰) + tool_use/server_tool_use 블록(advisor·grep 포함 전부)을 집계한다.

■ 실측으로 확정한 스키마 (2026-09-09, `~/.claude/projects/*/*.jsonl`)
  1. 어시스턴트 응답 1개가 «블록 수만큼» 여러 `type:assistant` 줄로 쪼개져 기록된다. 각 줄이
     같은 `message.id` + «동일한» usage 사본을 든다(실측: 1663줄 / 650 id, 같은 id 안에서
     output_tokens 변동 0). ⇒ **usage 는 message.id 당 «한 번만» 센다**(줄마다 더하면 ~2.5배
     과대). tool_use 블록은 줄마다 «다른» 블록이므로 줄마다 센다(dedup 안 함).
     Stop 은 턴 «완료 후» 발화하므로 한 message 의 블록들이 offset 경계를 가로지르지 않는다 —
     이 가정 위에서만 message.id 당 1회 집계가 안전하다.
  2. advisor 는 `type:"tool_use"` 가 아니라 `type:"server_tool_use"` 블록(name="advisor")으로
     기록된다. ⇒ **두 블록 타입을 «둘 다» 센다**(안 그러면 advisor 가 영영 0 — 이 훅의 존재 이유).
  3. 서브에이전트 트랜스크립트는 부모와 «별 파일»(`<session>/subagents/agent-*.jsonl`)에 살고
     모든 줄이 `isSidechain:true` + top-level `attributionAgent`(=do-er 유형: senior-*·Explore·
     code-review …)를 든다. ⇒ source 를 줄 단위 `isSidechain`+`attributionAgent` 로 판별하면
     별파일(FleetView)·인라인 sidechain 두 저장모델을 «둘 다» 커버한다. hook_event_name 은 폴백.
  4. offset 을 transcript_path 로 키잉하므로 SubagentStop 이 부모 것을 주든 서브 전용을 주든
     안전하다(어느 쪽이든 «그 경로의» 새 줄만 소비·중복집계 0).

설계 원칙(telemetry 와 동일): 훅은 결코 턴을 막지 않는다(항상 exit 0, 모든 예외 삼킴).
vault CONTENT_DIRS 밖(.dw-state/)에만 기록. 표준 라이브러리만.

동시성: 병렬 서브에이전트가 거의 동시에 끝나면 여러 프로세스가 같은 offset 을 읽어 같은 줄을
집계·append 할 수 있다. read-offset→parse→append→write-offset 임계구역을 `.dw-state/` 락 파일의
`fcntl.flock` 으로 감싼다. offset 파일은 tmp+os.replace 로 원자적 교체. 트렁케이션(파일이 저장
offset 보다 작아짐) 시 offset 을 0 으로 리셋.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from collections import Counter
from pathlib import Path

import dw_runtime

try:
    import fcntl  # POSIX only — 훅은 macOS/linux 러너에서만 돈다
except Exception:  # pragma: no cover - 방어(윈도우 등)
    fcntl = None


def _vault_root(project: Path):
    """vault 위치 — 정본은 `dw_runtime.find_vault`(telemetry 와 동일 규약). 없으면 None(no-op)."""
    return dw_runtime.find_vault(project, require="dir", ancestors=8, git_probe=True,
                                 self_repo_fallback=True)


def classify_source(obj: dict, hook_event_name: str) -> str:
    """어시스턴트 줄의 source 를 판별. main | subagent:<type>.

    1순위: 줄 자체의 `isSidechain`(별파일·인라인 두 저장모델 공통) + `attributionAgent`(do-er 유형).
    폴백: payload 의 hook_event_name 이 SubagentStop 이면 서브에이전트로 본다(isSidechain 부재 대비).
    """
    if obj.get("isSidechain") is True:
        t = str(obj.get("attributionAgent") or "unknown").strip() or "unknown"
        return "subagent:" + t
    if hook_event_name == "SubagentStop":
        t = str(obj.get("attributionAgent") or "unknown").strip() or "unknown"
        return "subagent:" + t
    return "main"


# usage 키 → 우리 레코드 필드. 실측 필드명 그대로(2026-09-09 확인).
_USAGE_MAP = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cache_read": "cache_read_input_tokens",
    "cache_creation": "cache_creation_input_tokens",
}


def _bucket():
    return {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0,
            "tools": Counter(), "seen_ids": set()}


def parse_lines(lines, hook_event_name: str) -> dict:
    """새 줄들을 source 별 델타로 집계. {source: {input,output,cache_read,cache_creation,tools:Counter}}.

    - usage: (source, message.id) 당 «한 번만» 더한다(같은 응답의 블록-줄이 usage 를 복제하므로).
    - tool_use / server_tool_use: 블록마다 name 별 카운트(advisor=server_tool_use 포함).
    - 빈 줄·깨진 JSON·usage 없는 줄은 조용히 건너뛴다.
    """
    buckets: dict[str, dict] = {}
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        if not isinstance(obj, dict) or obj.get("type") != "assistant":
            continue
        msg = obj.get("message") or {}
        if not isinstance(msg, dict):
            continue
        src = classify_source(obj, hook_event_name)
        b = buckets.get(src)
        if b is None:
            b = buckets[src] = _bucket()

        content = msg.get("content")
        if isinstance(content, list):
            for blk in content:
                if isinstance(blk, dict) and blk.get("type") in ("tool_use", "server_tool_use"):
                    name = str(blk.get("name") or "").strip()
                    if name:
                        b["tools"][name] += 1

        mid = msg.get("id")
        if mid is not None and mid in b["seen_ids"]:
            continue  # 같은 응답의 다른 블록-줄 — usage 는 이미 셌다
        if mid is not None:
            b["seen_ids"].add(mid)
        usage = msg.get("usage")
        if isinstance(usage, dict):
            for field, key in _USAGE_MAP.items():
                v = usage.get(key)
                if isinstance(v, int):
                    b[field] += v
    return buckets


def _read_new_bytes(path: str, stored_offset: int):
    """(new_lines, new_offset) 반환. 완결된 줄(마지막 개행까지)만 소비 — 부분 줄 재읽기 방지.

    바이트 offset 을 정확히 유지하려고 바이너리로 연다. 트렁케이션(size<stored) 시 0 부터.
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return [], stored_offset
    if size < stored_offset:  # 파일이 줄었다(로테이션/트렁케이트) → 처음부터
        stored_offset = 0
    if size <= stored_offset:
        return [], stored_offset
    with open(path, "rb") as f:
        f.seek(stored_offset)
        data = f.read()
    last_nl = data.rfind(b"\n")
    if last_nl < 0:
        return [], stored_offset  # 완결된 줄 없음 — 다음 호출에서 다시
    consumed = data[:last_nl + 1]
    new_offset = stored_offset + len(consumed)
    lines = consumed.decode("utf-8", "ignore").split("\n")
    return lines, new_offset


def _load_offsets(state_dir: Path) -> dict:
    p = state_dir / "token_offsets.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_offsets(state_dir: Path, offsets: dict) -> None:
    p = state_dir / "token_offsets.json"
    tmp = state_dir / "token_offsets.json.tmp"
    tmp.write_text(json.dumps(offsets, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)  # 원자적 교체


def process(transcript_path: str, hook_event_name: str, session: str, state_dir: Path) -> list:
    """임계구역: offset 로드 → 증분 파싱 → tokens.jsonl append → offset 저장. 델타 레코드 목록 반환.

    반환은 테스트·관측용(파일에 쓴 것과 동일). 데이터 없는 source 는 레코드로 남기지 않는다.
    """
    offsets = _load_offsets(state_dir)
    stored = int(offsets.get(transcript_path, 0) or 0)
    lines, new_offset = _read_new_bytes(transcript_path, stored)
    buckets = parse_lines(lines, hook_event_name)

    ts = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    records = []
    for src, b in buckets.items():
        tools = dict(b["tools"])
        if not (b["input"] or b["output"] or b["cache_read"] or b["cache_creation"] or tools):
            continue
        records.append({
            "ts": ts,
            "session": session,
            "source": src,
            "input": b["input"],
            "output": b["output"],
            "cache_read": b["cache_read"],
            "cache_creation": b["cache_creation"],
            "tool_uses": tools,
        })

    if records:
        with open(state_dir / "tokens.jsonl", "a", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    offsets[transcript_path] = new_offset
    _save_offsets(state_dir, offsets)
    return records


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        transcript_path = payload.get("transcript_path") or ""
        if not transcript_path or not os.path.isfile(transcript_path):
            return 0
        hook_event_name = payload.get("hook_event_name") or ""
        session = payload.get("session_id") or ""

        project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())
        vault = _vault_root(project)
        if vault is None:
            return 0
        state_dir = vault.resolve() / ".dw-state"
        state_dir.mkdir(exist_ok=True)

        lock_path = state_dir / "token_meter.lock"
        if fcntl is not None:
            with open(lock_path, "w") as lk:
                fcntl.flock(lk, fcntl.LOCK_EX)
                try:
                    process(transcript_path, hook_event_name, session, state_dir)
                finally:
                    fcntl.flock(lk, fcntl.LOCK_UN)
        else:  # pragma: no cover - 비POSIX 폴백(락 없이)
            process(transcript_path, hook_event_name, session, state_dir)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
