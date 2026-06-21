---
type: guidance
scope: engineering
status: stable
compiles-to: skill
title: 잔여분만 작업한다
---
핸드오프·회신·크리틱 항목은 다른 PR/세션이 이미 마감했을 수 있다. 트래커 "0건"을 믿지 말고
각 항목의 file:line 이 `origin/main` 에 아직 유효한지 검증한 뒤 **잔여분만** 작업한다.
이미 고쳐진 이슈를 재구현해 중복 사고(중복 UI·중복 구현)가 실제로 났었다.
