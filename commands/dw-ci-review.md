---
description: (선택) GitHub Actions Claude PR 리뷰어를 이 저장소에 설치 — 11단계 ⑥(PR+리뷰+CI) 자동화
argument-hint: "[프로젝트 절대경로 (생략 시 현재 폴더)]"
---
denver-workflow 11단계 중 **⑥단계(PR + 리뷰 + CI)** 를 GitHub Actions 에서 자동화하는 **Claude 기반 PR
리뷰어**를 대상 저장소에 설치한다. PR 이 열리거나 갱신되면 Claude 가 PR 브랜치를 실제로 받아 코드를
읽고 인라인 코멘트 + 최종 요약(합격/불합격 판정)을 남긴다. 판정이 불합격이면 그 검사(check)가
실패해, main 브랜치 보호 규칙에 넣으면 리뷰 통과 전 머지를 막을 수 있다. **선택 기능**이다 —
원하는 저장소에만 설치한다.

## 절차

**대상 경로**: `$ARGUMENTS` 가 있으면 그 절대경로, 없으면 `$(pwd)`(현재 폴더).

1. **미리보기**(쓰기 없음)로 무엇이 복사될지 사용자에게 보여준다:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw-ci-review.py" --project "<대상 경로>"
   ```
   - "이미 있음(보존)" 이 뜨면 기존 워크플로우가 있는 것 — 덮어쓰지 않는다. 사용자에게 알리고 끝낸다
     (갱신은 사용자가 직접 비교·수정).

2. **설치 확인 후 적용**(저장소에 파일을 만드는 동작이니 실행 전에 알린다):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw-ci-review.py" --project "<대상 경로>" --apply
   ```
   → `<대상 경로>/.github/workflows/dw-pr-review.yml` 생성(no-clobber).

3. **사람이 해야 할 바깥 작업 안내**(자동으로 하지 않는다 — 저장소 관리자 권한·비용이 걸린 동작).
   각 항목을 쉬운 말로 설명한다:

   - **① Claude 접속 토큰 등록** (리뷰어가 Claude 를 부를 때 쓰는 인증 — Claude Pro/Max 구독 토큰이라
     별도 API 요금 없이 구독으로 동작한다):
     ```bash
     claude setup-token        # 로컬에서 실행 → 토큰(sk-ant-oat…) 출력
     gh secret set CLAUDE_CODE_OAUTH_TOKEN --repo <owner/repo>   # 위 토큰을 붙여넣기
     ```
     여러 저장소를 함께 쓰면 **조직(org) 시크릿**으로 한 번만 등록해 여러 저장소가 공유하게 하는 편이
     편하다(`gh secret set CLAUDE_CODE_OAUTH_TOKEN --org <org> --repos <repo1,repo2,...>`). 사용자가
     `!claude setup-token` 을 이 세션에서 직접 실행하도록 안내해도 된다(토큰은 민감정보 — 로그·커밋 금지).

   - **② 워크플로우 파일 커밋·푸시** (GitHub Actions 는 커밋된 워크플로우만 실행한다):
     ```bash
     git add .github/workflows/dw-pr-review.yml && git commit -m "ci: denver-workflow PR 리뷰어 추가" && git push
     ```

   - **③ (선택) 머지 게이트로 승격** — main 브랜치 보호(branch protection)의 required status check 에
     `review` 를 추가하면, 리뷰 통과 전에는 머지가 막힌다. 저장소 Settings → Branches 에서 설정
     (관리자 권한 필요).

4. **마무리 보고**: 무엇이 설치됐고(파일 경로), 남은 사람 작업(①②③)이 무엇인지 표로 요약한다.

## 참고

- 리뷰 기준은 **특정 언어에 묶이지 않는다** — 리뷰어가 이 저장소에 커밋된 거버넌스(`.claude/skills`·
  `.claude/dw-checks.json`·`CLAUDE.md`)를 먼저 찾아 그 기준으로 리뷰하고, 없으면 일반 시니어
  엔지니어링 원칙으로 리뷰한다.
- 포크(fork)에서 온 PR 은 GitHub 이 시크릿을 주지 않아 리뷰가 안전하게 불합격 처리된다 — 내부 팀
  브랜치 PR 에서 정상 동작한다.
- **비용(러너 분) 줄이기 — self-hosted 러너(선택)**: public 레포는 러너 분이 무료지만 private 레포는
  과금된다. 부담되면 대상 레포에 **self-hosted 러너**를 등록하고 워크플로우의 `runs-on` 을
  `[self-hosted, <팀-러너-라벨>]` 로 바꾸면 러너 분 요금이 0 이 된다(기능은 전부 동일). 러너 등록:
  대상 레포 Settings → Actions → Runners → *New self-hosted runner*. macOS/Windows 러너면 `node`·`gh`
  CLI 가 PATH 에 있어야 리뷰 도구·verdict 스텝이 동작한다(GitHub-hosted 는 preinstall). **보안 —
  self-hosted 는 '외부 포크 PR 을 받지 않는 내부 신뢰 팀 레포'에서만**: `pull_request` 는 PR head 의
  워크플로우를 *머지 전* 실행하므로 write 권한자가 워크플로우를 고쳐 러너 호스트에서 임의 명령을
  돌릴 수 있다(브랜치보호는 '머지' 게이트라 이 실행 벡터를 못 막고, GitHub Free 플랜 private 레포엔
  설정도 불가). 러너는 배포 크레덴셜이 없는 **전용 저권한 계정**으로 돌리고, 러너 머신은 **상시
  가동**이어야 한다(꺼지면 체크가 큐에 걸려 머지 블록). 상세 주석은 워크플로우 템플릿의 `runs-on` 위.
  - **처리량**: self-hosted 러너 1개는 잡을 **순차** 실행한다(PR 의 여러 잡·동시 PR 이 큐에 쌓임).
    같은 라벨로 **러너 인스턴스를 여러 개** 등록하면 GitHub 이 잡을 분산해 병렬 처리된다.
  - **개인(User) 계정은 org 러너가 없어** 러너를 **레포별로** 등록해야 한다(레포마다 토큰 발급·등록).
  - 리뷰어 자체는 파일만 읽어 **아키텍처 무관**이지만, 같은 self-hosted 방식으로 **다른 CI 워크플로우**
    (테스트·빌드·배포)까지 옮길 땐 주의: (a) `services:`(서비스 컨테이너)·`container:` 는 **Linux 러너
    전용**(macOS 러너 불가) — Mac 이면 Linux VM/컨테이너 안에서 러너를 돌려야 한다, (b) 산출물
    아키텍처가 x86_64 인데 러너가 arm64 면 크로스컴파일/에뮬레이션이 필요하니 **타깃 arch 와 러너
    arch 를 맞춘다**, (c) 배포 등 **프로덕션 시크릿을 쓰는 잡은 untrusted PR 코드가 도는 러너와 분리**
    (전용 러너), (d) self-hosted 에선 ssh 가 ssh-agent 를 자동으로 안 집는 경우가 있어 배포 키는
    **파일+`ssh -i`(또는 ~/.ssh/config IdentityFile)** 로 명시하는 편이 안전하다.
- 템플릿 원본: `${CLAUDE_PLUGIN_ROOT}/assets/gh-workflows/dw-pr-review.yml`. 초기 설정 위저드
  `/dw-setup` 의 선택 단계에서도 이 설치를 제안한다.
