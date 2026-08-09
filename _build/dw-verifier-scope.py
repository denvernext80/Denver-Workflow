#!/usr/bin/env python3
"""dw-verifier-scope — 검증자 디스패치 relevance-gate (결정론, 토큰 절감).

문제: code-review/security-qa/design-review 검증자가 관련 없는 변경에도 판단으로 디스패치돼
작업당 무거운 서브에이전트 토큰을 태운다. 이 스크립트는 **바뀐 파일**을 도메인 글롭과 대조해
**실제로 필요한 검증자만** 결정론적으로 반환한다. 어떤 규칙도 약화하지 않는다 — 리뷰할 게
0인 검증자를 안 부를 뿐이다.

usage:
    python dw-verifier-scope.py --repo /abs/repo --base <base-branch>   # git diff 로 변경파일 산출
    python dw-verifier-scope.py --files - <<< "src/a.php\nlib/x.dart"    # 파일목록 직접
    (--json 으로 기계가독)

정책:
  - 문서/설정만 변경(*.md, docs/**, *.lock, 이미지 등) → 검증자 0(전부 스킵).
  - 코드 변경 있으면 code-review 는 기본 포함(구조 리뷰는 grep 이 대체 못 함).
  - design-review: UI/디자인 파일(*.dart, home-frontend/**, templates/**, *.css …) 있을 때만.
  - security-qa: 백엔드·인증·네트워크·토큰 파일 있을 때만.
도메인 맵은 아래 DOMAINS 로 조절(레포 무관 글롭; 레포별로 다르면 --map 로 JSON 주입).
표준 라이브러리만.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys

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


def _match_any(path: str, globs) -> bool:
    p = path.replace("\\", "/")
    return any(fnmatch.fnmatch(p, g) for g in globs)


def changed_files(repo: str, base: str) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "-C", repo, "diff", "--name-only", f"{base}...HEAD"],
            capture_output=True, text=True, timeout=20,
        )
        files = [l.strip() for l in out.stdout.splitlines() if l.strip()]
        # 미커밋 변경도 포함(작업 중 게이트)
        out2 = subprocess.run(
            ["git", "-C", repo, "diff", "--name-only"],
            capture_output=True, text=True, timeout=20,
        )
        files += [l.strip() for l in out2.stdout.splitlines() if l.strip()]
        return sorted(set(files))
    except Exception:
        return []


def scope(files: list[str]) -> dict:
    code_files = [f for f in files if not _match_any(f, NONCODE)]
    verifiers = []
    if code_files:
        verifiers.append("code-review")  # 코드 변경 있으면 구조 리뷰 필요
        if any(_match_any(f, DOMAINS["design-review"]) for f in code_files):
            verifiers.append("design-review")
        if any(_match_any(f, DOMAINS["security-qa"]) for f in code_files):
            verifiers.append("security-qa")
    skipped = [v for v in ("code-review", "design-review", "security-qa") if v not in verifiers]
    return {
        "changed": len(files),
        "code_changed": len(code_files),
        "dispatch": verifiers,
        "skip": skipped,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo")
    ap.add_argument("--base", default="main")
    ap.add_argument("--files", help="'-' 로 stdin(줄바꿈 목록), 또는 콤마목록")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.files == "-":
        files = [l.strip() for l in sys.stdin.read().splitlines() if l.strip()]
    elif a.files:
        files = [x.strip() for x in a.files.split(",") if x.strip()]
    elif a.repo:
        files = changed_files(a.repo, a.base)
    else:
        ap.error("--repo 또는 --files 필요")
        return

    r = scope(files)
    if a.json:
        print(json.dumps(r, ensure_ascii=False))
        return
    print(f"변경 {r['changed']}개 (코드 {r['code_changed']}개)")
    print(f"디스패치: {', '.join(r['dispatch']) or '(없음 — 문서/설정만)'}")
    print(f"스킵:     {', '.join(r['skip'])}")


if __name__ == "__main__":
    main()
