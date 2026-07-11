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
# vault 콘텐츠 위치(프로젝트 워크스페이스에서 분리). DW_VAULT_DIR 우선, 기본 ~/denver-workflow-vault.
# 도구(.venv·_build·hooks)는 이 워크스페이스에 잔류 — vault 만 외부화.
# 주의: DW_VAULT_DIR 값에 리터럴 `$HOME`/`~` 가 올 수 있다(settings.json env 규약) —
#       Python 런처(expanduser+expandvars)와 동일하게 shell eval 로 확장한다(make 는 $H 로 오해석).
VAULT_DIR      := $(shell eval echo "$${DW_VAULT_DIR:-$$HOME/denver-workflow-vault}")
# 컴파일러는 상대 --out 을 vault 기준으로 해석하므로(out=vault/out), 워크스페이스 산출물엔 절대경로 사용.
COMPILE := $(VPY) _build/dw-compile.py --vault "$(VAULT_DIR)" --out "$(TOOLS_ROOT)/.claude/skills"

# 플러그인이 들고 있는 제네릭 vault seed(콜드스타트 스캐폴드). 설치 시 빈 vault 로 복사.
# 제네릭화 = '선별'(byte-동일 유지 가능한 프로젝트 무관 노트만) — 손편집 금지(update-seed 가 되돌림).
# 사적 데이터(project/*) 는 seed 에 절대 없음.
SEED          := _seed
SEED_GUIDANCE := karpathy-guidelines tdd-iron-law regression-by-set-diff residual-only delegation-ownership pr-merge-discipline artifact-locations dw-dependencies dw-user-facing-copy denver-workflow dispatch-discipline graphify-search
# 예외: senior-backend-engineer·senior-mobile-engineer 는 _seed 에 손-제네릭화 변형으로 존재
# (vault 본은 프로젝트 특화) — update-seed 화이트리스트에 넣지 말 것(넣으면 특화본이 seed 를 덮어씀).
SEED_AGENTS   := code-review security-qa design-review perf-tester dw-governed dw-ratifier dw-orchestrator senior-front-engineer senior-infra-engineer senior-qa-engineer

.PHONY: build dry-run clean distclean help doctor review ratify install-project

# venv 부트 — .stamp 는 $(VPY)(실제 바이너리)에 의존한다. 플러그인 설치가 stale .stamp 를
# (바이너리 없이) 배포해도, $(VPY) 부재를 감지해 venv 를 재생성한다(부트 스킵 버그 방지).
$(VPY):
	$(PY) -m venv $(VENV)

$(VENV)/.stamp: $(VPY)
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
	@$(VPY) _build/dw-compile.py --vault $(SEED) --out /tmp/seed-skills --dry-run --strict >/dev/null 2>&1 && echo "  [ok] seed strict 컴파일(자기충족·위키링크 폐쇄)" || { echo "  [!!] seed 컴파일 실패 -> .venv/bin/python _build/dw-compile.py --vault $(SEED) --dry-run --strict"; exit 1; }
	@n=$$(find $(SEED)/project -type f ! -name .gitkeep | wc -l | tr -d ' '); [ "$$n" = "0" ] && echo "  [ok] seed 에 사적 project 데이터 0" || { echo "  [!!] seed/project 에 사적 파일 $$n 개 — 제거 필요"; exit 1; }

# 한 프로젝트에 스킬 + 결정론적 검사 매니페스트 + 린터 훅까지 설치.
# MCP 서버(절대경로 — CC/클라이언트가 다른 cwd 에서 spawn 하므로). 도구는 워크스페이스.
MCP_PY     := $(TOOLS_ROOT)/$(VENV)/bin/python
MCP_SERVER := $(TOOLS_ROOT)/_build/dw-mcp-server.py
MCP_NAME   := dw-vault

# 권한 확대는 민감한 자기수정이라 install 과 분리 — 사용자가 명시적으로 실행.
.PHONY: plugin-scope-user plugin-scope-project plugin-scope-off
plugin-scope-user:           ## 플러그인을 사용자 전역 활성(모든 프로젝트). CLAUDE_CONFIG_DIR 계정 기준.
	$(VPY) _build/dw-plugin-scope.py user
plugin-scope-project:        ## 플러그인을 이 프로젝트만 활성. 사용: make plugin-scope-project P=/path/to/project
	$(VPY) _build/dw-plugin-scope.py project "$(P)"
plugin-scope-off:            ## 플러그인 비활성(계정 전역, P 주면 프로젝트도)
	$(VPY) _build/dw-plugin-scope.py off "$(P)"

install-project: $(VENV)/.stamp  ## 한 프로젝트에 설치: make install-project P=/절대경로 [SCOPES=engineering,...]
	@test -n "$(P)" || { echo "사용법: make install-project P=/절대경로 [SCOPES=scope1,scope2]  (SCOPES 생략 = 전체 union)"; exit 1; }
	@test -d "$(VAULT_DIR)/governance" || { echo "vault 없음: $(VAULT_DIR) — /dw-setup 으로 vault(팀 지식 폴더)를 먼저 준비하세요"; exit 1; }
	$(VPY) _build/dw-compile.py --vault "$(VAULT_DIR)" --out "$(P)/.claude/skills" \
		$(if $(SCOPES),--scopes $(SCOPES),) \
		--checks-out "$(P)/.claude/dw-checks.json" \
		--agents-out "$(P)/.claude/agents" \
		--digest-out "$(P)/.claude/dw-session-digest.md"
	$(VPY) _build/wire-hook.py "$(P)" "$(VAULT_DIR)" --config-only
	@echo "✓ 설치 완료: $(P)/.claude/{skills,agents,dw-checks.json,dw-session-digest.md}"

.PHONY: plugin-update
plugin-update:               ## 플러그인 한 방 업데이트(클론 pull + 버전기반 update). ⚠️ plugin.json version 을 먼저 올려야 갱신됨.
	@echo "→ 마켓플레이스 최신화 + plugin update (CC 는 version 기반 — install 은 already-installed no-op)"
	@echo "  ⚠️ plugin.json/marketplace.json version 을 올리지 않으면 'already latest' 로 갱신 안 됨."
	claude plugin marketplace update denver-workflow
	claude plugin update denver-workflow@denver-workflow
	@echo "✓ 새 세션부터 반영. (스케줄로 자동화하려면 cron/launchd 에 이 타깃 등록)"

doctor: $(VENV)/.stamp       ## 콜드스타트 헬스체크(venv·컴파일러·MCP·vault·외부 의존)
	@echo "== denver-workflow 헬스체크 =="
	@$(VPY) -c "import yaml, mcp" 2>/dev/null && echo "  [ok] venv deps: pyyaml + mcp" || echo "  [!!] venv 의존성 누락 -> make build"
	@test -d "$(VAULT_DIR)/governance" && $(VPY) _build/dw-compile.py --vault "$(VAULT_DIR)" --out /tmp/dw-doctor-skills --dry-run --strict >/dev/null 2>&1 && echo "  [ok] 컴파일러 strict 통과" || echo "  [..] vault 컴파일 실패/vault 없음 -> make dry-run 으로 확인"
	@test -f "$(MCP_SERVER)" && echo "  [ok] MCP 서버 존재" || echo "  [!!] MCP 서버 없음"
	@test -d "$(VAULT_DIR)/governance" && echo "  [ok] vault 구조: $(VAULT_DIR)" || echo "  [..] vault 없음 -> /dw-setup 또는 make scaffold-vault"
	@test -f _build/dw-doctor.py && $(VPY) _build/dw-doctor.py || true

review: $(VENV)/.stamp       ## OBEY draft 큐(자동 비준 대상/hold) + 헬스체크
	@$(VPY) _build/review-queue.py --vault "$(VAULT_DIR)"
	@echo ""
	@$(MAKE) -s doctor

# 자동 비준 — 사람 비준 단계 제거. 결정론적으로 안전한 OBEY draft 를 승격하고, 항상 install.
# (스케줄 권장: cron/launchd/CC schedule 로 주기 실행하면 사람·수동 compile 모두 불요.)
# install 은 항상 돌려 에이전트 승격분 + 사람이 Obsidian 에서 고친 stable 변경까지 컴파일한다(멱등).
ratify: $(VENV)/.stamp       ## (스케줄 권장) draft OBEY 자동 비준 → 항상 compile+install
	-$(VPY) _build/dw-ratify.py --vault "$(VAULT_DIR)"
	@echo ""
	@echo "→ 컴파일·설치(승격분 + 사람 편집 stable 반영, 멱등)"
	@echo "→ 설치 반영은 /dw-install (프로젝트별) 로 실행"

clean:                       ## 산출물(.claude/skills) 제거
	rm -rf .claude/skills

distclean: clean             ## 산출물 + .venv 까지 제거
	rm -rf $(VENV)

help:                        ## 타겟 목록
	@grep -E '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  %-10s %s\n", $$1, $$2}'
