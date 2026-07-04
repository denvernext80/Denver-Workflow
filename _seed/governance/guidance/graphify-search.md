---
type: guidance
scope: engineering
status: stable
compiles-to: skill
digest: full
title: 지식 탐색은 graphify 그래프 우선 (활성 시)
---
정본은 graphify 유무와 무관하다: 규칙 강제는 **컴파일 스킬 + 세션 다이제스트**, 계약·스펙·메모리 원문은
**`dw_read`/`dw_search`**(vault MCP). graphify 는 **발견·탐색 보조**이지 정본이 아니다.

**graphify 설치 시**(MCP 도구가 세션에 있을 때만): 자료·지식 탐색을 substring `dw_search` 보다 graphify
그래프로 먼저 한다 —
- **지식**(팀 노트·계약·스펙): vault 를 ingest 한 **기본 그래프**(project_path 없이) — `query_graph`·
  `get_neighbors`·`shortest_path`.
- **코드**(특정 레포 내부): 그 레포의 그래프를 **`project_path=<repo 절대경로>`** 인자로 조회.
- 절차: ① graphify 로 노드·이웃·경로를 잡고 → ② 원문은 `dw_read` 로 편다.

**카페앗**: 코드 그래프는 AST-전용(LLM 미개입·결정론적). **INFERRED 엣지는 추정이라 근거로 인용 금지**
(실재 근거는 원문 `dw_read`). 여러 레포를 합친 global 통합 그래프는 심볼 충돌 아티팩트라 신뢰하지 않는다.
graphify 도구가 세션에 없으면(미설치) 이 전체가 무시되고 `dw_search` 로 동작한다.

디스패처는 do-er 에게도 이 우선순위를 relay 한다([[dispatch-discipline]]).
