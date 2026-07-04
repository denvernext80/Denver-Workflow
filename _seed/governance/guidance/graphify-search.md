---
type: guidance
scope: engineering
status: stable
compiles-to: skill
digest: full
title: 지식 탐색은 graphify 그래프 우선 (활성 시)
---
자료·지식을 찾을 때 **graphify MCP 도구가 세션에 노출돼 있으면 substring 매칭인 `dw_search` 보다
먼저** 쓴다. graphify 는 vault(SSOT 팀 지식)를 그래프로 ingest 한 것이라, 관계·경로 기반 탐색이
단어 일치보다 정확하고 넓다:
- 개념/노드 이해: `query_graph`·`get_node`·`get_neighbors`
- 두 개념의 연결·영향 경로: `shortest_path`·`get_pr_impact`
- 구조 파악: `graph_stats`·`god_nodes`·`get_community`

절차: ① graphify 도구로 관련 노드·이웃·경로를 잡고 → ② 구체 노트 전문은 `dw_read`(vault MCP)로 편다.
graphify 도구가 세션에 없으면(미등록 환경) `dw_search` 로 폴백한다 — 이 규율은 도구가 있을 때만 발동한다.

디스패처는 do-er 에게도 이 우선순위를 relay 한다(디스패치 규율은 [[dispatch-discipline]]). do-er 가
graphify 도구를 grant 받았으면 동일하게 우선 사용한다.
