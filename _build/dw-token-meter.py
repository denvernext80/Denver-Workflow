#!/usr/bin/env python3
"""dw 토큰 미터 — 비파괴 Stop/SubagentStop 훅. 트랜스크립트를 «증분» 파싱해 실토큰을 센다.

기존 텔레메트리(`dw-telemetry.py`)는 PostToolUse 기반이라 못 잡는 게 있다:
  - advisor·grep 은 tool_input 만 보고 «횟수» 만 세고 토큰은 0 으로 남는다.
  - do-er 서브에이전트(Task)는 부모 세션의 PostToolUse 로는 «내부» 호출이 안 잡힌다.
  - 애초에 «실토큰» 자체가 없다(PostToolUse payload 엔 usage 가 없다).

이 훅은 그 빈자리를 트랜스크립트 파싱으로 닫는다. Stop(메인 턴 종료)·SubagentStop(서브에이전트
종료) 에서 payload 의 `transcript_path` 를 열어, 지난번 이후 «새 줄만» 읽어 어시스턴트 턴의
`message.usage`(실토큰) + tool_use/server_tool_use 블록(advisor·grep 포함 전부)을 집계한다.

■ 부가 산출(2.25.0) — 서브에이전트 vault-노트 read 캡처
  같은 파싱 패스에서 isSidechain:true 줄의 «읽기 도구» target 이 tracked 노트(procedures·memory)로
  해석되면 access.jsonl 에 dw-telemetry 와 «동일 스키마»로 emit 한다. access.jsonl(PostToolUse)은
  서브에이전트 내부 read 를 못 봐서 do-er 가 읽은 플레이북이 never-read 로 오판되던 것을 고친다.
  토큰 집계(tokens.jsonl)는 «그대로» — 추가 산출일 뿐 기존 동작 불변. 판정·이중집계·프라이버시
  규율은 아래 read-capture 헬퍼 블록 주석 참조.

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
  5. 🔴 견고화(payload 비의존): SubagentStop 때 payload 의 transcript_path «값»에 do-er 커버리지가
     걸리면 안 된다(부모 경로를 주면 서브 토큰이 영영 0). 그래서 그 경로에서 서브에이전트 디렉토리를
     «직접 도출»(`subagents_dir_for`) 해 `<session>/subagents/*.jsonl` 을 전부 대상에 넣는다 —
     payload 가 부모를 주든 서브를 주든 같은 집합을 훑는다. 각 파일은 여전히 경로별 offset 증분이라
     중복집계 0, 실행 중인 다른 서브의 부분 파일도 완결줄만 소비돼 안전. glob 은 offset 덕에 대개
     0 새바이트라 값싸다.

설계 원칙(telemetry 와 동일): 훅은 결코 턴을 막지 않는다(항상 exit 0, 모든 예외 삼킴).
vault CONTENT_DIRS 밖(.dw-state/)에만 기록. 표준 라이브러리만.

동시성: 병렬 서브에이전트가 거의 동시에 끝나면 여러 프로세스가 같은 offset 을 읽어 같은 줄을
집계·append 할 수 있다. read-offset→parse→append→write-offset 임계구역을 `.dw-state/` 락 파일의
`fcntl.flock` 으로 감싼다. offset 파일은 tmp+os.replace 로 원자적 교체. 트렁케이션(파일이 저장
offset 보다 작아짐) 시 offset 을 0 으로 리셋.
"""
from __future__ import annotations

import datetime
import glob
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
    True→subagent, False→main(«명시적» — 견고화로 SubagentStop 때 부모 트랜스크립트도 함께 처리하니
    부모의 main 줄을 폴백이 삼키면 안 된다). isSidechain «부재»(None)일 때만 hook_event_name 폴백.
    """
    sc = obj.get("isSidechain")
    if sc is True:
        t = str(obj.get("attributionAgent") or "unknown").strip() or "unknown"
        return "subagent:" + t
    if sc is False:
        return "main"
    # isSidechain 부재 → 폴백: SubagentStop 이면 서브에이전트로 본다
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


# ─────────────────────────────────────────────────────────────────────────────
# 서브에이전트 vault-노트 read 캡처 (never-read 재사용 지표 교란 해소)
#
# access.jsonl(dw-telemetry.py, PostToolUse)은 서브에이전트 내부 read 를 못 본다 →
# do-er 가 dw_read 로 실제로 읽은 운영 플레이북이 `dw-workflow-report.py` 에서 never-read 로
# 오판된다. 이 파서는 서브에이전트에 «도달»하므로, isSidechain:true 줄의 read 도구 중 target 이
# tracked 노트(governance/procedures·project/memory)로 해석되는 것만 access.jsonl 에 emit 해
# never-read 를 신뢰 가능하게 만든다.
#
# 🔴 소비자 정합: 판정 규칙(TRACKED·note_index·resolve)은 `dw-workflow-report.py` 의
#    note_index/resolve_target 와 «같아야» 한다(그게 소비자다). 아래는 그 규칙의 사본이며,
#    셀프테스트(TokenMeterReadCaptureTest.test_note_resolution_parity_with_report)가 두 구현을
#    같은 픽스처로 돌려 «동일 판정»을 강제한다 — 드리프트 시 RED.
# 🔴 이중집계 방지: isSidechain:true 줄만 emit(메인 read 는 PostToolUse dw-telemetry 가 이미 기록).
# 🔴 프라이버시: vault 상대경로만 기록. 도구 인자 전체·본문·비-vault 경로는 기록 금지.
# ─────────────────────────────────────────────────────────────────────────────

READ_TRACKED = ("governance/procedures", "project/memory")


def note_index(vault: Path):
    """tracked 노트: (stem→relpath, relpath 집합). `dw-workflow-report.note_index` 규칙의 사본."""
    by_stem: dict[str, str] = {}
    rels: set[str] = set()
    for sub in READ_TRACKED:
        base = vault / sub
        if not base.is_dir():
            continue
        for p in base.rglob("*.md"):
            if "/archive/" in str(p).replace("\\", "/"):
                continue
            rel = str(p.relative_to(vault))
            rels.add(rel)
            by_stem[p.stem] = rel
    return by_stem, rels


def resolve_note(target: str, by_stem, rels):
    """접근 target 을 tracked 노트 relpath 로 정규화(아니면 None). `resolve_target` 규칙의 사본."""
    if not target:
        return None
    if target in rels:
        return target
    stem = Path(target).stem if target.endswith(".md") else target
    return by_stem.get(stem)


def _read_candidate(block):
    """content 블록이 «읽기 도구»면 (kind, tool, raw_target) 반환, 아니면 None.

    Read → ("file","Read",file_path) · dw_read(MCP 또는 bare) → ("vault","dw_read",name/query/…).
    dw-telemetry.py 의 target 추출과 정합(name > query > title > note_type).
    """
    if not isinstance(block, dict) or block.get("type") not in ("tool_use", "server_tool_use"):
        return None
    name = str(block.get("name") or "")
    inp = block.get("input") or {}
    if not isinstance(inp, dict):
        return None
    if name == "Read":
        fp = inp.get("file_path")
        return ("file", "Read", str(fp)) if fp else None
    if name.endswith("dw_read") or "dw-vault__dw_read" in name:
        raw = inp.get("name") or inp.get("query") or inp.get("title") or inp.get("note_type")
        return ("vault", "dw_read", str(raw)) if raw else None
    return None


def sidechain_read_targets(lines):
    """새 줄들에서 «isSidechain:true(서브에이전트)» 줄의 읽기 도구 후보만 뽑는다.

    🔴 sidechain 줄만 — 메인 세션 read 는 PostToolUse dw-telemetry 가 이미 access.jsonl 에 넣으니
    여기서 또 넣으면 이중집계. isSidechain 이 명시적 true 가 아니면 무시한다.
    """
    out = []
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
        if obj.get("isSidechain") is not True:
            continue
        msg = obj.get("message") or {}
        if not isinstance(msg, dict):
            continue
        for blk in (msg.get("content") or []):
            c = _read_candidate(blk)
            if c:
                out.append(c)
    return out


def resolve_read_records(candidates, vault: Path, session: str, ts: str):
    """읽기 후보 → tracked 노트로 해석되는 것만 access.jsonl 레코드로. 상대경로만 기록(프라이버시).

    스키마는 dw-telemetry.py 와 정합 — vault: {kind:"vault",tool:"dw_read",target:rel},
    file: {kind:"file",tool:"Read",target:rel,resolved:rel}. 소비자(dw-workflow-report)의 reads
    집계가 «무변경»으로 이 줄들을 주워 never-read 가 줄어든다.
    """
    if not candidates:
        return []
    vroot = vault.resolve()
    by_stem, rels = note_index(vroot)
    if not rels:
        return []
    recs = []
    for kind, tool, raw in candidates:
        if kind == "file":
            try:
                rel = str(Path(raw).resolve().relative_to(vroot))
            except Exception:
                rel = None
            if rel not in rels:
                continue
        else:  # vault dw_read
            rel = resolve_note(raw, by_stem, rels)
            if rel is None:
                continue
        rec = {"ts": ts, "session": session, "kind": kind, "tool": tool, "target": rel}
        if kind == "file":
            rec["resolved"] = rel
        recs.append(rec)
    return recs


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


def subagents_dir_for(transcript_path: str):
    """transcript_path 에서 서브에이전트 디렉토리를 «도출»한다(payload 값에 의존하지 않기 위해).

    이 머신 실측 레이아웃(2026-09-09): 부모 `…/projects/<slug>/<session>.jsonl` 옆에
    `…/projects/<slug>/<session>/subagents/agent-*.jsonl` 가 산다. 두 입력 형태를 모두 도출:
      - 부모 경로 `<session>.jsonl` → `.jsonl` 을 떼면 session 디렉토리 → `<sess>/subagents`.
      - 서브 파일 경로 `…/<session>/subagents/agent-x.jsonl` → `/subagents/` 앞까지가 session
        디렉토리 → `<sess>/subagents`.
    도출 불가면 None.
    """
    if not transcript_path:
        return None
    if "/subagents/" in transcript_path:
        return transcript_path.split("/subagents/")[0] + "/subagents"
    if transcript_path.endswith(".jsonl"):
        return transcript_path[: -len(".jsonl")] + "/subagents"
    return None


def collect_targets(transcript_path: str, hook_event_name: str) -> list[str]:
    """이번 호출에서 «증분 파싱할» 트랜스크립트 파일 목록(중복 제거·순서 보존).

    - 메인 `Stop`: payload 의 transcript_path 만(종전과 동일).
    - `SubagentStop`: payload 의 transcript_path 가 부모든 서브 전용이든 상관없이, 거기서
      «서브에이전트 디렉토리를 직접 도출해» `<sess>/subagents/*.jsonl` 을 «전부» 대상에 넣는다.
      ⇒ do-er 토큰 커버리지가 payload 의 transcript_path 실측값에 걸리지 않는다(견고화).
      여전히 실행 중인 다른 서브에이전트의 부분 파일도 offset+완결줄 로직으로 안전.
    """
    targets: list[str] = []
    if transcript_path and os.path.isfile(transcript_path):
        targets.append(transcript_path)
    if hook_event_name == "SubagentStop":
        sd = subagents_dir_for(transcript_path)
        if sd and os.path.isdir(sd):
            targets.extend(sorted(glob.glob(os.path.join(sd, "*.jsonl"))))
    seen: set[str] = set()
    out: list[str] = []
    for p in targets:
        if p not in seen and os.path.isfile(p):
            seen.add(p)
            out.append(p)
    return out


def process(paths, hook_event_name: str, session: str, state_dir: Path, vault: Path | None = None) -> list:
    """임계구역: offset 로드 → 대상 파일들 증분 파싱 → tokens.jsonl + access.jsonl append → offset 저장.

    `paths` 는 처리할 트랜스크립트 경로 목록. 각 경로는 «경로별 offset» 으로 독립 증분(중복집계 0).
    offset 로드·저장·append 는 목록 전체에 대해 «한 번만»(하나의 flock 안에서 원자적으로). 반환은
    테스트·관측용 델타 레코드 목록. 데이터 없는 (경로,source) 는 레코드로 남기지 않는다.

    부가 산출(기존 토큰 집계 불변): 같은 파싱 패스에서 isSidechain 줄의 vault-노트 read 를 뽑아
    access.jsonl 에 emit(never-read 지표 교란 해소). vault 미지정 시 `state_dir.parent`(=vault).
    """
    if isinstance(paths, str):  # 하위호환 — 단일 경로도 허용
        paths = [paths]
    if vault is None:
        vault = state_dir.parent
    offsets = _load_offsets(state_dir)
    ts = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    records = []
    read_cands = []
    for transcript_path in paths:
        stored = int(offsets.get(transcript_path, 0) or 0)
        lines, new_offset = _read_new_bytes(transcript_path, stored)
        buckets = parse_lines(lines, hook_event_name)
        read_cands.extend(sidechain_read_targets(lines))  # sidechain 줄만(내부 필터)
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
        offsets[transcript_path] = new_offset

    if records:
        with open(state_dir / "tokens.jsonl", "a", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 부가 산출: 서브에이전트 vault-노트 read → access.jsonl(소비자 스키마 정합)
    areads = resolve_read_records(read_cands, vault, session, ts)
    if areads:
        with open(state_dir / "access.jsonl", "a", encoding="utf-8") as f:
            for rec in areads:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    _save_offsets(state_dir, offsets)
    return records


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        transcript_path = payload.get("transcript_path") or ""
        hook_event_name = payload.get("hook_event_name") or ""
        session = payload.get("session_id") or ""

        targets = collect_targets(transcript_path, hook_event_name)
        if not targets:
            return 0  # 처리할 파일 없음(경로 없음/디렉토리 부재) — 조용히 스킵

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
                    process(targets, hook_event_name, session, state_dir, vault.resolve())
                finally:
                    fcntl.flock(lk, fcntl.LOCK_UN)
        else:  # pragma: no cover - 비POSIX 폴백(락 없이)
            process(targets, hook_event_name, session, state_dir, vault.resolve())
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
