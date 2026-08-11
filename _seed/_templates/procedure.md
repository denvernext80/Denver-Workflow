---
type: procedure
status: draft
scope: 
compiles-to: skill
title: {{title}}
---
재사용 가능한 절차(playbook). "이 작업을 다음에 또 어떻게 하나"를 단계로 적는다.
강제 규칙(rule)이 아니라 how-to 다 — 따르면 빠르고 안전하다.

1. (단계)
2. (단계)
3. (검증)

**언제 쓰나:** 이 절차가 적용되는 상황.
**주의:** 흔한 함정·예외.

**기존 절차를 정정·반증하는 노트라면** frontmatter 에 `supersedes: <대상 절차의 파일명(stem)
또는 vault 상대경로 또는 title>` 을 넣는다. 컴파일러가 피-정정 절차의 전문(references/*.md)
머리와 스킬 인덱스 줄에 정정 배너를 박아, 원본만 펼쳐 읽는 에이전트도 정정을 보게 된다
(원본은 지우지 않는다 — 정정이 일부 단계만 반증하면 나머지 유효분이 소실되므로).
대상은 컴파일되는 절차(type:procedure·status:stable)여야 하고, 아니면 컴파일이 실패한다.

에이전트가 draft 로 기록하고, 사람이 검토 후 status:stable 로 올리면 스킬로 컴파일된다.
