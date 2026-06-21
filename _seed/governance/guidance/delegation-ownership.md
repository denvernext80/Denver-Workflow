---
type: guidance
scope: engineering
status: stable
compiles-to: skill
title: 위임해도 품질 책임은 본인
---
필요하면 리드가 되어 전문 에이전트에게 작업을 병렬 지시할 수 있다. 그러나 결과 검증과 품질
책임은 항상 본인에게 있다 — 에이전트 보고를 그대로 믿지 않는다. 리뷰어가 "계약 문서에
명문화 안 됨"이라 하면 직접 grep(머지 직전, detached/stale 체크아웃 금지)으로 재검증 후
판정한다. diff·테스트·스크린샷으로 직접 확인한다.
