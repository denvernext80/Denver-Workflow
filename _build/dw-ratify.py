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

usage: dw-ratify.py --vault . [--project PATH ...] [--dry-run]
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

import dw_state
import dw_verify

OBEY = {"rule", "guidance", "procedure"}
REQUIRED = {
    "rule": ["type", "scope", "status", "enforced-by", "compiles-to"],
    "guidance": ["type", "scope", "status", "compiles-to"],
    "procedure": ["type", "scope", "status", "compiles-to"],
}
# 스캔 SKIP·검증 로직은 dw_verify.py 단일 정본(비준기와 제안 시점이 공유 — 판정이 갈리면 안 된다).
SKIP = dw_verify.SKIP
STATE_DIR = dw_state.STATE_DIR
PROJECTS_JSON = dw_state.PROJECTS_JSON
FM_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
MAX_BYTES = 2_000_000

# scope 정규화 — 컴파일러·MCP 와 동일 alias. ratify 도 canonical 로 판정·승격(불일치 방지).
SCOPE_ALIASES = {
    "backend": "backend-php", "admin": "backend-php", "web": "backend-php",
    "dev-engineering-charter": "engineering", "workspace": "engineering",
    "workflow": "engineering", "general": "engineering", "infra": "engineering",
    "orchestration": "engineering",
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


as_list = dw_verify.as_list
matches_glob = dw_verify.matches_glob
scan_codebase = dw_verify.scan_codebase


def registered_projects(vault: Path) -> list[Path]:
    """`<vault>/.dw-state/projects.json` 에 등록된 스캔 대상 레포(실재하는 것만).

    정본을 여기 두는 이유: ① 엔진 코드에 사용자 경로를 하드코딩하면 공개 플러그인이 특정
    워크스페이스에 묶인다 ② `~/.claude.json` 의 projects 맵은 **한 번도 열지 않은 레포를
    빠뜨린다**(실측: 3개 중 2개 누락) ③ `make install-project` 가 이미 프로젝트↔vault 를 잇고
    있으니 그 역링크만 남기면 크론·스케줄에서 인자를 줄 필요가 없다.
    """
    return dw_state.registered_projects(vault)


def scan_codebase(projects: list[Path], glob: list[str], exclude: list[str],
                  deny: list[str], require: list[str]) -> tuple[list[str], int]:
    """rule 의 check 패턴을 기존 코드에 돌린다. 반환 `(위반목록, 검사대상 파일수)`.

    **검사대상 수를 함께 돌려주는 게 핵심이다.** 위반 0 은 두 가지를 뜻할 수 있다 —
    ① 대상이 있고 깨끗하다 ② **대상이 아예 없다**(검증 불가). 호출부가 그 둘을 갈라야 한다
    (vault stable 규칙 「검증 장치는 비교 대상이 비어있지 않음을 먼저 증명하라」).

    walk 는 `dirnames` 프루닝으로 SKIP 트리에 **내려가지 않는다**(종전 rglob 사후필터는 8.8s,
    이건 0.12s — 3레포 실측). symlink 는 따라가지 않는다(os.walk 기본값).
    """
    hits: list[str] = []
    candidates = 0
    deny_res = [re.compile(p) for p in deny]
    req_res = [re.compile(p) for p in require]
    for proj in projects:
        if not proj.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(proj):
            dirnames[:] = [d for d in dirnames if d not in SKIP]
            for name in filenames:
                p = Path(dirpath) / name
                try:
                    rel = p.relative_to(proj).as_posix()
                except ValueError:
                    continue
                if glob and not matches_glob(rel, glob):
                    continue
                if exclude and matches_glob(rel, exclude):
                    continue
                candidates += 1
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
                    return hits, candidates
    return hits, candidates


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
    # 명시 --project 가 최우선, 없으면 레지스트리(크론·스케줄에서 인자 없이 동작해야 한다).
    projects = [p.resolve() for p in args.project] or registered_projects(vault)
    proj_src = "--project 인자" if args.project else f"{STATE_DIR}/{PROJECTS_JSON} 레지스트리"

    agents = {p.stem for p in (vault / "governance" / "agents").glob("*.md")}
    manifests = set()
    for p in (vault / "governance" / "_skills").glob("*.md"):
        fm, _ = parse(p.read_text(encoding="utf-8"))
        if fm.get("scope"):
            manifests.add(str(fm["scope"]))

    promoted: list[str] = []
    held: list[tuple[str, str]] = []
    snapshot: list[tuple[Path, str]] = []  # 롤백용
    scan_notes: list[str] = []             # 승격분의 검사대상 수(= '무엇에 비추어 0 인가'의 근거)

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
                # ⚠️ 판정은 dw_verify 단일 정본에 위임한다 — `dw_propose_rule` 이 제안
                #    시점에 돌리는 예측과 **같은 코드**여야 예측과 실제가 어긋나지 않는다.
                #    check 패턴이 없는 규칙(서술 규칙)·guidance·procedure 는 NO_CHECKS 로
                #    바로 승격 가능이다 — 검증 대상이 없으니 hold 하면 큐가 정체된다.
                v = dw_verify.verify_rule_checks(
                    vault, deny=fm.get("check-deny"), require=fm.get("check-require"),
                    glob=fm.get("check-glob"), exclude=fm.get("check-exclude"),
                    projects=projects)
                if not v.promotable:
                    held.append((rel, v.reason))
                    continue
                if v.state == dw_verify.CLEAN:
                    scan_notes.append(f"{rel}: 검사대상 {v.candidates}건 · 위반 0")
            # 승격 — status:stable + scope 를 canonical 로 정규화(불일치 데이터 정리).
            snapshot.append((p, text))
            head = re.sub(r"^status:\s*draft\s*$", "status: stable", text[:fm_end],
                          count=1, flags=re.MULTILINE)
            if canon != str(fm.get("scope") or "").strip():
                head = re.sub(r"^scope:\s*.+$", f"scope: {canon}", head, count=1, flags=re.MULTILINE)
            # 이전 run 의 hold 주석 제거(승격됐으므로 더는 유효하지 않음).
            body = re.sub(r"<!-- ratify-hold:.*?-->\n*", "", text[fm_end:].lstrip("\n"),
                          flags=re.DOTALL)
            new = head + "\n" + body
            if not args.dry_run:
                p.write_text(new, encoding="utf-8")
            promoted.append(rel)

    # 승격분 검증 — 컴파일 깨지면 롤백
    rolled_back = False
    if promoted and not args.dry_run:
        r = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "dw-compile.py"),
                            "--vault", str(vault), "--out", str(vault / ".claude" / "skills"),
                            "--dry-run", "--strict"], capture_output=True, text=True)
        if r.returncode != 0:
            for p, orig in snapshot:
                p.write_text(orig, encoding="utf-8")
            rolled_back = True

    print(f"== SSOT 자동 비준 ==")
    # 스캔 대상을 **먼저** 보고한다 — 대상이 0 이면 이 아래 '위반 0' 은 아무 의미가 없다.
    if projects:
        print(f"  스캔 대상 {len(projects)}개 ({proj_src}): "
              + ", ".join(str(p) for p in projects))
    else:
        print(f"  ⚠️ 스캔 대상 프로젝트 0개 ({proj_src}) — check 패턴을 가진 규칙은 "
              f"검증 불가로 hold 된다. `make install-project P=/절대경로` 로 등록하라.")
    for n in scan_notes:
        print(f"    ✓ {n}")
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
