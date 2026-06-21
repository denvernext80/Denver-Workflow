#!/usr/bin/env python3
"""SSOT 자동 비준기 — 사람 비준 단계를 제거한다(결정론적, 무료·즉시·안전).

LIVE(memory/contract/spec)는 MCP가 이미 stable 로 쓰므로 게이트가 없다. 이 스크립트는
OBEY(rule/guidance/procedure) draft 를 검증해 **안전한 것만** 자동 stable 로 승격한다.
사람도 LLM도 필요 없는 명확한 케이스를 처리하고, 판단이 필요한 케이스(check 패턴이 기존
코드에 매치되는 rule = 진짜위반 vs 오탐 구분 필요)는 draft 로 두고 사유를 적어 hold 한다.

승격 기준:
  guidance / procedure : 필수 필드 완비 + scope 의 skill-manifest 존재 → 승격(강제 teeth 없음).
  rule                 : 위 + enforced-by 가 agents/ 에 실재
                         + check 패턴(deny/require)이 양 repo 기존 코드에 **0 매치**
                         (강제해도 기존 코드에 즉시 오탐/위반 0) → 승격.
                         매치가 있으면 hold — 진짜위반인지 오탐인지는 판단 필요(LLM/사람).

승격 후 `compile --dry-run --strict` 로 검증한다. 깨지면 그 승격을 되돌린다(안전).
이 스크립트는 status 만 바꾼다 — 실제 컴파일·설치(make install)는 호출자(make ratify)가 한다.

usage: ssot-ratify.py --vault . [--project PATH ...] [--dry-run]
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

import yaml

OBEY = {"rule", "guidance", "procedure"}
REQUIRED = {
    "rule": ["type", "scope", "status", "enforced-by", "compiles-to"],
    "guidance": ["type", "scope", "status", "compiles-to"],
    "procedure": ["type", "scope", "status", "compiles-to"],
}
# 코드베이스 스캔 시 건너뛸 디렉터리
SKIP = {".git", ".venv", "node_modules", "vendor", "build", "dist", ".dart_tool",
        ".bkit", "__pycache__", ".claude", ".obsidian", "ios", "android", "_build"}
FM_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
MAX_BYTES = 2_000_000

# scope 정규화 — 컴파일러·MCP 와 동일 alias. ratify 도 canonical 로 판정·승격(불일치 방지).
SCOPE_ALIASES = {
    "backend": "backend-php", "admin": "backend-php", "web": "backend-php",
    "dev-engineering-charter": "engineering", "workspace": "engineering",
    "workflow": "engineering", "general": "engineering", "infra": "engineering",
    "orchestration": "engineering",
    "balipick-design": "design-system",
    "balipick-mobile": "mobile-flutter", "balipick-app": "mobile-flutter",
    "balipick-ios-release": "mobile-flutter", "ios": "mobile-flutter",
    "balipick-api-contract": "api-contract", "chat": "api-contract",
}


def canonical_scope(scope: str, manifests: set) -> str:
    raw = (scope or "").strip()
    if raw in manifests:
        return raw
    if raw in SCOPE_ALIASES:
        return SCOPE_ALIASES[raw]
    for tok in re.split(r"[\s,/_-]+", raw.lower()):
        if tok in manifests:
            return tok
        if tok in SCOPE_ALIASES:
            return SCOPE_ALIASES[tok]
    return raw


def parse(text: str) -> tuple[dict, int]:
    m = FM_RE.match(text)
    if not m:
        return {}, -1
    try:
        return (yaml.safe_load(m.group(1)) or {}), m.end()
    except yaml.YAMLError:
        return {}, -1


def as_list(v) -> list[str]:
    if not v:
        return []
    return [str(x) for x in v] if isinstance(v, list) else [str(v)]


def matches_glob(rel: str, patterns: list[str]) -> bool:
    base = rel.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(base, p) for p in patterns)


def scan_codebase(projects: list[Path], glob: list[str], exclude: list[str],
                  deny: list[str], require: list[str]) -> list[str]:
    """양 repo 에서 rule 의 check 패턴 위반(있으면)을 모아 반환. 비어 있으면 '기존 코드 깨끗'."""
    hits: list[str] = []
    deny_res = [re.compile(p) for p in deny]
    req_res = [re.compile(p) for p in require]
    for proj in projects:
        if not proj.is_dir():
            continue
        for p in proj.rglob("*"):
            if not p.is_file():
                continue
            if any(part in SKIP for part in p.relative_to(proj).parts):
                continue
            rel = p.relative_to(proj).as_posix()
            if glob and not matches_glob(rel, glob):
                continue
            if exclude and matches_glob(rel, exclude):
                continue
            try:
                if p.stat().st_size > MAX_BYTES:
                    continue
                text = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for rx in deny_res:
                if rx.search(text):
                    hits.append(f"{proj.name}/{rel}: 금지패턴 /{rx.pattern}/ 매치")
                    break
            for rx in req_res:
                if not rx.search(text):
                    hits.append(f"{proj.name}/{rel}: 필수패턴 /{rx.pattern}/ 누락")
                    break
            if len(hits) >= 20:
                return hits
    return hits


def annotate_hold(path: Path, text: str, fm_end: int, reason: str) -> None:
    """hold 사유를 본문 상단 주석으로 남긴다(멱등 — 기존 hold 주석 있으면 갱신)."""
    body = text[fm_end:].lstrip("\n")
    marker = "<!-- ratify-hold:"
    body = re.sub(rf"{re.escape(marker)}.*?-->\n*", "", body, flags=re.DOTALL)
    note = f"{marker} {reason} -->\n\n"
    path.write_text(text[:fm_end] + "\n" + note + body, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=".", type=Path)
    ap.add_argument("--project", action="append", default=[], type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    vault = args.vault.resolve()
    projects = [p.resolve() for p in args.project]

    agents = {p.stem for p in (vault / "governance" / "agents").glob("*.md")}
    manifests = set()
    for p in (vault / "governance" / "_skills").glob("*.md"):
        fm, _ = parse(p.read_text(encoding="utf-8"))
        if fm.get("scope"):
            manifests.add(str(fm["scope"]))

    promoted: list[str] = []
    held: list[tuple[str, str]] = []
    snapshot: list[tuple[Path, str]] = []  # 롤백용

    for d in ("governance/rules", "governance/guidance", "governance/procedures"):
        base = vault / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.md")):
            if "archive" in p.relative_to(base).parts:
                continue
            text = p.read_text(encoding="utf-8")
            fm, fm_end = parse(text)
            if fm.get("status") != "draft" or fm.get("type") not in OBEY:
                continue
            ty = fm["type"]
            rel = str(p.relative_to(vault))

            missing = [k for k in REQUIRED[ty] if not fm.get(k)]
            if missing:
                held.append((rel, f"필수 필드 누락: {', '.join(missing)}"))
                continue
            canon = canonical_scope(str(fm.get("scope") or ""), manifests)
            if canon not in manifests:
                held.append((rel, f"scope '{fm.get('scope')}' 의 skill-manifest 없음(고아)"))
                continue
            if ty == "rule":
                eb = str(fm.get("enforced-by"))
                if eb not in agents:
                    held.append((rel, f"enforced-by '{eb}' 가 agents/ 에 없음"))
                    continue
                glob = as_list(fm.get("check-glob"))
                deny = as_list(fm.get("check-deny"))
                require = as_list(fm.get("check-require"))
                if (deny or require):
                    if not glob:
                        held.append((rel, "check 패턴은 있으나 check-glob 없음(검사 비활성 — 무의미)"))
                        continue
                    hits = scan_codebase(projects, glob, as_list(fm.get("check-exclude")), deny, require)
                    if hits:
                        held.append((rel, f"기존 코드에 {len(hits)}건 매치 — 진짜위반/오탐 판단 필요. 예: {hits[0]}"))
                        continue
            # 승격 — status:stable + scope 를 canonical 로 정규화(불일치 데이터 정리).
            snapshot.append((p, text))
            head = re.sub(r"^status:\s*draft\s*$", "status: stable", text[:fm_end],
                          count=1, flags=re.MULTILINE)
            if canon != str(fm.get("scope") or "").strip():
                head = re.sub(r"^scope:\s*.+$", f"scope: {canon}", head, count=1, flags=re.MULTILINE)
            new = head + text[fm_end:]
            if not args.dry_run:
                p.write_text(new, encoding="utf-8")
            promoted.append(rel)

    # 승격분 검증 — 컴파일 깨지면 롤백
    rolled_back = False
    if promoted and not args.dry_run:
        r = subprocess.run([sys.executable, str(vault / "_build" / "ssot-compile.py"),
                            "--vault", str(vault), "--out", str(vault / ".claude" / "skills"),
                            "--dry-run", "--strict"], capture_output=True, text=True)
        if r.returncode != 0:
            for p, orig in snapshot:
                p.write_text(orig, encoding="utf-8")
            rolled_back = True

    print(f"== SSOT 자동 비준 ==")
    if rolled_back:
        print(f"  [롤백] 승격 {len(promoted)}건이 컴파일을 깨 전부 되돌림 — 모두 hold 로 간주.")
        held.extend((r, "승격 시 컴파일 strict 실패(아래 dry-run 확인)") for r in promoted)
        promoted = []
    print(f"  승격(draft→stable) {len(promoted)}건:")
    for r in promoted:
        print(f"    + {r}")
    print(f"  hold(판단 필요, draft 유지) {len(held)}건:")
    for r, why in held:
        print(f"    · {r}\n        → {why}")
        if not args.dry_run:
            pp = vault / r
            t = pp.read_text(encoding="utf-8")
            _, fe = parse(t)
            if fe > 0:
                annotate_hold(pp, t, fe, why)
    # 승격이 있었으면 호출자가 make install 하도록 신호(exit code 10)
    return 10 if promoted else 0


if __name__ == "__main__":
    raise SystemExit(main())
