---
type: guidance
scope: engineering
status: stable
compiles-to: skill
digest: full
title: TDD 철칙
---
프로덕션 코드 전에 실패 테스트를 먼저 쓴다 — RED 의 **실패 사유가 의도와 일치하는지**까지 확인한
뒤 최소 구현으로 GREEN. 버그 수정은 반드시 재현 테스트부터(cold 재현 후 수정, 추측 fix 금지).
기존 테스트 하니스(fake repo·_pump·body seam 패턴)를 재사용해 비용을 낮춘다. 스펙 변경으로 기존
가드를 깨면 삭제가 아니라 "스펙 변경" 주석과 함께 신규 동작 가드로 갱신한다. 화면/모델 개편 시
관련 테스트의 fake·단언 동기화(테스트 부패)를 함께 확인한다.
