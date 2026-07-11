---
type: agent
id: 
title: {{title}}
---
이 에이전트가 검사하는 위반 항목을 적는다(enforced-by 의 대상이 된다).
단독 게이트가 아님을 명시 — 결정론적 도구와 사람 리뷰를 병행한다.

주의: frontmatter 에 tools:/model: 을 적어도 컴파일러는 emit 하지 않는다(name/description 만).
설치된 에이전트는 세션 도구 전체를 상속한다(MCP 포함) — tools: 는 넣지 말 것.
