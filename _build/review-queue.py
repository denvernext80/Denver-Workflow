#!/usr/bin/env python3
"""vault OBEY draft 큐 — 자동 비준(ssot-ratify) 대상/hold 를 보고한다.

LIVE(memory/contract/spec)는 MCP가 stable 로 쓰므로 비준 게이트가 없다(읽기는 status 무관).
강제되는 OBEY(rule/guidance/procedure)만 draft 일 수 있고, 이는 `make ratify` 가 자동 비준한다.
이 큐는 아직 stable 이 안 된 OBEY(=ratify 가 hold 한 판단 필요 건)를 사람이 보게 한다.
표준 라이브러리만 사용. usage: review-queue.py [--vault .]
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

CONTENT = ["governance/rules", "governance/guidance", "governance/procedures"]
SKIP = {"archive"}
FM = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def field(text: str, key: str) -> str:
    m = re.search(rf"^{key}:\s*(.+)$", text[:600], re.MULTILINE)
    return m.group(1).strip().strip("'\"") if m else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=".", type=Path)
    args = ap.parse_args()
    vault = args.vault.resolve()

    queue: dict[str, list[tuple[str, str]]] = {}
    for d in CONTENT:
        base = vault / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.md")):
            if any(s in p.relative_to(base).parts for s in SKIP) or p.name == "MEMORY.md":
                continue
            text = p.read_text(encoding="utf-8")
            if field(text, "status") == "draft":
                ty = field(text, "type") or "?"
                title = field(text, "title") or field(text, "name") or p.stem
                queue.setdefault(ty, []).append((str(p.relative_to(vault)), title))

    total = sum(len(v) for v in queue.values())
    print(f"== OBEY draft 큐 (rule/guidance/procedure {total}건) ==")
    if not total:
        print("  (없음 — 모두 stable. `make ratify` 가 자동 비준 중)")
    for ty in sorted(queue):
        print(f"  [{ty}] {len(queue[ty])}건")
        for path, title in queue[ty]:
            print(f"    • {title[:60]}  ({path})")
    if total:
        print("\n  → `make ratify` 가 안전한 건을 자동 stable·compile 합니다(사람 불요).")
        print("    여기 남는 건 = ratify 가 hold 한 '판단 필요' 건(본문 <!-- ratify-hold: ... --> 사유 참고).")
        print("    LIVE(memory/contract/spec)는 게이트 없음 — 이 큐에 안 뜸.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
