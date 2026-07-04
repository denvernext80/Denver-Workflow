# Changelog

## 2.2.1 — 2026-07-04

### 추가
- **graphify 안내를 서브에이전트 디스패치에 전파** — SessionStart 주입은 메인 세션에만 닿고 Task 로
  디스패치된 do-er 컨텍스트엔 안 닿는다. graphify 가 활성인 세션이면(`🕸 graphify` 블록 존재)
  디스패처가 디스패치 프롬프트에 "자료 탐색 시 `graphify explain`/`path` 를 `dw_search` 보다 우선"을
  graph.json 경로와 함께 relay 하도록, `dispatch-discipline` guidance 와 `dw-orchestrator` §3 에
  조건부 항목 추가. graphify 미활성 환경이면 조건이 거짓이라 무영향.

## 2.2.0 — 2026-07-04

### 추가
- **선택적 graphify 연동** — `graphify` CLI 와 `graphify-out/graph.json` 이 둘 다 감지되면
  SessionStart 시 세션 컨텍스트에 시멘틱 탐색 안내를 주입한다(자료를 찾을 때 substring `dw_search`
  대신 `graphify explain`/`path` 를 그래프 위에서 우선, 실패 시 `dw_search` 폴백). graphify 환경이
  없으면 완전히 무시(현행 동작 무변경) — 팀 공용 설치자 대다수에 영향 없음. 훅 시점 subprocess
  없이 파일 존재만 검사하며, 감지 실패는 조용히 무시해 digest 주입을 막지 않는다.

## 2.1.2 — 2026-07-04

### 수정
- **vault 기록 실패 근본 수정** — 매니페스트 개명(`.ssot-agents.json`→`.dw-agents.json`)으로
  추적 이탈한 1.x do-er 에이전트가 죽은 `ssot_write_*` 도구 grant 를 문 채 방치돼, 디스패치돼도
  `dw_write_*` 를 못 써 vault 기록이 조용히 실패하던 문제. 파일명은 멀쩡하고 내용만 stale 이라
  파일명접두 정리·vault전용 치환 양쪽 그물을 통과하던 사각을 메움:
  - `dw-migrate-vault` `--project` 모드 — 설치된 `.claude/agents/*.md` 의 죽은 식별자를 `dw_*` 로
    제자리 치환(skills 는 재설치가 재생성, agent-memory 는 사용자 데이터라 제외).
  - `/dw-install`·`/dw-setup` 레거시 감지를 파일명 접두(`ssot-`) → 내용 grep 으로 확장.

### 추가
- **디스패치 규율 강화** — `dw-orchestrator` §3 디스패치 프롬프트에 브랜치/워크트리 격리 강제 +
  마감 기록 지시, §4 do-er 학습 취합, §6 기록 규율 강화. 신규 `dispatch-discipline` guidance
  (digest:full — 절대경로·워크트리·대상레포 checks·마감 기록, 세션 유형 무관 항상 주입).

### 정합성
- `marketplace.json` metadata 설명의 구 제품명 `Denver Agent` → `Denver AI Workflow` 정정.

## 2.1.1 — 2026-07-04

### 수정
- venv 부트 스킵 버그 — 플러그인 설치가 stale `.venv/.stamp`(바이너리 없이)를 배포하면
  `make` 가 venv 를 이미 부트된 걸로 오판해 `install-project`/`dw-install` 이
  `.venv/bin/python: No such file` 로 실패하던 문제. `.stamp` 를 실제 바이너리 `$(VPY)` 에
  의존시켜 바이너리 부재 시 재생성하도록 교정.

## 2.1.0 — 2026-07-04

### 추가
- `/dw-setup` 레거시 정리 보강 — 로컬 훅·settings 배선 제거, 커스텀 vault 경로 감지,
  `dw-migrate-vault` 구 이름 리터럴 치환 스크립트.

### 수정
- `make` 가 `DW_VAULT_DIR` 의 리터럴 `$HOME` 을 못 풀어 vault 경로가 깨지던 버그 교정
  (`install-project`/`dw-setup` 실패 원인).

## 2.0.0 — 2026-07-03 (브레이킹)

팀 공용 전환 릴리스. **1.x 에서 올리는 경우 아래 마이그레이션 필수.**

### 변경
- **이름 전면 변경 `ssot-*` → `dw-*`**: 에이전트(dw-governed·dw-orchestrator·dw-ratifier),
  커맨드(/dw-build·/dw-install·/dw-ratify·/dw-review·/dw-scope), MCP 서버(dw-vault)·도구(dw_*),
  검사/다이제스트 파일(.claude/dw-checks.json·dw-session-digest.md).
- **플러그인·마켓플레이스 이름**: `denver-agent` → `denver-workflow`.
- **vault 규약 경로**: `~/denver-agent-vault` → `~/denver-workflow-vault`
  (env `DENVER_VAULT_DIR` → `DW_VAULT_DIR`).
- **신규 `/dw-setup`**: 초기 설정 도우미 — 외부 프로그램(Obsidian·superpowers·impeccable·gstack)
  설치 대행, vault 준비, 프로젝트(신규/기존/멀티레포) 설치까지 한 번에.
- SessionStart 가 설정 미완료를 감지해 `/dw-setup` 을 안내. 실행 중 미설치 의존은 자가치유.
- 특정 프로젝트 종속 잔재 전면 제거 — 완전 범용 플러그인.

### 1.x → 2.0 마이그레이션 (1회)
1. 구 플러그인 제거: `claude plugin uninstall denver-agent@denver-agent`
2. 신 설치: `claude plugin marketplace add https://github.com/denvernext80/Denver-Workflow`
   → `claude plugin install denver-workflow@denver-workflow`
3. 세션에서 `/dw-setup` 실행 — 구 산출물(`ssot-*`)과 구 vault 경로를 감지해 정리·이전을 안내한다.
