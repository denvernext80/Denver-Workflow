# Changelog

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
