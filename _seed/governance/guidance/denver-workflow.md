---
type: guidance
scope: engineering
status: stable
compiles-to: skill
digest: full
title: denver-workflow — 신규 기능 풀사이클 11단계(멀티레포)
---
신규 기능은 **요구사항 → 배포** 11단계 풀사이클로 진행한다(typo·1줄 fix·docs-only 단발 수정은
해당 레포 do-er git flow 직행). 이 워크스페이스가 멀티레포면 원본의 "FE/BE worktree 2개"가 아니라
**레포별 do-er 디스패치**로 분기한다 — 어느 레포에 어느 do-er 를 붙이는지는 **세션 digest 의
"## 레포 맵 (라우팅)"** 을 따른다(레포 맵이 없으면 `/denver-workflow` 0단계 부트스트랩이 먼저 수집한다).

단계 골격: ① 요구사항(brainstorming+advisor) → ② 기획(writing-plans) → ③ UI/UX(impeccable·design,
프론트/앱 한정) → ④ 분기+worktree → 🔒 **API 계약 GATE**(vault contracts/ shape 확정 전 구현 진입
금지) → ⑤ 구현(순차 디스패치·회귀가드 RED 먼저) → ⑥ PR+리뷰+레포별 CI → ⑦ 기획↔구현 비교(수동
체크리스트) → ⑦.5 디자인 QA → ⑧ 기능 QA → ⑧.5 회귀 스위트 → ⑨ 레포별 머지·배포(게이트 동의).

규율 정본은 재정의하지 않고 참조한다: gitflow·`--admin`금지는 [[pr-merge-discipline]], worktree 격리(격리된
작업공간에서 do-er 가 자기 레포에서 수행), 회귀는 [[tdd-iron-law]]·[[regression-by-set-diff]], 모든 단계 전제는
[[karpathy-guidelines]]. 디스패치·게이트·계약 흐름은 `ssot-orchestrator` roster.
교차 작업은 **순차**(계약 먼저 → 공급측 → 소비측), 완료 게이트는 **대상 레포 checks**.
막히면 즉시 **advisor 에스컬레이션**. 상세 단계·도구·외부 플러그인 설치 안내는 `/denver-workflow`.
