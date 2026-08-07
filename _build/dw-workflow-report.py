#!/usr/bin/env python3
"""dw 워크플로우 리포트 — 텔레메트리 로그로 '규율 준수 + 재사용'을 실측.

usage:
    python dw-workflow-report.py --vault /abs/vault [--days 30] [--json]

두 개의 진단 가설을 데이터로 확정/반증한다:
  A) 규율 준수 분포
     - 탐색: graphify vs dw_search vs Grep  → graphify-우선 준수율
     - 쓰기: dw_write_* vs vault 파일 직접 Edit/Write → write-through 준수율(bypass 율)
     - 읽기: dw_read vs vault 파일 직접 Read → read-through 준수율
  B) 절차·memory 재사용 (read 0회 = archive 후보; 직접 Read/Edit 도 read 로 집계해 오판 방지)

관측창 주의: 로그는 계측 설치 이후만 담는다. archive 후보는 '관측창과 --days 보다 오래됐고
read 0회' 인 것만. 관측일수가 --days 미만이면 경고.
"""
from __future__ import annotations

import argparse
import datetime
import json
from collections import defaultdict
from pathlib import Path

TRACKED = ["governance/procedures", "project/memory"]


def load_log(vault: Path) -> list[dict]:
    p = vault / ".dw-state" / "access.jsonl"
    out: list[dict] = []
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    return out


def note_index(vault: Path):
    """tracked 노트: stem→relpath, relpath 집합."""
    by_stem: dict[str, str] = {}
    rels: set[str] = set()
    files: list[Path] = []
    for sub in TRACKED:
        base = vault / sub
        if not base.is_dir():
            continue
        for p in base.rglob("*.md"):
            if "/archive/" in str(p).replace("\\", "/"):
                continue
            rel = str(p.relative_to(vault))
            rels.add(rel)
            by_stem[p.stem] = rel
            files.append(p)
    return by_stem, rels, files


def resolve_target(target: str, resolved: str, by_stem, rels):
    """접근 레코드를 tracked 노트 relpath 로 정규화(아니면 None)."""
    if resolved and resolved in rels:
        return resolved
    if not target:
        return None
    t = target
    if t in rels:
        return t
    stem = Path(t).stem if t.endswith(".md") else t
    return by_stem.get(stem)


def pct(a: int, b: int) -> str:
    tot = a + b
    return f"{(100*a/tot):.0f}%" if tot else "—"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", required=True)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    vault = Path(a.vault).resolve()
    recs = load_log(vault)
    by_stem, rels, files = note_index(vault)

    now = datetime.datetime.now().astimezone()
    tss = []
    for r in recs:
        try:
            tss.append(datetime.datetime.fromisoformat(r.get("ts", "")))
        except Exception:
            pass
    start = min(tss) if tss else None
    obs_days = ((now - start).total_seconds() / 86400) if start else 0.0

    # --- 규율 카운트 ---
    c = defaultdict(int)
    reads = defaultdict(int)  # relpath -> read/touch count
    for r in recs:
        kind, tool = r.get("kind"), r.get("tool", "")
        if kind == "graphify":
            c["disc_graphify"] += 1
        elif kind == "grep":
            c["disc_grep"] += 1
        elif kind == "vault":
            if tool.startswith("dw_search"):
                c["disc_search"] += 1
            elif tool.startswith("dw_read"):
                c["read_dw"] += 1
                rel = resolve_target(r.get("target", ""), r.get("resolved", ""), by_stem, rels)
                if rel:
                    reads[rel] += 1
            elif tool.startswith(("dw_write", "dw_propose", "dw_resolve")):
                c["write_dw"] += 1
        elif kind == "file":
            rel = r.get("resolved")
            if tool == "Read":
                c["read_direct"] += 1
                if rel in rels:
                    reads[rel] += 1
            elif tool in ("Edit", "Write", "MultiEdit"):
                c["write_direct"] += 1
                if rel in rels:
                    reads[rel] += 1  # 편집도 접근(재사용) 신호

    # --- 재사용/archive 후보 ---
    buckets = {}
    cands = {}
    for sub in TRACKED:
        base = vault / sub
        notes = [p for p in base.rglob("*.md") if "/archive/" not in str(p).replace("\\", "/")] if base.is_dir() else []
        active = never = 0
        cand = []
        for p in notes:
            rel = str(p.relative_to(vault))
            rc = reads.get(rel, 0)
            age = (now.timestamp() - p.stat().st_mtime) / 86400
            if rc > 0:
                active += 1
            else:
                never += 1
            if rc == 0 and age >= a.days and age >= obs_days:
                cand.append((round(age), rel))
        cand.sort(reverse=True)
        buckets[sub] = {"total": len(notes), "read>0": active, "never_read": never}
        cands[sub] = [{"age_days": x[0], "path": x[1]} for x in cand]

    report = {
        "observed_since": start.isoformat() if start else None,
        "observed_days": round(obs_days, 1),
        "total_events": len(recs),
        "discipline": {
            "discovery": {"graphify": c["disc_graphify"], "dw_search": c["disc_search"], "grep": c["disc_grep"]},
            "writes": {"dw_write": c["write_dw"], "direct_vault_edit": c["write_direct"]},
            "reads": {"dw_read": c["read_dw"], "direct_vault_read": c["read_direct"]},
        },
        "reuse": buckets,
        "archive_candidates": cands,
    }
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print("# dw 워크플로우 리포트")
    print(f"관측 시작 {report['observed_since']} | 관측 {report['observed_days']}일 | 총 이벤트 {report['total_events']}")
    if obs_days < a.days:
        print(f"\n⚠️  관측일수({round(obs_days,1)}) < 임계({a.days}일) — archive 후보는 관측이 더 쌓인 뒤 신뢰.")

    d = report["discipline"]
    g, s, gr = d["discovery"]["graphify"], d["discovery"]["dw_search"], d["discovery"]["grep"]
    print("\n## A. 규율 준수")
    print(f"  탐색: graphify {g} · dw_search {s} · grep {gr}"
          f"   → graphify 비중 {pct(g, s+gr)} (규율: graphify 우선)")
    print(f"  쓰기: dw_write {d['writes']['dw_write']} · 직접편집 {d['writes']['direct_vault_edit']}"
          f"   → write-through {pct(d['writes']['dw_write'], d['writes']['direct_vault_edit'])}"
          f"  (직접편집 = SSOT bypass)")
    print(f"  읽기: dw_read {d['reads']['dw_read']} · 직접Read {d['reads']['direct_vault_read']}"
          f"   → read-through {pct(d['reads']['dw_read'], d['reads']['direct_vault_read'])}")

    print("\n## B. 절차·memory 재사용")
    for sub in TRACKED:
        b = report["reuse"][sub]
        print(f"  {sub}: 총 {b['total']} | read>0 {b['read>0']} | 한 번도 안 읽힘 {b['never_read']}")
        cc = report["archive_candidates"][sub]
        if cc:
            print(f"    archive 후보(read 0 & {a.days}일+): {len(cc)}건 — 상위 12")
            for x in cc[:12]:
                print(f"      - [{x['age_days']}d] {x['path']}")


if __name__ == "__main__":
    main()
