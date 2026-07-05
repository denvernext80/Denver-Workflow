---
type: rule
scope: engineering
status: stable
compiles-to: skill
enforced-by: code-review
title: 백로그·후속 항목은 vault 로 — 프로젝트 repo 에 Backlog 파일 금지
---
후속 작업·백로그(이번 범위 밖이라 나중에 다룰 항목)를 **프로젝트 repo 안에 파일로 만들지 마라** —
`BACKLOG.md`·`TODO.md`·`FOLLOWUP.md`·`backlog/*.md`(전문용어: 프로젝트 루트/하위에 흩뿌리는 할일 목록
파일) 등. 이런 파일은 worktree 청소·브랜치 삭제 시 휘발하고, vault SSOT 밖이라 팀·다음 세션이 못 본다.

**대신 vault 로 기록한다**: `dw_write_backlog(scope, title, item, context)` — vault `project/backlog/` 에
LIVE(status:stable)로 남아 `dw_search`·`dw_list(note_type=backlog)` 로 즉시 조회된다. item=무엇을
해야 하나, context=어디서 나왔나·왜(file:line·커밋).

경계: README·CHANGELOG 등 코드-인접 관례 문서, 그리고 코드 안의 인라인 `// TODO:` 주석은 대상이
아니다(이건 코드의 일부). 금지 대상은 **후속작업 목록을 담은 별도 마크다운 파일**이다. durable
분석/스펙/계획 문서 전반의 vault-우선 규율은 [[artifact-locations]] 를 따른다.
