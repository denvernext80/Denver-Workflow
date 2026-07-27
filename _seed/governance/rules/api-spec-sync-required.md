---
type: rule
scope: engineering
status: stable
compiles-to: skill
enforced-by: code-review
title: API 표면을 바꿨으면 명세 갱신 + 변경 이력 없이 완료 금지
---
**호출하는 쪽이 관측할 수 있는 HTTP 표면**(엔드포인트 신설·삭제, 요청 파라미터·응답 shape·인증·
에러 코드 변경)을 바꾼 작업은 아래 둘이 모두 끝나야 완료다:

1. vault `project/reference/` 의 해당 **도메인 상세 노트 갱신 + 전체 인덱스의 엔드포인트 수 갱신**
2. `API 명세 — 변경 이력` 노트에 **항목 1건 이상 prepend** (날짜·유형·메서드+경로·요약·근거 PR/커밋)

절차는 api-spec-update 를 따른다.

**검증자(`code-review`)가 보는 것**: PR diff 에 라우트 정본(URL↔코드 연결 원본) 변경이나 응답 생성
코드 변경이 있는데 명세 갱신 근거(이력 항목·인덱스 카운트 변화)가 PR 본문·세션 기록에 없으면
**Major 로 지적한다.**

경계 — 이 규칙의 대상이 **아닌** 것: 내부 함수 시그니처 변경, 이름 바꾸기·구조 정리 같은 리팩터링,
응답이 그대로인 성능 개선, 아직 머지되지 않은 작업(명세는 머지된 현재 상태만 담는다 — 진행 중
인터페이스 협상은 vault `contracts/` 가 SSOT 다).

읽기 쪽 규율과 읽기 범위는 [[api-spec-first]] 에 있다. 후속 항목을 repo 파일 대신 vault 에 두는
같은 계열의 규칙은 [[no-project-backlog-files]] 다.
