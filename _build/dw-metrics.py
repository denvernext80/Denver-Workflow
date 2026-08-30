#!/usr/bin/env python3
"""dw-metrics — repository 이력(history)을 **재현 가능한 Engineering Evidence(엔지니어링 증거)** 로
변환한다. Software 가 실제로 어떻게 만들어지고·검증되고·전달되는지 **관찰**하기 위한 Measure/Evidence
레이어이며, 성과를 과장하거나 인과(causation)를 증명하기 위한 것이 아니다.

핵심 원칙 — **Evidence first, interpretation second.**
  이 스크립트는 결정론(deterministic) raw dump + 집계(metrics.json·REPORT.md)만 만든다.
  LLM 해석(FACT/INFERENCE/UNKNOWN)은 /dw-metrics 커맨드 층에서 이 산출물을 읽은 **뒤에** 붙는다.
  즉 LLM 이 숫자를 직접 추측하거나 git history 를 기억으로 해석하지 않는다.

이 파일은 검증된 engineering-metrics 도구(extract.sh + analyze.py)의 **behavior-preserving
Python 포팅**이다 — 플러그인의 python3-only / make·bash 비의존 / Windows 이식성 SSOT 를 지키기
위해 bash 를 순수 stdlib subprocess 로 1:1 이식했다. 추출(extraction) semantics 와 raw evidence
schema, 집계(aggregation) semantics 는 **변경하지 않았다**.

사용:
    python3 dw-metrics.py [--project 경로] [--phases d1,d2] [--json] [--no-github] [--out 경로]

인자 없으면 현재 디렉토리를 대상 repo 로 자동 감지한다. GitHub remote 가 있으면 owner/repo 를
자동 감지하고, `gh` 가 없거나 --no-github 이면 Git-only mode 로 graceful 하게 동작한다.

산출(<repo>/.claude/dw-metrics/, gitignore 대상 — repo 오염 없음):
    raw/            결정론 원시 증거(numstat·commits·trailers·reverts·evolution·growth·gh dump)
    metrics.json    결정론 집계(머신 판독)
    REPORT.md       사람 판독 요약(관찰만 — 인과 표현 없음)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # git 빈 트리 — 최초부터의 diff 기준
# 개념 발생 추적 키워드 — extract.sh 와 동일(behavior-preserving). ⚠️ git --grep 은 기본 BRE 라
# '|' 가 리터럴이다(alternation 아님) — 단일 토큰 키워드만 매칭된다. 이 동작은 oracle 그대로
# 보존한다(고치면 extraction semantics 변경). 알려진 한계로 REPORT/문서에 명시.
EVOLUTION_KEYWORDS = [
    "계약|contract",
    "게이트|gate",
    "에이전트|agent|do-er|오케스트레이터|orchestrat",
    "ssot|vault|digest|다이제스트|정본",
    "가드|회귀|regression",
    "denver-workflow",
]
GOVERNANCE_FILES = ["CLAUDE.md", "AGENTS.md", ".claude", ".mcp.json"]


# ── 실행 헬퍼 (stdlib subprocess only) ────────────────────────────────────────────

def _run(argv, cwd=None):
    """(returncode, stdout_text) — stderr 는 삼킨다(oracle 의 2>/dev/null 등가)."""
    p = subprocess.run([str(a) for a in argv], cwd=cwd,
                       capture_output=True, text=True)
    return p.returncode, p.stdout


def git(repo, *args):
    """git -C <repo> … stdout(성공) / "" (실패). oracle 의 `g(){ git -C "$REPO" …; }` 등가."""
    rc, out = _run(["git", "-C", str(repo), *args])
    return out if rc == 0 else ""


def have(tool):
    return shutil.which(tool) is not None


def write(path, text):
    """POSIX 스타일 개행으로 기록(플랫폼 무관 byte 동일성 — oracle `>` 와 일치)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


# ── repo / remote / branch 자동 감지 ──────────────────────────────────────────────

def detect_repo(path):
    top = git(path, "rev-parse", "--show-toplevel").strip()
    return Path(top) if top else None


def detect_slug(repo):
    """origin remote → 'owner/repo'. 없으면 None (Git-only mode)."""
    url = (git(repo, "remote", "get-url", "origin").strip()
           or git(repo, "config", "--get", "remote.origin.url").strip())
    if not url:
        return None
    # git@host:owner/repo(.git)  |  https://host/owner/repo(.git)
    s = re.sub(r"^git@[^:]+:", "", url)
    s = re.sub(r"^https?://[^/]+/", "", s)
    s = re.sub(r"\.git$", "", s).strip("/")
    return s if "/" in s else None


def detect_branch(repo, override=None):
    """분석 ref. 우선순위: --branch/BRANCH env > origin/HEAD > origin/main > 로컬 HEAD."""
    if override:
        return override
    head = git(repo, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD").strip()
    if head:
        return head  # 예: origin/main
    for cand in ("origin/main", "origin/master"):
        if git(repo, "rev-parse", "--verify", "--quiet", cand).strip():
            return cand
    return "HEAD"


# ── EXTRACT (extract.sh 의 behavior-preserving 포팅) ───────────────────────────────

def extract(repo, slug, branch, raw, use_gh):
    """raw/ 에 결정론 원시 증거를 덤프. git 명령·출력 포맷은 extract.sh 와 1:1."""
    steps = []
    raw.mkdir(parents=True, exist_ok=True)

    # fetch(있으면 최신 ref) — 실패해도 로컬로 진행
    git(repo, "fetch", "origin", "--quiet")

    sha = git(repo, "rev-parse", branch).strip()
    first_lines = git(repo, "log", "--reverse", "--format=%ad", "--date=short", branch).splitlines()
    first = first_lines[0] if first_lines else "—"
    last = git(repo, "log", "-1", "--format=%ad", "--date=short", branch).strip() or "—"
    n_all = git(repo, "rev-list", "--count", branch).strip() or "0"
    n_fp = git(repo, "rev-list", "--count", "--first-parent", branch).strip() or "0"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    meta = (f"REPO={repo}\nSLUG={slug or '(no remote)'}\nBRANCH={branch}\n"
            f"REF_SHA={sha}\nANALYSIS_TS={ts}\nFIRST_COMMIT={first}\nLAST_COMMIT={last}\n"
            f"COMMITS_ALL={n_all}\nCOMMITS_FIRST_PARENT={n_fp}\n")
    write(raw / "_meta.txt", meta)
    steps.append("_meta.txt")

    # first-parent numstat — 크기/분류/속도의 정본(그대로 기록)
    write(raw / "firstparent_numstat.txt",
          git(repo, "log", "--first-parent", branch,
              "--pretty=format:@@COMMIT|%H|%ad|%s", "--date=short", "--numstat"))
    write(raw / "allcommits.txt",
          git(repo, "log", branch, "--pretty=format:%H|%ad", "--date=short"))
    steps += ["firstparent_numstat.txt", "allcommits.txt"]

    # trailers — AI-native 신호(공동저작/세션 트레일러 포함 커밋 수)
    def grep_commits(pattern):
        out = git(repo, "log", branch, "--format=%H", "--grep", pattern, "-i")
        return sum(1 for ln in out.splitlines() if ln.strip())
    write(raw / "trailers.txt",
          f"commits_all={n_all}\n"
          f"commits_with_claude_coauthor={grep_commits('Co-Authored-By: Claude')}\n"
          f"commits_with_claude_session={grep_commits('Claude-Session:')}\n")
    steps.append("trailers.txt")

    # governance/workflow 파일 최초 추가일
    rows = []
    wf = [f for f in git(repo, "ls-tree", "-r", "--name-only", branch,
                         "--", ".github/workflows").splitlines() if f.strip()]
    for f in GOVERNANCE_FILES + wf:
        adds = git(repo, "log", "--first-parent", "--diff-filter=A",
                   "--date=short", "--format=%ad", "--", f).splitlines()
        rows.append((adds[-1] if adds else "—", f))   # 가장 오래된 추가일
    # oracle 의 로케일 sort 는 누락(—) 행을 앞에 둔다 — 결정론+로케일 독립으로 동일 순서 재현.
    rows.sort(key=lambda r: (0 if r[0] == "—" else 1, r[0], r[1]))
    write(raw / "governance-adds.txt", "".join(f"{d}\t{f}\n" for d, f in rows))
    steps.append("governance-adds.txt")

    # reverts / reapply / hotfix (first-parent)
    rev_re = re.compile(r"revert|reapply|되돌|롤백|rollback|hotfix", re.I)
    rlines = [ln for ln in git(repo, "log", "--first-parent", branch,
                               "--date=short", "--format=%ad %h %s").splitlines()
              if rev_re.search(ln)]
    write(raw / "reverts.txt", ("".join(l + "\n" for l in rlines)) if rlines else "(none)\n")
    steps.append("reverts.txt")

    # evolution 키워드(개념 발생 추적) — git --grep BRE 동작 그대로(위 상수 주석 참조)
    ev = []
    for kw in EVOLUTION_KEYWORDS:
        ev.append(f"### {kw} ###\n")
        lines = git(repo, "log", branch, "-i", "--grep", kw, "--reverse",
                    "--date=short", "--format=%ad %h %s").splitlines()[:6]
        ev.append("".join(l + "\n" for l in lines))
        ev.append("\n")
    write(raw / "evolution.txt", "".join(ev))
    steps.append("evolution.txt")

    # codebase 성장 스냅샷(월 1일 기준)
    months = sorted(set(git(repo, "log", "--first-parent", "--format=%ad",
                            "--date=format:%Y-%m", branch).split()))
    growth = ["date\ttracked_files\tinsertions\n"]
    for m in months:
        snap = f"{m}-01"
        s = git(repo, "rev-list", "-1", "--first-parent", f"--before={snap}", branch).strip()
        if not s:
            continue
        files = len([x for x in git(repo, "ls-tree", "-r", "--name-only", s).splitlines() if x])
        short = git(repo, "diff", "--shortstat", EMPTY_TREE, s)
        mi = re.search(r"(\d+) insert", short)
        growth.append(f"{snap}\t{files}\t{mi.group(1) if mi else 0}\n")
    write(raw / "codebase-growth.tsv", "".join(growth))
    steps.append("codebase-growth.tsv")

    # ── GitHub 지표(gh 있고 slug 있고 --no-github 아닐 때만) ──────────────────────
    gh_mode = bool(use_gh and slug and have("gh"))
    if gh_mode:
        rc, out = _run(["gh", "pr", "list", "--repo", slug, "--state", "all",
                        "--limit", "5000", "--json",
                        "number,title,state,createdAt,mergedAt,closedAt,labels,headRefName,author"])
        write(raw / "prs.json", out if rc == 0 and out.strip() else "[]")

        rc, out = _run(["gh", "api", "--paginate",
                        f"repos/{slug}/actions/workflows/deploy.yml/runs?per_page=100",
                        "--jq", ".workflow_runs[] | [.conclusion,(.created_at[0:10])] | @tsv"])
        write(raw / "deploy_runs.tsv", out if rc == 0 else "")

        def wf_total(wf_name, status=None):
            q = f"repos/{slug}/actions/workflows/{wf_name}/runs?per_page=1"
            if status:
                q += f"&status={status}"
            rc, out = _run(["gh", "api", q, "--jq", ".total_count"])
            try:
                return int(out.strip()) if rc == 0 else 0
            except ValueError:
                return 0
        rc, out = _run(["gh", "api", f"repos/{slug}/actions/runs?per_page=1", "--jq", ".total_count"])
        try:
            all_runs = int(out.strip()) if rc == 0 else 0
        except ValueError:
            all_runs = 0
        run_counts = {
            "all_workflow_runs": all_runs,
            "deploy": {"total": wf_total("deploy.yml"), "success": wf_total("deploy.yml", "success"),
                       "failure": wf_total("deploy.yml", "failure")},
            "ci": {"total": wf_total("ci.yml"), "success": wf_total("ci.yml", "success"),
                   "failure": wf_total("ci.yml", "failure")},
            "pr_review": {"total": wf_total("dw-pr-review.yml"),
                          "success": wf_total("dw-pr-review.yml", "success"),
                          "failure": wf_total("dw-pr-review.yml", "failure")},
        }
        write(raw / "run-counts.json", json.dumps(run_counts, ensure_ascii=False, indent=2) + "\n")
        steps += ["prs.json", "deploy_runs.tsv", "run-counts.json"]
    else:
        write(raw / "prs.json", "[]")
        note = "gh 미설치/미인증 또는 remote 없음 — GitHub 지표 없음(Git-only mode)"
        write(raw / "run-counts.json", json.dumps({"note": note}, ensure_ascii=False) + "\n")
        write(raw / "deploy_runs.tsv", "")

    return steps, gh_mode


# ── ANALYZE (analyze.py 의 결정론 집계 — semantics 그대로) ──────────────────────────

def parse_numstat(path):
    commits, cur = [], None
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("@@COMMIT|"):
                if cur:
                    commits.append(cur)
                _, sha, d, subj = line.split("|", 3)
                cur = {"sha": sha, "date": d, "subj": subj, "add": 0, "del": 0, "files": 0}
            elif line.strip() and cur is not None:
                parts = line.split("\t")
                if len(parts) == 3:
                    a, dl, _p = parts
                    cur["files"] += 1
                    if a.isdigit():
                        cur["add"] += int(a)
                    if dl.isdigit():
                        cur["del"] += int(dl)
        if cur:
            commits.append(cur)
    commits.reverse()
    return commits


def classify(subj):
    m = re.match(r"^(\w+)(\([^)]*\))?!?:", subj)
    t = (m.group(1).lower() if m else None)
    scope = (m.group(2) or "").lower() if m else ""
    if t == "feat":
        return "feature"
    if t == "fix":
        return "bugfix"
    if t in ("refactor", "perf"):
        return "refactor"
    if t in ("ci", "build", "infra", "deploy", "ops"):
        return "infra"
    if t == "test":
        return "test"
    if t == "docs":
        return "docs"
    if t == "chore":
        return "dependency/security" if re.search(r"dep|secur|sec", scope) else "chore"
    if t == "style":
        return "chore"
    return "기타(non-conforming)"


def _ym(d):
    return d[:7]


def _has_pr(subj):
    return bool(re.search(r"\(#\d+\)\s*$", subj))


def _is_revert(subj):
    return bool(re.search(r"revert|reapply|되돌|롤백|rollback", subj, re.I))


def _is_hotfix(subj):
    return bool(re.search(r"hotfix", subj, re.I))


def _days_incl(a, b):
    fmt = "%Y-%m-%d"
    return (datetime.strptime(b, fmt) - datetime.strptime(a, fmt)).days + 1


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _load_kv(path):
    kv = {}
    if path.exists():
        for ln in open(path, encoding="utf-8"):
            if "=" in ln:
                k, v = ln.rstrip("\n").split("=", 1)
                kv[k] = v
    return kv


def analyze(raw, phases_arg):
    """analyze.py 의 summary 구조를 그대로 산출(집계 semantics 불변). +phases(계산은 동일)."""
    numstat = raw / "firstparent_numstat.txt"
    commits = parse_numstat(numstat)
    n = len(commits)
    if n == 0:
        raise SystemExit("❌ first-parent 커밋이 없습니다 — 빈 저장소이거나 잘못된 branch.")
    meta = _load_kv(raw / "_meta.txt")
    prs = _load_json(raw / "prs.json", [])
    runs = _load_json(raw / "run-counts.json", {})
    summary = {}

    d0, d1 = commits[0]["date"], commits[-1]["date"]
    span = _days_incl(d0, d1)
    summary["period"] = {"first": d0, "last": d1, "days": span,
                         "commits_all": meta.get("COMMITS_ALL"), "first_parent": n}
    if prs:
        st = Counter(p["state"] for p in prs)
        summary["prs"] = {"total": len(prs), **st}
        merged = sum(1 for p in prs if p["state"] == "MERGED")
        summary["velocity"] = {"merged": merged, "per_week": round(merged / (span / 7), 1)}

    bym = defaultdict(list)
    for c in commits:
        bym[_ym(c["date"])].append(c)
    monthly = {}
    for m in sorted(bym):
        cs = bym[m]
        fl = sorted(c["files"] for c in cs)
        pr = sum(1 for c in cs if _has_pr(c["subj"]))
        monthly[m] = {"prs": len(cs), "add": sum(c["add"] for c in cs),
                      "del": sum(c["del"] for c in cs),
                      "pr_discipline_pct": round(100 * pr / len(cs))}
    summary["monthly"] = monthly

    summary["classification"] = dict(Counter(classify(c["subj"]) for c in commits))

    fs = sorted(c["files"] for c in commits)
    add = sum(c["add"] for c in commits)
    dele = sum(c["del"] for c in commits)
    summary["size"] = {"mean_files": round(sum(fs) / n, 1), "median_files": fs[n // 2],
                       "add": add, "del": dele,
                       "small_pct": round(100 * sum(1 for c in commits if c["files"] <= 5) / n),
                       "large_pct": round(100 * sum(1 for c in commits if c["files"] > 20) / n)}

    summary["runs"] = runs

    rev = [c for c in commits if _is_revert(c["subj"])]
    summary["stability"] = {"reverts": len(rev), "revert_pct": round(100 * len(rev) / n, 1),
                            "hotfix": sum(1 for c in commits if _is_hotfix(c["subj"])),
                            "reverts_by_month": dict(sorted(Counter(_ym(c["date"]) for c in rev).items()))}

    tr = _load_kv(raw / "trailers.txt")
    if tr:
        summary["ai_native"] = tr

    # phases — analyze.py 가 계산·출력하던 것과 동일(경계 주어질 때만). additive 직렬화.
    if phases_arg:
        bounds = [b.strip() for b in phases_arg.split(",") if b.strip()]

        def phase(d):
            for i, b in enumerate(bounds):
                if d < b:
                    return f"P{i + 1} (<{b})"
            return f"P{len(bounds) + 1} (>={bounds[-1]})"

        ph = defaultdict(list)
        for c in commits:
            ph[phase(c["date"])].append(c)
        phases = {}
        for p in sorted(ph):
            cs = ph[p]
            fp = len(cs)
            fl = sorted(c["files"] for c in cs)
            phases[p] = {
                "prs": fp,
                "pr_discipline_pct": round(100 * sum(1 for c in cs if _has_pr(c["subj"])) / fp),
                "median_files": fl[len(fl) // 2],
                "test_pct": round(100 * sum(1 for c in cs if classify(c["subj"]) == "test") / fp),
                "bugfix_pct": round(100 * sum(1 for c in cs if classify(c["subj"]) == "bugfix") / fp),
                "revert_pct": round(100 * sum(1 for c in cs if _is_revert(c["subj"])) / fp, 1),
            }
        summary["phases"] = {"bounds": bounds, "buckets": phases}

    summary["_meta"] = {"slug": meta.get("SLUG"), "ref": meta.get("REF_SHA"),
                        "analysis_ts": meta.get("ANALYSIS_TS"), "branch": meta.get("BRANCH")}
    return summary


# ── REPORT.md 렌더 (관찰만 — 인과 표현 없음) ───────────────────────────────────────

def render_report(summary, gh_mode):
    m = summary["_meta"]
    per = summary["period"]
    s = summary["size"]
    st = summary["stability"]
    L = []
    L.append(f"# Engineering Evidence — {m.get('slug') or '(local repo)'}")
    L.append("")
    L.append(f"> 분석 ref `{(m.get('ref') or '')[:12]}` ({m.get('branch')}) · 생성 "
             f"{m.get('analysis_ts')} · mode **{'GitHub-enhanced' if gh_mode else 'Git-only'}**")
    L.append(">")
    L.append("> **관찰(observation) 리포트.** 아래는 git/GitHub 이력에서 결정론적으로 계산한 수치다. "
             "성과·품질을 단정하지 않으며, 상관을 인과로 표현하지 않는다. 해석은 이 증거 위에서 별도로 이뤄진다.")
    L.append("")

    L.append("## 기간·규모 (period & scale)")
    L.append(f"- 기간: **{per['first']} → {per['last']}** ({per['days']}일 ≈ {per['days']/7:.1f}주)")
    L.append(f"- 커밋: all **{per['commits_all']}** · first-parent(머지 단위) **{per['first_parent']}**")
    if summary.get("prs"):
        p = summary["prs"]
        states = " · ".join(f"{k} {v}" for k, v in p.items() if k != "total")
        L.append(f"- PR: total **{p['total']}** ({states})")
    if summary.get("velocity"):
        v = summary["velocity"]
        L.append(f"- 처리량: 병합 PR **{v['merged']}** → 주당 **{v['per_week']}**")
    L.append("")

    L.append("## 변경 성격 (change classification)")
    L.append("> 기준: conventional-commit 접두사 정규식. 비접두는 강제 분류하지 않고 `기타`로 둔다.")
    L.append("")
    L.append("| 분류 | 건수 | 비율 |")
    L.append("|---|---:|---:|")
    total = per["first_parent"]
    for k, v in sorted(summary["classification"].items(), key=lambda kv: -kv[1]):
        L.append(f"| {k} | {v} | {100*v/total:.1f}% |")
    L.append("")

    L.append("## 변경 크기 (change size)")
    L.append(f"- 파일/PR: 평균 **{s['mean_files']}** · 중앙값 **{s['median_files']}**")
    L.append(f"- 라인: **+{s['add']} / -{s['del']}** (net {s['add']-s['del']:+})")
    L.append(f"- 분포: 소형(≤5파일) **{s['small_pct']}%** · 대형(>20파일) **{s['large_pct']}%**")
    L.append("")

    L.append("## 월별 활동 (monthly activity)")
    L.append("| 월 | first-parent PR | +add | -del | median files | via (#N) |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for mo, d in summary["monthly"].items():
        L.append(f"| {mo} | {d['prs']} | {d['add']} | {d['del']} | — | {d['pr_discipline_pct']}% |")
    L.append("")

    runs = summary.get("runs", {})
    if runs and "note" not in runs:
        L.append("## 전달·CI 활동 (delivery & CI) — live 값")
        dp = runs.get("deploy", {})
        if dp.get("total"):
            rate = 100 * dp["success"] / dp["total"]
            L.append(f"- deploy 워크플로 실행 **{dp['total']}** · 성공 {dp['success']} ({rate:.1f}%) · "
                     f"실패 {dp['failure']} · 일평균 {dp['total']/per['days']:.1f}")
        ci = runs.get("ci", {})
        conc = (ci.get("success", 0) or 0) + (ci.get("failure", 0) or 0)
        if conc:
            L.append(f"- ci 워크플로 실행 total {ci.get('total')} · 실패율 {100*ci['failure']/conc:.1f}% (결론 {conc})")
        if runs.get("all_workflow_runs"):
            L.append(f"- 전체 워크플로 실행 **{runs['all_workflow_runs']}**")
        L.append(">")
        L.append("> ⚠️ CI/deploy 실패를 **production defect·incident 로 해석하지 않는다** — 상당수는 "
                 "게이트가 프로덕션 도달 전에 차단한 것일 수 있다(원인 미분류). run count 는 실행 시점에 따라 증가하는 live 값.")
    else:
        L.append("## 전달·CI 활동")
        L.append("- (Git-only mode — GitHub Actions 지표 없음. `gh` 인증 시 배포·CI 지표가 추가된다.)")
    L.append("")

    L.append("## 안정성 신호 (stability signals)")
    L.append(f"- revert: **{st['reverts']}** ({st['revert_pct']}% of first-parent)")
    L.append(f"- hotfix: **{st['hotfix']}** — 발견된 버그를 해소하는 corrective change 로 분류")
    if st.get("reverts_by_month"):
        L.append(f"- revert 월별: {st['reverts_by_month']}")
    L.append(">")
    L.append("> ⚠️ revert·hotfix 를 production outage 로 단정하지 않는다. git 이력만으로는 사용자 영향·실제 장애 여부를 확인할 수 없다(UNKNOWN).")
    L.append("")

    if summary.get("ai_native"):
        ai = summary["ai_native"]
        co = int(ai.get("commits_with_claude_coauthor", 0) or 0)
        allc = int(ai.get("commits_all", 0) or 0)
        L.append("## AI-assisted 개발 흔적 (traces)")
        if allc:
            L.append(f"- Claude 공동저작 트레일러 포함 커밋: **{co}/{allc} ({100*co/allc:.0f}%)**")
        L.append(f"- `Claude-Session:` 트레일러: {ai.get('commits_with_claude_session','?')}")
        L.append("")

    if summary.get("phases"):
        ph = summary["phases"]
        L.append(f"## 페이즈 비교 (경계 {ph['bounds']})")
        L.append("> 페이즈 차이는 **관측된 변화**일 뿐 — 프로젝트 성숙·기능 믹스 등 교란요인이 있어 특정 규칙 '덕분'이라 단정하지 않는다.")
        L.append("")
        L.append("| phase | PR | via(#N) | median files | test% | bugfix% | revert% |")
        L.append("|---|---:|---:|---:|---:|---:|---:|")
        for p, d in ph["buckets"].items():
            L.append(f"| {p} | {d['prs']} | {d['pr_discipline_pct']}% | {d['median_files']} | "
                     f"{d['test_pct']}% | {d['bugfix_pct']}% | {d['revert_pct']}% |")
        L.append("")

    L.append("---")
    L.append("### 근거·한계 (evidence & limitations)")
    L.append("- **FACT**: 위 수치는 raw/ 의 결정론 덤프에서 재계산 가능하다.")
    L.append("- **INFERENCE**: 분류·페이즈 해석 등은 규칙 기반 추정이며 인과가 아니다.")
    L.append("- **UNKNOWN**: production incident·사용자 영향·실제 장애 여부는 git/GitHub 이력만으로 확인 불가.")
    L.append("- 개념 발생 추적(`raw/evolution.txt`)의 키워드 검색은 git `--grep` 기본(BRE)이라 `|` alternation 이 "
             "동작하지 않는다(단일 토큰만 매칭) — oracle 동작 보존. 넓은 탐색이 필요하면 raw 로 별도 grep 하라.")
    return "\n".join(L) + "\n"


# ── main ──────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(prog="dw-metrics",
                                 description="repository 이력 → 재현 가능한 Engineering Evidence")
    ap.add_argument("--project", "-p", default=None, help="대상 repo 경로(생략 = 현재 디렉토리)")
    ap.add_argument("--phases", default="", help="쉼표구분 경계일 (예: 2026-07-05,2026-08-11)")
    ap.add_argument("--json", action="store_true", help="metrics.json 을 stdout 에도 출력")
    ap.add_argument("--no-github", action="store_true", help="gh 무시(Git-only mode)")
    ap.add_argument("--branch", default=os.environ.get("BRANCH"), help="분석 ref(생략 = origin/HEAD→main)")
    ap.add_argument("--out", default=None, help="출력 경로(생략 = <repo>/.claude/dw-metrics)")
    args = ap.parse_args(argv)

    if not have("git"):
        print("❌ git 이 필요합니다.", file=sys.stderr)
        return 1
    start = Path(args.project).expanduser().resolve() if args.project else Path.cwd().resolve()
    repo = detect_repo(start)
    if not repo:
        print(f"❌ git 저장소가 아닙니다: {start}", file=sys.stderr)
        print("   --project <repo 경로> 로 대상 저장소를 지정하세요.", file=sys.stderr)
        return 1

    slug = detect_slug(repo)
    branch = detect_branch(repo, args.branch)
    use_gh = not args.no_github
    out = Path(args.out).expanduser().resolve() if args.out else repo / ".claude" / "dw-metrics"
    raw = out / "raw"

    print(f"▶ 대상 repo: {repo}")
    print(f"▶ remote: {slug or '(없음 → Git-only)'} · ref: {branch}")
    mode_gh = bool(use_gh and slug and have('gh'))
    print(f"▶ mode: {'GitHub-enhanced' if mode_gh else 'Git-only'} · 출력: {out}")
    print("▶ EXTRACT (결정론 raw evidence)…")
    steps, gh_mode = extract(repo, slug, branch, raw, use_gh)
    print(f"   raw/ 생성: {', '.join(steps)}")

    print("▶ ANALYZE (결정론 집계)…")
    summary = analyze(raw, args.phases)
    write(out / "metrics.json", json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    write(out / "REPORT.md", render_report(summary, gh_mode))

    per = summary["period"]
    print("✅ 완료 — Evidence first, interpretation second")
    print(f"   기간 {per['first']}→{per['last']} ({per['days']}일) · first-parent {per['first_parent']}"
          + (f" · 병합 PR {summary['velocity']['merged']}" if summary.get('velocity') else ""))
    print(f"   → {out}/metrics.json · {out}/REPORT.md · {raw}/")
    if args.json:
        print("\n===JSON===")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
