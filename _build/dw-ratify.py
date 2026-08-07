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

OBEY = {"rule", "guidance", "procedure"}
REQUIRED = {
    "rule": ["type", "scope", "status", "enforced-by", "compiles-to"],
    "guidance": ["type", "scope", "status", "compiles-to"],
    "procedure": ["type", "scope", "status", "compiles-to"],
}
# 코드베이스 스캔 시 건너뛸 디렉터리 — os.walk 의 dirnames 를 **프루닝**한다(하위로 내려가지 않는다).
# 종전엔 rglob 로 전부 순회한 뒤 사후 필터해서, 건너뛸 트리의 walk 비용을 그대로 냈다(3레포 8.8s/규칙).
#
# ⚠️ `ios`·`android` 를 여기서 **뺐다**. 그것들 탓에 `ios/**/project.pbxproj` 를 노리는 규칙은
#   `--project` 를 줘도 **검사 대상이 0 건**이었다(2026-08-07 실측). 대신 그 아래 **무거운 산출물
#   디렉터리만** 좁혀 막는다 — ios/ 는 878 → 102 파일로 줄고 Runner.xcodeproj 는 스캔된다.
SKIP = {
    # VCS·의존성·에디터
    ".git", ".venv", "node_modules", "vendor", "__pycache__", ".claude", ".obsidian",
    # 빌드 산출물(공통)
    "build", "dist", "_build", ".dart_tool", ".bkit",
    # 빌드 산출물·벤더 트리(모바일·러스트·웹) — ios·android 를 열면서 대신 좁혀 막는 대상.
    # Pods 엔 벤더된 project.pbxproj 사본이 3개 있어(실측) 열어두면 그대로 오탐 후보가 된다.
    "Pods", "DerivedData", ".symlinks", "ephemeral", ".gradle", "Carthage",
    "target", ".next", "coverage",
    # git worktree 디렉터리 — 같은 코드의 사본이라 검사대상을 부풀리고 중복 보고를 낳는다
    # (실측: 레포 안 worktree 사본의 project.pbxproj 가 본체와 나란히 후보로 잡혔다).
    # 본체 체크아웃에서 이미 검사된다.
    ".worktrees", "_worktrees",
}
# 스캔 대상 프로젝트 레지스트리 — vault CONTENT_DIRS **밖**(.dw-state/)에 둔다(검색·graphify·컴파일
# 무오염 — dw_access_log.py 와 동일 규약). `make install-project`(wire-hook.py)가 등록한다.
STATE_DIR = ".dw-state"
PROJECTS_JSON = "projects.json"
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


def as_list(v) -> list[str]:
    if not v:
        return []
    return [str(x) for x in v] if isinstance(v, list) else [str(v)]


def matches_glob(rel: str, patterns: list[str]) -> bool:
    base = rel.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(base, p) for p in patterns)


def registered_projects(vault: Path) -> list[Path]:
    """`<vault>/.dw-state/projects.json` 에 등록된 스캔 대상 레포.

    정본을 여기 두는 이유: ① 엔진 코드에 사용자 경로를 하드코딩하면 공개 플러그인이 특정
    워크스페이스에 묶인다(이 레포는 `_seed` 에서 사적 데이터를 배제하는 규율을 이미 갖고 있다)
    ② `~/.claude.json` 의 projects 맵은 **한 번도 열지 않은 레포를 빠뜨린다**(실측: 3개 중 2개 누락)
    ③ `make install-project` 가 이미 프로젝트↔vault 를 잇고 있으니, 그 역링크만 남기면 사람이
    크론·스케줄에서 인자를 줄 필요가 없다.
    """
    f = vault / STATE_DIR / PROJECTS_JSON
    if not f.is_file():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out = []
    for s in data.get("projects", []):
        p = Path(str(s)).expanduser()
        if p.is_dir():
            out.append(p.resolve())
    return out


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
                glob = as_list(fm.get("check-glob"))
                deny = as_list(fm.get("check-deny"))
                require = as_list(fm.get("check-require"))
                # ⚠️ 아래 게이트는 **check 패턴이 있는 규칙에만** 적용된다. 검사 없는 서술 규칙·
                #    guidance·procedure 는 검증할 대상이 없으므로 여기 오지 않는다(큐 정체 방지).
                if (deny or require):
                    if not glob:
                        held.append((rel, "check 패턴은 있으나 check-glob 없음(검사 비활성 — 무의미)"))
                        continue
                    # ① 스캔할 코드베이스가 없으면 '오탐 0' 을 주장할 수 없다. 종전엔 이 경우
                    #    scan 루프가 한 번도 돌지 않아 hits=[] → **무조건 승격**됐다(가짜 green).
                    if not projects:
                        held.append((rel, f"스캔 대상 프로젝트 0 ({proj_src}) — 오탐 0 을 검증할 코드가 "
                                          f"없다. `make install-project P=/절대경로` 로 레포를 등록하거나 "
                                          f"`make ratify RATIFY_PROJECTS=\"/abs/repo1 /abs/repo2\"` 로 주라."))
                        continue
                    hits, cand = scan_codebase(projects, glob,
                                               as_list(fm.get("check-exclude")), deny, require)
                    if hits:
                        held.append((rel, f"기존 코드에 {len(hits)}건 매치(검사대상 {cand}건) — "
                                          f"진짜위반/오탐 판단 필요. 예: {hits[0]}"))
                        continue
                    # ② 검사 대상이 0 건이면 '위반 0' 은 공허하다 — 비교 대상이 비어 있음을
                    #    성공으로 보고하지 않는다(vault stable 규칙: 「검증 장치는 비교 대상이
                    #    비어있지 않음을 먼저 증명하라 — 0건을 성공으로 보고하는 게이트 금지」).
                    if cand == 0:
                        held.append((rel, f"검사대상 파일 0건 — check-glob {glob} 이 등록 레포 "
                                          f"{len(projects)}개에서 아무 파일도 매치하지 않는다. 위반 0 은 "
                                          f"공허하다(검증 불가). glob 오타/경로 착오인지 확인하고, "
                                          f"대상이 아직 없는 선제 규칙이면 사람이 승인하라."))
                        continue
                    scan_notes.append(f"{rel}: 검사대상 {cand}건 · 위반 0")
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
