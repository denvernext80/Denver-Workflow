#!/usr/bin/env python3
"""dw-verifier-scope — 검증자 디스패치 relevance-gate (결정론, 토큰 절감).

문제: code-review/security-qa/design-review 검증자가 관련 없는 변경에도 판단으로 디스패치돼
작업당 무거운 서브에이전트 토큰을 태운다. 이 스크립트는 **바뀐 파일**을 도메인 글롭과 대조해
**실제로 필요한 검증자만** 결정론적으로 반환한다. 어떤 규칙도 약화하지 않는다 — 리뷰할 게
0인 검증자를 안 부를 뿐이다.

usage:
    python dw-verifier-scope.py --repo /abs/repo --base <base-branch>   # git 으로 변경파일 산출
    python dw-verifier-scope.py --files - <<< "src/a.php\nlib/x.dart"    # 파일목록 직접
    (--json 으로 기계가독)

정책:
  - 문서/설정만 변경(*.md, docs/**, *.lock, 이미지 등) → 검증자 0(전부 스킵).
  - 코드 변경 있으면 code-review 는 기본 포함(구조 리뷰는 grep 이 대체 못 함).
  - design-review: UI/디자인 파일(*.dart, home-frontend/**, templates/**, *.css …) 있을 때만.
  - security-qa: 백엔드·인증·네트워크·토큰 파일 있을 때만.
도메인 맵은 아래 DOMAINS 로 조절(레포 무관 글롭). 표준 라이브러리만.

## ⚠️ fail-safe 극성 — 「판정 불가」는 스킵이 아니라 전량 디스패치다

호출 규약이 *「`dispatch` 만 부르고 `skip` 은 안 부른다」*(dispatch-discipline)라, 이 도구가
변경 집합을 **틀리게 비워** 내면 그대로 **검수 없는 머지**가 된다. 비용이 비대칭이다 —
불필요한 디스패치는 토큰이고, 누락된 디스패치는 리뷰되지 않은 코드다. 그래서 **확신할 수
없는 모든 경우를 「전량 디스패치」로 착지**시키고, 무엇을 비교했는지(repo·해석된 SHA·소스별
파일 수)를 함께 출력해 사람이 오판을 알아챌 표면을 남긴다.

2.20.1 까지 있던 조용한 fail-open **넷**을 닫은 자리다(issue 25):
  (A) `except Exception: return []` — base 오타·타임아웃·repo 아님이 전부 「검증 불필요」로 착지.
  (B) `returncode` 미확인 — `git diff <base>...HEAD` 가 실패해도 stdout 이 빌 뿐이라 그대로 진행.
  (C) 「변경 0개」와 「판정 불가」를 구별하지 않음 — 격리 워크트리 규율(do-er 는 항상 워크트리에서
      일한다) 하에서 메인 체크아웃을 가리키면 **정상 경로가 항상 위음성**을 냈다.
  (D) 변경 수집이 커밋범위 + unstaged 뿐 — **staged·untracked 를 못 봤다.** 워크트리 생성 →
      신규 파일 작성 → `git add` → 커밋 전 게이트 호출이 정확히 그 상태다. 부분 케이스
      (unstaged `.md` 1개 + staged 코드 10개)는 집합이 비지 않아 「판정 가능」으로 확정되며
      **「변경 1개(코드 0개) → 전부 스킵」** 으로 (C) 의 안전망마저 우회했다.

종료 코드 규약은 **바뀌지 않았다** — 판정 불가에서도 0 이다. 이 경우 도구는 실패한 게 아니라
안전한 답(전량 디스패치)을 성공적으로 냈다. 비영 종료는 `make verifier-scope` 를 깨고 호출자에게
「도구 고장」으로 읽혀 결과를 무시할 여지를 준다 — 최악의 극성이다. (argparse 사용법 오류만 2.)
출력도 `디스패치:`/`스킵:` 줄을 그대로 유지하고 근거를 **위에 덧붙이기만** 한다(파서 무손상).
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys

GIT_TIMEOUT = 20

# 검증자 → 도메인 글롭. fnmatch 의 '*' 는 '/' 도 넘으므로 "*.dart" 는 모든 깊이의 .dart 를,
# "*token*" 는 경로 어디든 token 포함을 매치한다(별도 **/ 폴백 불필요).
DOMAINS = {
    "design-review": [                        # UI/디자인 표면
        "*.dart",                             # Flutter(대부분 UI)
        "home-frontend/*", "templates/*", "og-bg/*", "public/*",
        "*.css", "*.scss",
    ],
    "security-qa": [                          # 보안-민감 표면만(순수 UI 는 제외)
        "*.php", "migrations/*", "config/*",  # 백엔드(SQL·이스케이프·쿠키·스코핑)
        "*auth*", "*oauth*", "*session*", "*cookie*", "*token*", "*login*",
        "*secure*", "*password*", "*sql*", "*query*", "*http*", "*network*", "*api*",
    ],
}
# 문서/설정 등 '코드 아님' — 이것만 바뀌면 code-review 도 스킵.
NONCODE = [
    "*.md", "docs/*", "*.lock",
    "*.png", "*.jpg", "*.jpeg", "*.svg", "*.gif", "*.webp",
    "*.gitignore", "*.example", "LICENSE", "*.txt",
]

ALL_VERIFIERS = ("code-review", "design-review", "security-qa")


def _match_any(path: str, globs) -> bool:
    p = path.replace("\\", "/")
    return any(fnmatch.fnmatch(p, g) for g in globs)


def _git(repo: str, args: list[str]) -> tuple[int, str, str]:
    """git 을 돌려 (returncode, stdout, stderr) 를 준다.

    예외를 **삼키지 않는다** — 타임아웃·git 부재·경로 오류는 rc=-1 + stderr 문면으로 승격해
    호출부가 「판정 불가」로 처리하게 한다. 종전엔 이게 `return []`(= 전부 스킵)이었다.
    """
    try:
        p = subprocess.run(["git", "-C", repo] + args,
                           capture_output=True, text=True, timeout=GIT_TIMEOUT)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"타임아웃({GIT_TIMEOUT}s): git {' '.join(args)}"
    except OSError as e:                      # git 부재, repo 경로 없음 등
        return -1, "", f"{type(e).__name__}: {e}"


def _lines(out: str) -> list[str]:
    return [l.strip() for l in out.splitlines() if l.strip()]


def _first_err(stderr: str) -> str:
    e = _lines(stderr)
    return e[0] if e else "(stderr 없음)"


def _short(sha) -> str:
    return sha[:8] if sha else "?"


def _branch_name(full: str) -> str | None:
    """`refs/heads/x` · `refs/remotes/origin/x` → `x`. 분리(detached)면 None.

    `origin/main` 과 `main` 을 **같은 브랜치**로 보기 위한 정규화다 — 사고 실측에서 base 는
    `origin/main`, HEAD 는 `main` 이었다.
    """
    full = (full or "").strip()
    if not full or full == "HEAD":
        return None
    if full.startswith("refs/heads/"):
        return full[len("refs/heads/"):]
    if full.startswith("refs/remotes/"):
        rest = full[len("refs/remotes/"):]
        return rest.split("/", 1)[1] if "/" in rest else rest
    return None


def _worktrees(repo: str) -> list[dict]:
    """형제 워크트리 열거(best-effort — 실패해도 판정에 영향 주지 않는다)."""
    rc, out, _ = _git(repo, ["worktree", "list", "--porcelain"])
    if rc != 0:
        return []
    trees, cur = [], {}
    for line in out.splitlines():
        if not line.strip():
            if cur:
                trees.append(cur)
            cur = {}
        elif line.startswith("worktree "):
            cur["path"] = line[len("worktree "):].strip()
        elif line.startswith("HEAD "):
            cur["head"] = line[len("HEAD "):].strip()
        elif line.startswith("branch "):
            cur["branch"] = line[len("branch "):].strip().replace("refs/heads/", "")
        elif line.strip() == "detached":
            cur["branch"] = "(detached)"
    if cur:
        trees.append(cur)
    return trees


def collect(repo: str, base: str) -> dict:
    """변경 파일 + 「무엇을 비교했는지」 근거를 모은다.

    반환 dict 의 `undetermined` 가 True 면 변경 집합을 신뢰할 수 없다는 뜻이며,
    호출부는 이를 **전량 디스패치**로 착지시킨다(스킵 아님).
    """
    ev = {
        "repo": repo, "base_ref": base, "base_sha": None,
        "head_sha": None, "head_ref": None,
        "sources": {}, "worktrees": [], "files": [],
        "undetermined": False, "reason": None,
    }

    def undet(reason: str) -> dict:
        ev["undetermined"] = True
        ev["reason"] = reason
        ev["worktrees"] = ev["worktrees"] or _worktrees(repo)
        return ev

    # ── ① ref 해석. 여기서 실패하면 그 뒤 diff 는 전부 무의미하다.
    #     HEAD 를 **먼저** 푼다 — base 가 깨져도 「어느 트리를 보고 있었나」는 출력돼야
    #     사람이 원인 구간을 가른다(base 오타인가, 엉뚱한 체크아웃인가).
    rc, out, err = _git(repo, ["rev-parse", "--verify", "HEAD^{commit}"])
    if rc != 0:
        return undet(f"HEAD 를 해석하지 못했다(git repo 아님·빈 레포?) — {_first_err(err)}")
    ev["head_sha"] = out.strip()

    rc, out, _ = _git(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
    ev["head_ref"] = out.strip() if rc == 0 else "(unknown)"
    ev["worktrees"] = _worktrees(repo)

    rc, out, err = _git(repo, ["rev-parse", "--verify", f"{base}^{{commit}}"])
    if rc != 0:
        return undet(f"base ref '{base}' 를 해석하지 못했다 — {_first_err(err)}")
    ev["base_sha"] = out.strip()

    # ── ② base 와 HEAD 의 관계. 「비어 있는 diff」가 구조적으로 확정된 상태를 걸러낸다.
    rc, _, err = _git(repo, ["merge-base", base, "HEAD"])
    if rc == 1:
        return undet(f"base '{base}' 와 HEAD 에 공통 조상이 없다(무관계한 히스토리) — 비교 자체가 무의미")
    if rc != 0:
        return undet(f"merge-base 판정 실패 — {_first_err(err)}")

    # rc 0=ancestor, 1=아님, 그 이상은 에러 — 에러를 「ancestor 아님」으로 접으면 새 fail-open.
    rc, _, err = _git(repo, ["merge-base", "--is-ancestor", "HEAD", base])
    if rc < 0 or rc > 1:
        return undet(f"HEAD/base 선후 판정 실패 — {_first_err(err)}")
    if rc == 0 and ev["head_sha"] != ev["base_sha"]:
        return undet(
            f"HEAD({_short(ev['head_sha'])}) 가 base '{base}'({_short(ev['base_sha'])}) 보다 "
            "뒤처져 있다 — 커밋 범위가 구조적으로 비어 판정이 불가능하다. "
            "작업 중인 격리 워크트리가 아니라 낡은 메인 체크아웃을 가리키고 있지 않은가?")

    # ── ②b 「작업 브랜치가 아니다」. do-er 규율상 base 브랜치 위에서 작업하는 일이 없으므로,
    #     HEAD 가 base 브랜치 «자체» 면 작업 트리를 가리키고 있지 않다는 뜻이다. 이게 실제
    #     사고의 서명이었다(base=origin/main, HEAD=main).
    rc, out, _ = _git(repo, ["rev-parse", "--symbolic-full-name", "HEAD"])
    head_branch = _branch_name(out) if rc == 0 else None
    rc, out, _ = _git(repo, ["rev-parse", "--symbolic-full-name", base])
    base_branch = _branch_name(out) if rc == 0 else None
    if head_branch is not None and base_branch is not None and head_branch == base_branch:
        return undet(
            f"HEAD 가 base 브랜치 자체('{head_branch}')를 가리킨다 — 작업 브랜치가 아니다. "
            "격리 워크트리의 작업 브랜치를 --repo 로 넘겼는지 확인하라")
    if head_branch is None and ev["head_sha"] == ev["base_sha"]:
        return undet("HEAD 가 base 와 같은 커밋에 분리(detached)돼 있다 — 작업 브랜치가 아니다")

    # ── ③ 변경 수집. 넷 다 봐야 한다 — 커밋범위·unstaged·staged·untracked.
    #     staged/untracked 누락이 (D): 워크트리에서 `git add` 후 커밋 전 게이트가 정확히 그 상태다.
    sources = [
        ("committed", ["diff", "--name-only", f"{base}...HEAD"]),
        ("unstaged", ["diff", "--name-only"]),
        ("staged", ["diff", "--cached", "--name-only"]),
        ("untracked", ["ls-files", "--others", "--exclude-standard"]),
    ]
    files: list[str] = []
    for name, args in sources:
        rc, out, err = _git(repo, args)
        if rc != 0:                            # 조용한 실패를 「성공한 0」 으로 취급하지 않는다.
            return undet(f"`git {' '.join(args)}` 실패(rc={rc}) — {_first_err(err)}")
        got = _lines(out)
        ev["sources"][name] = len(got)
        files += got
    ev["files"] = sorted(set(files))

    # ── ③b 이 트리엔 base 너머 커밋이 «없는데» 형제 워크트리엔 «있다».
    #     🔴 (D) 의 untracked 수집이 (C) 의 「빈 집합」 안전망을 무력화하는 잔여 케이스를 잡는다.
    #     작업과 무관한 untracked 노이즈(에이전트 산출물·메모 등)만으로 집합이 비지 않게 되면
    #     「판정 가능」이 확정되고, **다른 트리의 실제 작업에 대해 검증자가 «자신 있게» 스킵된다.**
    #     실측: 이 레포 메인 체크아웃에서 untracked 128개(.agents/) 때문에 design-review 가
    #     비어 있지 않은 skip 목록으로 나왔다 — 워크트리에 UI 파일이 있었다면 그대로 누락이다.
    #     ⚠️ 자기 트리는 committed==0 조건상 이미 base 의 조상이라 busy 에 들어오지 않는다
    #        (경로 비교가 어긋나도 위양성이 안 생기는 이유).
    if ev["sources"].get("committed", 0) == 0:
        busy = []
        for w in ev["worktrees"]:
            if not w.get("path") or w.get("path") == repo or not w.get("head"):
                continue
            rc, _, _ = _git(repo, ["merge-base", "--is-ancestor", w["head"], base])
            # rc 0=조상(작업 없음) · 1=조상 아님(작업 있음) · >1=에러. 에러를 「작업 없음」으로
            # 접으면 여기서 새 fail-open 이 난다 — 안전측(busy)으로 센다.
            if rc != 0:                       # base 의 조상이 아니다 = base 너머 작업이 있다
                busy.append(f"{w['path']} [{w.get('branch', '?')}]")
        if busy:
            return undet(
                "이 트리엔 base 너머 커밋이 없는데 형제 워크트리엔 있다 — 작업 중인 트리를 "
                f"가리키고 있지 않을 가능성이 높다: {', '.join(busy)}")

    # ── ④ 「변경 0개」도 의심 신호다. 변경이 0인데 이 스크립트를 부를 이유가 거의 없다.
    if not ev["files"]:
        return undet("변경 집합이 비어 있다 — 커밋범위·unstaged·staged·untracked 어디에도 파일이 없다. "
                     "base 가 틀렸거나, 변경이 다른 워크트리에 있을 가능성이 높다")
    return ev


def scope(files: list[str], undetermined: bool = False) -> dict:
    """파일 목록 → 디스패치할 검증자.

    `undetermined` 면 도메인 판정을 아예 하지 않고 **전량 디스패치**한다. 「모르겠으면 전부
    부른다」 — 불필요한 호출은 토큰이지만 누락은 검수 없는 머지다.
    """
    code_files = [f for f in files if not _match_any(f, NONCODE)]
    if undetermined:
        return {"changed": len(files), "code_changed": len(code_files),
                "dispatch": list(ALL_VERIFIERS), "skip": []}
    verifiers = []
    if code_files:
        verifiers.append("code-review")  # 코드 변경 있으면 구조 리뷰 필요
        if any(_match_any(f, DOMAINS["design-review"]) for f in code_files):
            verifiers.append("design-review")
        if any(_match_any(f, DOMAINS["security-qa"]) for f in code_files):
            verifiers.append("security-qa")
    skipped = [v for v in ALL_VERIFIERS if v not in verifiers]
    return {
        "changed": len(files),
        "code_changed": len(code_files),
        "dispatch": verifiers,
        "skip": skipped,
    }


def _print_evidence(ev: dict) -> None:
    """무엇을 비교했는지 — 결론만 있으면 사람이 오판을 알아챌 표면이 없다."""
    if ev.get("repo"):
        print(f"repo:     {ev['repo']}")
        print(f"HEAD:     {_short(ev.get('head_sha'))} ({ev.get('head_ref') or '(unknown)'})")
        print(f"base:     {ev.get('base_ref')} ({_short(ev.get('base_sha'))})")
    if ev.get("sources"):
        s = ev["sources"]
        parts = " · ".join(f"{k} {s[k]}" for k in ("committed", "unstaged", "staged", "untracked")
                           if k in s)
        print(f"스캔:     {parts} → 고유 {len(ev.get('files') or [])}개")
    # 워크트리가 둘 이상이면 **항상** 보여준다. 메인 체크아웃이 base 보다 앞서 있고 실작업은
    # 다른 워크트리에 있는 잔여 케이스는 집합이 비지 않아 판정 가능으로 떨어진다 — 유일한 감지 표면.
    wts = ev.get("worktrees") or []
    if len(wts) > 1:
        print(f"워크트리: {len(wts)}개 — 아래 중 «작업 중인» 트리를 --repo 로 넘겼는지 확인하라")
        for w in wts:
            mark = " ←현재" if w.get("path") == ev.get("repo") else ""
            print(f"  - {w.get('path')}  {_short(w.get('head'))}  [{w.get('branch', '?')}]{mark}")
    if ev.get("undetermined"):
        print(f"⚠️ 판정 불가: {ev.get('reason')}")
        print("   → 「변경 0개」가 아니다. 안전측으로 검증자를 전량 디스패치한다.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo")
    ap.add_argument("--base", default="main")
    ap.add_argument("--files", help="'-' 로 stdin(줄바꿈 목록), 또는 콤마목록")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.files == "-":
        files = [l.strip() for l in sys.stdin.read().splitlines() if l.strip()]
        ev = {"files": files, "undetermined": False, "reason": None}
    elif a.files:
        files = [x.strip() for x in a.files.split(",") if x.strip()]
        ev = {"files": files, "undetermined": False, "reason": None}
    elif a.repo:
        ev = collect(a.repo, a.base)
        files = ev["files"]
    else:
        ap.error("--repo 또는 --files 필요")
        return

    # --files 로 빈 목록이 와도 「변경 0개 → 전부 스킵」으로 착지시키지 않는다.
    if not files and not ev["undetermined"]:
        ev["undetermined"] = True
        ev["reason"] = "파일 목록이 비어 있다 — 검증 대상을 확인할 수 없다"

    r = scope(files, ev["undetermined"])
    r["undetermined"] = ev["undetermined"]
    r["reason"] = ev["reason"]
    for k in ("repo", "base_ref", "base_sha", "head_sha", "head_ref", "sources", "worktrees"):
        if k in ev:
            r[k] = ev[k]

    if a.json:
        print(json.dumps(r, ensure_ascii=False))
        return

    _print_evidence(ev)
    # ↓ 아래 3 줄은 호출 규약(스킬 문면이 `디스패치:`/`스킵:` 을 읽는다) — 포맷 유지.
    if ev["undetermined"]:
        print(f"변경 판정 불가 (사유: {ev['reason']})")
    else:
        print(f"변경 {r['changed']}개 (코드 {r['code_changed']}개)")
    print(f"디스패치: {', '.join(r['dispatch']) or '(없음 — 문서/설정만)'}")
    print(f"스킵:     {', '.join(r['skip']) or '(없음)'}")


if __name__ == "__main__":
    main()
