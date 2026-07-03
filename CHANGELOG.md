# Changelog

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
