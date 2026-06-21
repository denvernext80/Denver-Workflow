# SSOT vault → .claude/skills 빌드
#
# pyyaml 는 이 컴파일러의 유일한 외부 의존성이다. PEP 668(externally-managed)
# 환경을 깨지 않도록 전역이 아닌 프로젝트-로컬 .venv 에 설치한다.

PY      := python3
VENV    := .venv
VPY     := $(VENV)/bin/python
# 도구 루트 = 이 워크스페이스(.venv·_build·hooks·.claude 산출물 잔류).
TOOLS_ROOT := $(shell pwd)

# 설치 대상 프로젝트 경로 + 각 프로젝트가 받을 scope 묶음.
# vault=소스(Obsidian-Vault, 외부화), 각 프로젝트의 .claude/skills=빌드 산출물(직접 편집 금지).
REPO_ROOT      := /Users/myeongseokyang/Desktop/Repository
# vault 콘텐츠 위치(balipick-workspace 에서 분리). DENVER_VAULT_DIR 우선, 기본 ~/denver-agent-vault.
# 도구(.venv·_build·hooks)는 이 워크스페이스에 잔류 — vault 만 외부화.
VAULT_DIR      := $(if $(DENVER_VAULT_DIR),$(DENVER_VAULT_DIR),$(HOME)/denver-agent-vault)
# 컴파일러는 상대 --out 을 vault 기준으로 해석하므로(out=vault/out), 워크스페이스 산출물엔 절대경로 사용.
COMPILE := $(VPY) _build/ssot-compile.py --vault "$(VAULT_DIR)" --out "$(TOOLS_ROOT)/.claude/skills"

# 플러그인이 들고 있는 제네릭 vault seed(콜드스타트 스캐폴드). 설치 시 빈 vault 로 복사.
# 제네릭화 = '선별'(byte-동일 유지 가능한 프로젝트 무관 노트만) — 손편집 금지(update-seed 가 되돌림).
# 사적 데이터(project/*) 는 seed 에 절대 없음.
SEED          := _seed
SEED_GUIDANCE := karpathy-guidelines tdd-iron-law regression-by-set-diff residual-only delegation-ownership pr-merge-discipline artifact-locations
SEED_AGENTS   := code-review security-qa ssot-governed ssot-ratifier
TRAVEL_ONE     := $(REPO_ROOT)/Travel-One
BALIPICK       := $(REPO_ROOT)/Balipick-App
BALIPICK_CHAT  := $(REPO_ROOT)/balipick-chat
# engineering = 개발 에이전트의 공유 작업 규율(전 프로젝트 공통 설치)
TRAVEL_SCOPES  := backend-php,auth,api-contract,content-policy,engineering
BALIPICK_SCOPES:= mobile-flutter,design-system,auth,api-contract,engineering
# balipick-chat = Rust 채팅 마이크로서비스. Rust 전용 scope 없음 → 공유 규율+JWT 계약·인증.
BALIPICK_CHAT_SCOPES := engineering,api-contract,auth

.PHONY: build dry-run clean distclean help install install-travel-one install-balipick install-balipick-chat install-orchestrator doctor register-mcp review ratify

$(VENV)/.stamp:
	$(PY) -m venv $(VENV)
	$(VPY) -m pip install --quiet --upgrade pip
	$(VPY) -m pip install --quiet pyyaml mcp
	@touch $(VENV)/.stamp

build: $(VENV)/.stamp        ## vault 를 컴파일해 .claude/skills 생성
	$(COMPILE)

dry-run: $(VENV)/.stamp      ## 쓰기 없이 검증/요약(CI 용, 경고도 에러)
	$(COMPILE) --dry-run --strict

.PHONY: scaffold-vault update-seed seed-check
scaffold-vault: $(VENV)/.stamp  ## 빈/없는 vault 에 제네릭 seed(축B 거버넌스+폴더 구조+VAULT-STRUCTURE) 복사 (no-clobber)
	@echo "→ vault 스캐폴드: $(VAULT_DIR)  (기존 파일 보존 — no-clobber)"
	@mkdir -p "$(VAULT_DIR)"
	@cp -Rn $(SEED)/. "$(VAULT_DIR)/" 2>/dev/null || true
	@echo "✓ seed 복사 완료. 구조: governance/(축B 운영체계) + project/(축A, 빈 골격) + VAULT-STRUCTURE.md"
	@echo "  다음: Obsidian 으로 \"$(VAULT_DIR)\" 폴더 열기(Open folder as vault) → make build"

update-seed: $(VENV)/.stamp  ## live vault 의 제네릭 축-B 노트를 _seed 로 갱신(화이트리스트 verbatim; 사적 project 제외)
	@echo "→ _seed 갱신: live $(VAULT_DIR) → $(SEED) (화이트리스트만, project 사적 데이터 미포함)"
	@for g in $(SEED_GUIDANCE); do cp "$(VAULT_DIR)/governance/guidance/$$g.md" $(SEED)/governance/guidance/; done
	@for a in $(SEED_AGENTS); do cp "$(VAULT_DIR)/governance/agents/$$a.md" $(SEED)/governance/agents/; done
	@cp "$(VAULT_DIR)/governance/_skills/engineering.md" $(SEED)/governance/_skills/
	@cp "$(VAULT_DIR)"/_templates/*.md $(SEED)/_templates/ 2>/dev/null || true
	@$(MAKE) -s seed-check

seed-check: $(VENV)/.stamp  ## seed 자기충족 검증(strict 컴파일 + 사적 데이터 0)
	@$(VPY) _build/ssot-compile.py --vault $(SEED) --out /tmp/seed-skills --dry-run --strict >/dev/null 2>&1 && echo "  [ok] seed strict 컴파일(자기충족·위키링크 폐쇄)" || { echo "  [!!] seed 컴파일 실패 -> .venv/bin/python _build/ssot-compile.py --vault $(SEED) --dry-run --strict"; exit 1; }
	@n=$$(find $(SEED)/project -type f ! -name .gitkeep | wc -l | tr -d ' '); [ "$$n" = "0" ] && echo "  [ok] seed 에 사적 project 데이터 0" || { echo "  [!!] seed/project 에 사적 파일 $$n 개 — 제거 필요"; exit 1; }

install: install-travel-one install-balipick install-balipick-chat  ## 모든 대상 프로젝트에 설치(스킬+검증자)

# 한 프로젝트에 스킬 + 결정론적 검사 매니페스트 + 린터 훅까지 설치.
# 인자: $(1)=프로젝트경로 $(2)=scope목록
# MCP 서버(절대경로 — CC/클라이언트가 다른 cwd 에서 spawn 하므로). 도구는 워크스페이스.
MCP_PY     := $(TOOLS_ROOT)/$(VENV)/bin/python
MCP_SERVER := $(TOOLS_ROOT)/_build/ssot-mcp-server.py
MCP_NAME   := ssot-vault

define INSTALL_PROJECT
	$(VPY) _build/ssot-compile.py --vault "$(VAULT_DIR)" --out "$(1)/.claude/skills" \
		--scopes $(2) --checks-out "$(1)/.claude/ssot-checks.json" \
		--agents-out "$(1)/.claude/agents" \
		--digest-out "$(1)/.claude/ssot-session-digest.md"
	$(VPY) _build/wire-hook.py "$(1)" "$(VAULT_DIR)" --config-only
endef

# 권한 확대는 민감한 자기수정이라 install 과 분리 — 사용자가 명시적으로 실행.
.PHONY: plugin-scope-user plugin-scope-project plugin-scope-off
plugin-scope-user:           ## 플러그인을 사용자 전역 활성(모든 프로젝트). CLAUDE_CONFIG_DIR 계정 기준.
	$(VPY) _build/ssot-plugin-scope.py user
plugin-scope-project:        ## 플러그인을 이 프로젝트만 활성. 사용: make plugin-scope-project P=/path/to/project
	$(VPY) _build/ssot-plugin-scope.py project "$(P)"
plugin-scope-off:            ## 플러그인 비활성(계정 전역, P 주면 프로젝트도)
	$(VPY) _build/ssot-plugin-scope.py off "$(P)"

.PHONY: plugin-update
plugin-update:               ## 플러그인 한 방 업데이트(클론 pull + 버전기반 update). ⚠️ plugin.json version 을 먼저 올려야 갱신됨.
	@echo "→ 마켓플레이스 최신화 + plugin update (CC 는 version 기반 — install 은 already-installed no-op)"
	@echo "  ⚠️ plugin.json/marketplace.json version 을 올리지 않으면 'already latest' 로 갱신 안 됨."
	claude plugin marketplace update denver-agent
	claude plugin update denver-agent@denver-agent
	@echo "✓ 새 세션부터 반영. (스케줄로 자동화하려면 cron/launchd 에 이 타깃 등록)"

.PHONY: clean-hooks
clean-hooks: $(VENV)/.stamp  ## 프로젝트 settings.json 의 SSOT 훅 wire 제거(플러그인이 전역 제공 → 중복 해소)
	$(VPY) _build/wire-hook.py "$(TRAVEL_ONE)" --remove
	$(VPY) _build/wire-hook.py "$(BALIPICK)" --remove
	$(VPY) _build/wire-hook.py "$(BALIPICK_CHAT)" --remove

.PHONY: grant-access
grant-access: $(VENV)/.stamp  ## (선택) 양 프로젝트에 vault 읽기/쓰기 권한 사전 승인
	$(VPY) _build/grant-vault-access.py "$(TRAVEL_ONE)" "$(VAULT_DIR)"
	$(VPY) _build/grant-vault-access.py "$(BALIPICK)" "$(VAULT_DIR)"
	$(VPY) _build/grant-vault-access.py "$(BALIPICK_CHAT)" "$(VAULT_DIR)"

install-travel-one: $(VENV)/.stamp  ## Travel-One 에 스킬+검증자 설치 (계약은 vault SSOT, 미러 안 함)
	$(call INSTALL_PROJECT,$(TRAVEL_ONE),$(TRAVEL_SCOPES))

install-balipick: $(VENV)/.stamp    ## Balipick-App 에 스킬+검증자 설치 (계약은 vault SSOT, 미러 안 함)
	$(call INSTALL_PROJECT,$(BALIPICK),$(BALIPICK_SCOPES))

install-balipick-chat: $(VENV)/.stamp  ## balipick-chat(Rust 채팅 서비스)에 스킬·다이제스트 설치
	$(call INSTALL_PROJECT,$(BALIPICK_CHAT),$(BALIPICK_CHAT_SCOPES))

# 오케스트레이터 — 이 워크스페이스(repo 자체)의 .claude 에 union 전 scope(--scopes 생략) +
# enforced-by 검증자 emit + roster do-er/orchestrator verbatim cp(tools 보존). 멀티레포 단일 세션용.
install-orchestrator: $(VENV)/.stamp  ## 이 워크스페이스 .claude 에 union 스킬+검증자+roster do-er/orchestrator 설치
	$(VPY) _build/ssot-compile.py --vault "$(VAULT_DIR)" --out "$(TOOLS_ROOT)/.claude/skills" \
		--checks-out "$(TOOLS_ROOT)/.claude/ssot-checks.json" \
		--agents-out "$(TOOLS_ROOT)/.claude/agents" \
		--digest-out "$(TOOLS_ROOT)/.claude/ssot-session-digest.md"
	@echo "→ roster do-er/orchestrator verbatim cp (tools 보존, 컴파일러 무관)"
	cp roster/backend-lead.md roster/senior-mobile-engineer.md roster/rust-chat-engineer.md .claude/agents/
	@echo "✓ 오케스트레이터 설치 완료 (.claude/{skills,agents,ssot-checks.json,ssot-session-digest.md})"

doctor: $(VENV)/.stamp       ## 콜드스타트 헬스체크(venv·의존성·MCP 서버·설치 상태)
	@echo "== SSOT 헬스체크 =="
	@$(VPY) -c "import yaml, mcp" 2>/dev/null && echo "  [ok] venv deps: pyyaml + mcp" || echo "  [!!] venv 의존성 누락 -> make build"
	@$(VPY) _build/ssot-compile.py --vault "$(VAULT_DIR)" --out .claude/skills --dry-run --strict >/dev/null 2>&1 && echo "  [ok] 컴파일러 strict 통과" || echo "  [!!] 컴파일 실패 -> make dry-run"
	@test -f "$(MCP_SERVER)" && echo "  [ok] MCP 서버 존재" || echo "  [!!] MCP 서버 없음"
	@test -d "$(VAULT_DIR)/governance" && test -d "$(VAULT_DIR)/project" && echo "  [ok] vault 구조(축 A/B): $(VAULT_DIR)" || echo "  [..] vault 비었거나 구조 없음 -> make scaffold-vault"
	@test -d "$(TRAVEL_ONE)/.claude/skills" && echo "  [ok] Travel-One 설치됨" || echo "  [..] Travel-One 미설치 -> make install-travel-one"
	@test -d "$(BALIPICK)/.claude/skills" && echo "  [ok] Balipick 설치됨" || echo "  [..] Balipick 미설치 -> make install-balipick"
	@test -d "$(BALIPICK_CHAT)/.claude/skills" && echo "  [ok] balipick-chat 설치됨" || echo "  [..] balipick-chat 미설치 -> make install-balipick-chat"
	@echo "  CC 등록 확인: claude mcp list | grep $(MCP_NAME)"

# [LEGACY/DEPRECATED] register-mcp — 1.3.3 plugin.json 일원화로 대체됨.
#   MCP 는 plugin.json 의 mcpServers.ssot-vault 가 plugin:denver-agent:ssot-vault 로 자동 제공한다
#   (플러그인이 켜진 모든 세션). roster 오케스트레이터·do-er 화이트리스트도 plugin prefix
#   (mcp__plugin_denver-agent_ssot-vault__*)에 정합돼 있어, 아래가 출력하는 bare `claude mcp add`
#   등록은 더는 소비되지 않는다(bare prefix 미사용). 구(舊) 수동 경로로만 보존 — 신규 사용 금지.
register-mcp: $(VENV)/.stamp ## [LEGACY] bare MCP 등록 명령 출력 — plugin.json(plugin:denver-agent:ssot-vault)으로 대체됨, 신규 사용 금지
	@echo "⚠️  [LEGACY] register-mcp 는 1.3.3 plugin.json 일원화로 대체됐습니다."
	@echo "    MCP 는 플러그인이 plugin:denver-agent:ssot-vault 로 자동 제공 — 아래 bare 등록은 불요/미소비."
	@echo "    플러그인 미설치(make 단독) 환경에서만 참고하세요."
	@echo ""
	@echo "Claude Code 에 MCP 서버를 등록하세요. MCP 는 config-dir(계정)별로 등록됩니다 —"
	@echo "여러 계정/프로필을 쓰면 각각 등록해야 그 세션에서 도구가 보입니다(세션 시작 시 로드)."
	@echo ""
	@echo "  # 기본 계정:"
	@echo "  claude mcp add $(MCP_NAME) --scope user -- \"$(MCP_PY)\" \"$(MCP_SERVER)\" --vault \"$(VAULT_DIR)\""
	@echo ""
	@echo "  # 다른 config-dir 계정(예시):"
	@echo "  CLAUDE_CONFIG_DIR=~/.claude-account2 claude mcp add $(MCP_NAME) --scope user -- \"$(MCP_PY)\" \"$(MCP_SERVER)\" --vault \"$(VAULT_DIR)\""
	@echo ""
	@echo "  확인:  claude mcp list   (-> $(MCP_NAME) ... Connected)"

review: $(VENV)/.stamp       ## OBEY draft 큐(자동 비준 대상/hold) + 헬스체크
	@$(VPY) _build/review-queue.py --vault "$(VAULT_DIR)"
	@echo ""
	@$(MAKE) -s doctor

# 자동 비준 — 사람 비준 단계 제거. 결정론적으로 안전한 OBEY draft 를 승격하고, 항상 install.
# (스케줄 권장: cron/launchd/CC schedule 로 주기 실행하면 사람·수동 compile 모두 불요.)
# install 은 항상 돌려 에이전트 승격분 + 사람이 Obsidian 에서 고친 stable 변경까지 컴파일한다(멱등).
ratify: $(VENV)/.stamp       ## (스케줄 권장) draft OBEY 자동 비준 → 항상 compile+install
	-$(VPY) _build/ssot-ratify.py --vault "$(VAULT_DIR)" --project "$(TRAVEL_ONE)" --project "$(BALIPICK)"
	@echo ""
	@echo "→ 컴파일·설치(승격분 + 사람 편집 stable 반영, 멱등)"
	@$(MAKE) -s install

clean:                       ## 산출물(.claude/skills) 제거
	rm -rf .claude/skills

distclean: clean             ## 산출물 + .venv 까지 제거
	rm -rf $(VENV)

help:                        ## 타겟 목록
	@grep -E '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  %-10s %s\n", $$1, $$2}'
