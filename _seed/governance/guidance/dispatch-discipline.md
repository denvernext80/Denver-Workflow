---
type: guidance
scope: engineering
status: stable
compiles-to: skill
title: 서브에이전트 디스패치 규율 (절대경로·워크트리·검사·기록)
---
do-er(구현·진단·QA·배포·리뷰 서브에이전트)에게 `Task`/`Agent` 로 위임할 때, 디스패치 프롬프트에
**항상** 다음을 넣는다 — 세션 유형(오케스트레이터 경유든 메인 루프 직접이든)과 무관하다:

1. **대상 레포 절대경로.** `Agent` 디스패치(구 `Task`)는 re-root 불가라 do-er 는 이 경로 기준으로만 움직인다.
2. **브랜치 + 워크트리 격리 강제.** do-er 는 첫 in-repo 동작으로 **올바른 base**(레포 맵이 정한 그
   레포의 base 브랜치) 위에 격리 워크트리 + 작업 브랜치를 만들고, **모든 변경을 그 안에서만** 수행한다.
   base/main 직접 커밋·작업 **금지**. 어느 워크트리·브랜치·base 를 썼는지 회신에 명시하게 한다
   (`git worktree add` · `superpowers:using-git-worktrees`, 머지 규율은 [[pr-merge-discipline]]).
3. **대상 레포 검사.** "변경 후 그 레포의 `<repo>/.claude/dw-checks.json` 로 결정론 검사하라" — 완료
   게이트는 워크스페이스 union 이 아니라 **대상 레포 checks** 기준.
4. **마감 기록.** "비자명한 학습·재사용 절차·계약 변경을 vault 에 기록하고(`dw_write_memory`/
   `dw_write_procedure`/`dw_write_contract`, draft), 무엇을 기록했는지 회신하라." do-er 컨텍스트는
   회신 후 버려지므로, 기록하지 않으면 학습이 사라진다.

결과 검증·완료 게이트 책임은 **디스패처 본인**이다([[delegation-ownership]]). 교차레포·통합·계약
협상처럼 디스패처만 본 학습은 어느 do-er 에도 안 남으므로 디스패처가 직접 기록한다.
