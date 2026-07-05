#!/usr/bin/env python3
"""dw-ci-review — denver-workflow 11단계 ⑥(PR 리뷰)용 GitHub Actions 워크플로우를 프로젝트에 설치.

Claude 기반 PR 리뷰어(anthropics/claude-code-action) 워크플로우를 대상 저장소의
`.github/workflows/dw-pr-review.yml` 로 복사한다. 이 파일은 저장소가 소유하는 **커밋 코드**라
`.claude/` 재생성 산출물(install-project)이나 vault seed 대상이 아니다 — 그래서 별도 no-clobber
복사로 다룬다(기존 파일은 절대 덮어쓰지 않음). 사용처: /dw-ci-review 커맨드, /dw-setup 옵인 단계.

시크릿 등록·브랜치 보호는 저장소 관리자 영역(바깥 동작)이라 이 스크립트가 하지 않는다 —
커맨드가 사람에게 안내한다.

사용:
  python3 dw-ci-review.py --project <레포>            # dry-run(미리보기, 쓰기 없음)
  python3 dw-ci-review.py --project <레포> --apply    # 실제 복사(no-clobber)
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

WORKFLOW_NAME = "dw-pr-review.yml"
# 플러그인 자산: 이 스크립트(_build/) 기준 상위의 assets/gh-workflows/dw-pr-review.yml
TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "gh-workflows" / WORKFLOW_NAME


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, help="대상 저장소 절대경로")
    ap.add_argument("--apply", action="store_true", help="실제 복사(기본은 미리보기)")
    args = ap.parse_args()

    project = Path(args.project).expanduser().resolve()
    if not project.is_dir():
        sys.stderr.write(f"(오류) 프로젝트 폴더 없음: {project}\n")
        return 1
    if not (project / ".git").exists():
        sys.stderr.write(f"(경고) git 저장소가 아닌 것 같습니다: {project} — GH Actions 는 git 저장소에만 동작합니다.\n")
    if not TEMPLATE.is_file():
        sys.stderr.write(f"(오류) 템플릿 없음: {TEMPLATE}\n")
        return 1

    dest_dir = project / ".github" / "workflows"
    dest = dest_dir / WORKFLOW_NAME

    if dest.exists():
        print(f"  이미 있음(보존): {dest}")
        print("  → 기존 워크플로우를 덮어쓰지 않습니다. 갱신하려면 파일을 직접 비교·수정하세요.")
        print(f"     템플릿 원본: {TEMPLATE}")
        return 0

    if not args.apply:
        print("── 미리보기(쓰기 없음) ──")
        print(f"  복사 예정: {TEMPLATE}")
        print(f"        →   {dest}")
        print("  적용하려면 --apply 를 붙여 다시 실행하세요.")
        print("  적용 후 필요한 사람 작업(커맨드가 안내):")
        print("    1) Claude Pro/Max 토큰 생성(claude setup-token) → 시크릿 CLAUDE_CODE_OAUTH_TOKEN 등록")
        print("    2) (선택) main 브랜치 보호 required check 에 'review' 추가")
        return 0

    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(TEMPLATE, dest)
    print(f"✓ 설치됨: {dest}")
    print("  다음(사람 작업 — 바깥 동작이라 자동으로 하지 않음):")
    print("    1) 로컬에서 토큰 생성:  claude setup-token   (Claude Pro/Max 구독 토큰)")
    print("       저장소 시크릿 등록:  gh secret set CLAUDE_CODE_OAUTH_TOKEN --repo <owner/repo>")
    print("       (멀티레포면 조직 시크릿으로 한 번만 등록해 공유 가능)")
    print("    2) 커밋·푸시:  git add .github/workflows/dw-pr-review.yml && git commit && git push")
    print("    3) (선택) main 브랜치 보호의 required status check 에 'review' job 추가 → 리뷰 통과 전 머지 차단")
    return 0


if __name__ == "__main__":
    sys.exit(main())
