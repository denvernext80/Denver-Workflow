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

## 판단형 검증자는 도메인이 겹칠 때만 부른다 (relevance-gate)

`code-review`·`design-review`·`security-qa` 는 무거운 서브에이전트다(diff 통째 추론 + 규칙 로드).
**바뀐 파일이 그 검증자 도메인에 하나도 없으면 부르지 마라** — 리뷰할 게 0인 검증자를 부르는 건
토큰만 태우고 아무 것도 못 잡는다. 판단으로 고르지 말고 **결정론 도구로 산출**한다:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw-verifier-scope.py" --repo <레포 절대경로> --base <base 브랜치>
# 또는 파일 목록 직접:  --files "lib/a.dart,src/Auth.php" [--json]
```

`dispatch` 로 나온 검증자만 부르고 `skip` 은 부르지 않는다. 판정 규칙: 문서·설정만 바뀌면
**전부 스킵**, 코드가 바뀌면 `code-review` 는 기본 포함(구조 리뷰는 grep 이 대체 못 한다),
`design-review` 는 UI 표면(`*.dart`·`home-frontend/*`·`templates/*`·`*.css` …), `security-qa` 는
보안-민감 표면(`*.php`·`migrations/*`·`*auth*`·`*token*`·`*sql*` …)이 있을 때만.

**이건 규칙 완화가 아니다** — 결정론 검사(`dw-checks.json`)와 완료 게이트는 그대로다. 스킵은
"그 검증자가 볼 파일이 0" 일 때만 일어난다. 도메인 글롭이 그 레포와 안 맞으면(예: UI 가 `.vue`
인 레포) 도구 판정보다 **실측이 우선**이다 — 더 부르는 쪽으로 어긋내고, 어긋난 이유를 남겨라.
