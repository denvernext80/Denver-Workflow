---
type: guidance
scope: engineering
status: stable
compiles-to: skill
digest: full
title: 산출물이 사는 곳 — durable 한 건 전부 vault SSOT
---
**vault 가 모든 durable 프로젝트 지식의 단일 SSOT 다**: `rules`(법) · `guidance`(작업 규율) ·
`contracts`(백엔드↔앱 인터페이스) · `specs`(계획·스펙·설계) · `decisions`(ADR/왜) · `memory`(학습).

**스펙·계획·설계는 vault `specs/` 에 둔다** — `ssot_write_spec(scope, title, body, kind)` 로 작성한다
(kind=plan|spec|design, 항상 draft). 조회는 `ssot_search`/`ssot_read`.
repo/worktree(`docs/superpowers/`)에만 두면 **worktree 청소·브랜치 삭제 시 휘발**한다 — durable 한
스펙은 반드시 vault 에 보존한다. (기존 repo 스펙은 vault 로 이전 완료, repo 사본은 레거시.)

**작업 흐름**: 활성 구현 중엔 worktree 에서 초안을 다듬되, **정착분(또는 끝난 스펙)은 vault `specs/`
에 올려** worktree 청소돼도 살아남게 한다. 미래 세션은 `ssot_search` 로 전체 스펙을 찾는다.

**판단 기준**: 두고두고 참조되거나 worktree/브랜치에 묶여 휘발 위험이 있으면 → **vault**.
순수 일회성 스크래치(곧 버릴 메모)는 굳이 올리지 않아도 된다.

**스펙 본문은 repo 코드 경로를 링크로 남긴다**(스펙↔코드 연결 유지, 중복 복제는 금지).
