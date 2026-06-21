#!/usr/bin/env python3
"""일회성: Travel-One/docs 의 발리픽 히스토리를 vault project/ 로 통합(SSOT 보존).

advisor 가드 반영:
  - 델타만 + idempotent: 대상에 같은 파일명이 이미 있으면 skip(덮어쓰기 금지).
  - project/ 로만 라우팅(비컴파일 LIVE 지식). governance/ 승격은 이 스크립트 범위 밖(수동 선별).
  - frontmatter 는 기존 project/{contracts,specs}/*.md 스키마와 동일하게 생성.
  - 비파괴: 원본 repo 파일은 건드리지 않는다(정리-1).

라우팅:
  contracts  → project/contracts/          (api-contract, open-items/tombstone/README 제외)
  specs      → project/specs/              (01-plan·02-design·superpowers·design = 기획/설계 정본)
  archive    → project/specs/archive/      (archive·analysis·report·operations·agents·architecture·top-level = 역사/참조)

usage: migrate-history.py <travel_one_docs> <vault_project> [--apply]
       (--apply 없으면 dry: 무엇을 옮길지/skip 할지만 출력)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-(.+)$")
H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
CONTRACT_KINDS = ["request", "reply", "signoff", "notice", "notify", "decision", "mapping", "contract"]
CONTRACT_EXCLUDE = ("open-items", "_SSOT-MOVED-TO-VAULT", "README")

# 스코프 휴리스틱(비컴파일 노트 — 메타데이터용. 컴파일러 canonical_scope 가 별칭 흡수)
def scope_for(name: str, rel: str) -> str:
    s = (name + " " + rel).lower()
    if any(k in s for k in ("mobile", "app-", "flutter", "ios", "deeplink", "applink")):
        return "mobile-flutter"
    if any(k in s for k in ("design", "ui", "hero", "image-viewer")):
        return "design-system"
    if any(k in s for k in ("contract", "api-")):
        return "api-contract"
    if any(k in s for k in ("crawl", "policy", "jalanjalan", "terminology", "spot", "photo")):
        return "content-policy"
    return "engineering"


def yaml_sq(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def title_of(name: str, body: str) -> str:
    h = H1_RE.search(body)
    if h:
        return h.group(1).strip()
    stem = name[:-3] if name.endswith(".md") else name
    m = DATE_RE.match(stem)
    return (m.group(2) if m else stem).replace("-", " ").replace(".", " ").strip()


def date_of(name: str) -> str:
    m = DATE_RE.match(name[:-3] if name.endswith(".md") else name)
    return m.group(1) if m else ""


def strip_frontmatter(body: str) -> str:
    if body.startswith("---\n"):
        end = body.find("\n---", 4)
        if end != -1:
            return body[end + 4:].lstrip("\n")
    return body


def contract_fm(name: str, body: str) -> str:
    slug = (name[:-3] if name.endswith(".md") else name)
    m = DATE_RE.match(slug)
    date, rest = (m.group(1), m.group(2)) if m else ("", slug)
    direction = ("backend-to-app" if rest.startswith("backend-") or "-backend-" in rest
                 else "app-to-backend" if rest.startswith("app-") or "-app-" in rest
                 else "shared")
    kind = next((k for k in CONTRACT_KINDS if k in rest), "doc")
    scope = "chat" if ("chat" in slug or "채팅" in name) else "balipick-api-contract"
    return "\n".join([
        "---", "type: contract", "status: stable", f"scope: {scope}",
        f"date: {yaml_sq(date)}" if date else "date:",
        f"direction: {direction}", f"kind: {kind}",
        f"title: {yaml_sq(title_of(name, body))}", "---",
    ])


def spec_fm(name: str, body: str, rel: str, kind: str) -> str:
    date = date_of(name)
    return "\n".join([
        "---", "type: spec", "status: stable", f"scope: {scope_for(name, rel)}",
        f"date: {yaml_sq(date)}" if date else "date:",
        f"kind: {kind}",
        f"title: {yaml_sq(title_of(name, body))}",
        f"source: {yaml_sq('Travel-One/docs/' + rel)}", "---",
    ])


def spec_kind(name: str, rel: str) -> str:
    s = (name + " " + rel).lower()
    if ".design" in s or "/02-design/" in s or "design" in rel.lower():
        return "design"
    if ".plan" in s or "/01-plan/" in s:
        return "plan"
    return "spec"


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    if len(args) != 2:
        sys.stderr.write("usage: migrate-history.py <travel_one_docs> <vault_project> [--apply]\n")
        return 2
    docs, proj = Path(args[0]), Path(args[1])
    c_out, s_out, a_out = proj / "contracts", proj / "specs", proj / "specs" / "archive"

    # (target_dir, builder, iterable of (src_path, rel))
    jobs: list[tuple[Path, str, Path, str]] = []  # (out_dir, kind_tag, src, rel)

    # 1) contracts
    for p in sorted((docs / "api-contract").glob("*.md")):
        if any(x in p.name for x in CONTRACT_EXCLUDE):
            continue
        jobs.append((c_out, "contract", p, "api-contract/" + p.name))

    # 2~3) 전부 역사/참조 → specs/archive/ (다이제스트 LIVE 인덱스 제외, ssot_search 로는 검색됨)
    #   repo docs 는 모두 shipped 기능 히스토리 — active specs/ 에 넣으면 다이제스트 오염.
    #   기획/설계 정본 + 역사·PDCA·운영·에이전트·아키텍처·top-level
    for sub in ("01-plan/features", "02-design/features", "superpowers/specs",
                "superpowers/specs-backend", "design",
                "archive", "03-analysis", "04-report", "operations", "architecture"):
        for p in sorted((docs / sub).rglob("*.md")):
            jobs.append((a_out, "spec", p, str(p.relative_to(docs))))
    # agents: denver-workflow 는 이미 통합 → 제외
    for p in sorted((docs / "agents").glob("*.md")):
        if p.name == "denver-workflow.md":
            continue
        jobs.append((a_out, "spec", p, "agents/" + p.name))
    # top-level 정책/참조 md
    for p in sorted(docs.glob("*.md")):
        jobs.append((a_out, "spec", p, p.name))

    migrated = skipped = collided = 0
    seen_targets: set[Path] = set()
    for out_dir, tag, src, rel in jobs:
        target = out_dir / src.name
        if target in seen_targets:
            # 파일명 충돌(서로 다른 내용) → 드롭하지 말고 소스 디렉토리 접두어로 보존
            prefix = src.parent.name
            target = out_dir / f"{prefix}--{src.name}"
            collided += 1
            print(f"  [dedup→] {rel}  →  {target.name}")
        seen_targets.add(target)
        if target.exists():
            skipped += 1
            continue
        body = strip_frontmatter(src.read_text(encoding="utf-8").rstrip())
        fm = (contract_fm(src.name, body) if tag == "contract"
              else spec_fm(src.name, body, rel, spec_kind(src.name, rel)))
        print(f"  [+{tag:8}] {rel}  →  {target.relative_to(proj.parent)}")
        if apply:
            out_dir.mkdir(parents=True, exist_ok=True)
            target.write_text(fm + "\n\n" + body + "\n", encoding="utf-8")
            migrated += 1

    mode = "APPLY" if apply else "DRY(미적용)"
    print(f"\n[{mode}] 신규 {migrated if apply else len([j for j in jobs])} 후보 · "
          f"기존 skip {skipped} · 충돌 {collided}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
