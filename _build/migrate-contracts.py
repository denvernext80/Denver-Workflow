#!/usr/bin/env python3
"""일회성: 두 repo 의 docs/api-contract 합집합을 vault contracts/ 로 이전(SSOT화).

규칙:
  - 공통 파일 동일 → 한 부. drift → 저자 기준(backend-* = Travel-One, app-* = Balipick).
  - repo 고유 → 그대로 가져옴.
  - *open-items* = repo-로컬(각 repo 자기 것) → vault 제외, 미러 안 함.
  - 본문은 원형 보존, frontmatter(type:contract 등)는 파일명에서 결정론적으로 생성.

usage: migrate-contracts.py <travel_one_contract_dir> <balipick_contract_dir> <vault_contracts_out>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)$")
HEADING_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
EXCLUDE = ("open-items",)  # repo-로컬, vault 미포함
KINDS = ["request", "reply", "signoff", "contract", "notice", "notify", "decision", "mapping"]


def yaml_sq(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def meta_for(name: str, body: str) -> str:
    stem = name[:-3] if name.endswith(".md") else name
    m = DATE_RE.match(stem)
    date, slug = (m.group(1), m.group(2)) if m else ("", stem)
    if slug.startswith("backend-"):
        direction = "backend-to-app"
    elif slug.startswith("app-"):
        direction = "app-to-backend"
    else:
        direction = "shared"
    kind = next((k for k in KINDS if k in slug), "doc")
    h = HEADING_RE.search(body)
    title = h.group(1).strip() if h else slug.replace("-", " ")
    lines = [
        "---",
        "type: contract",
        "status: stable",
        f"date: {date}" if date else "date:",
        f"direction: {direction}",
        f"kind: {kind}",
        f"title: {yaml_sq(title)}",
        "---",
    ]
    return "\n".join(lines)


def authoritative(name: str, to_dir: Path, bp_dir: Path) -> Path | None:
    t, b = to_dir / name, bp_dir / name
    if t.exists() and b.exists():
        if t.read_bytes() == b.read_bytes():
            return t
        # drift → 저자 기준
        if name.startswith("backend-") or "-backend-" in name:
            return t
        if name.startswith("app-") or "-app-" in name:
            return b
        sys.stderr.write(f"  ⚠️ drift 저자 불명, Travel-One 채택: {name}\n")
        return t
    return t if t.exists() else (b if b.exists() else None)


def main() -> int:
    if len(sys.argv) != 4:
        sys.stderr.write("usage: migrate-contracts.py <to_dir> <bp_dir> <vault_out>\n")
        return 2
    to_dir, bp_dir, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    names = sorted({p.name for p in to_dir.glob("*.md")} | {p.name for p in bp_dir.glob("*.md")})

    out.mkdir(parents=True, exist_ok=True)
    migrated = excluded = 0
    for name in names:
        if any(x in name for x in EXCLUDE):
            excluded += 1
            continue
        src = authoritative(name, to_dir, bp_dir)
        if src is None:
            continue
        body = src.read_text(encoding="utf-8").rstrip()
        # 이미 frontmatter 가 있으면(재실행) 제거 후 재생성
        if body.startswith("---\n"):
            end = body.find("\n---", 4)
            if end != -1:
                body = body[end + 4:].lstrip("\n")
        (out / name).write_text(meta_for(name, body) + "\n\n" + body + "\n", encoding="utf-8")
        migrated += 1

    print(f"이전 완료: {migrated}개 → {out}  (repo-로컬 제외 {excluded}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
