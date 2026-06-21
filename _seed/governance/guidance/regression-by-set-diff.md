---
type: guidance
scope: engineering
status: stable
compiles-to: skill
title: 회귀는 카운트가 아니라 SET diff로 증명
---
회귀 판정은 테스트 통과 카운트가 아니라 **실패 SET diff** 로 한다 — 워크트리(또는 변경본)의 실패
집합을 클린 `origin/main` 의 실패 집합과 비교(`comm -13`)해 사전실패와 신규 회귀를 분리하고
회귀 0 을 증명한다. 전체 스위트를 돌린다. 주의: compound command `cd A && cmd1; cmd2` 에서
cmd2 는 A 에서 돌지 않으니 디렉토리별로 분리 실행한다.
