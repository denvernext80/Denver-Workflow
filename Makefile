# SSOT vault → .claude/skills 빌드 — **개발자 인터페이스**.
#
# ⚠️ 로직의 정본은 `_build/dw.py`(이식 가능 CLI)다. 이 Makefile 은 **얇게 위임**한다.
#    슬래시 커맨드가 부르는 것도 그 CLI 다 — 구현을 둘로 두면 `make X` 와 `/dw-X` 가 갈라진다
#    (이 레포에서 반복 관측된 결함 클래스). 새 동작은 CLI 에 넣고 여기서 위임만 추가하라.
#    `dw-selftest.py` 가 "위임 타깃의 레시피가 실제로 CLI 호출뿐인지" 를 검사한다.
#
# make 자체는 여전히 필요하다 — 단 **개발자용**이다. Windows 에는 make 가 없고
# (Git for Windows 는 grep·uname·cp 는 주지만 make 는 주지 않는다) 그래서 커맨드 문서는
# 2.15.0 부터 CLI 를 직접 부른다.
#
# pyyaml 는 이 컴파일러의 유일한 외부 의존성이다. PEP 668(externally-managed)
# 환경을 깨지 않도록 전역이 아닌 프로젝트-로컬 .venv 에 설치한다.

PY      := python3
DW      := $(PY) _build/dw.py
VENV    := .venv
VPY     := $(VENV)/bin/python
# 도구 루트 = 이 워크스페이스(.venv·_build·hooks·.claude 산출물 잔류).
TOOLS_ROOT := $(shell pwd)

# ⚠️ vault 해석의 정본은 `dw_runtime` 이다 — Makefile 은 **사본을 갖지 않는다**(2.16.0).
# 종전: `VAULT_DIR := $(shell eval echo "$${DW_VAULT_DIR:-$$HOME/<규약>}")`. 두 가지가 문제였다 —
#   ① 셸 `eval` 은 경로 **중간**의 `$VAR`·명령치환까지 확장해 CLI(접두 전용)보다 넓었다
#      (실측: `/x/$NOPE/v` → `/x//v` = 존재하는 **엉뚱한** 경로). 그래서 `make` 만 다른 vault 를
#      가리킬 수 있었다. ② `:=` 라 VAULT_DIR 를 쓰지도 않는 `make build`·`make test` 에서까지
#      parse 시점에 셸이 돌았다.
# 지금은 **쓰는 레시피 안에서만** CLI 를 부른다(`V="$$($(VAULT_CMD))"`). 아래 3 타깃은 위임하지
# 않는 **개발자 전용**이라 POSIX 셸을 쓴다(이식 범위 밖 — 의도적 잔여, CHANGELOG 명시).
VAULT_CMD      := $(PY) _build/dw.py vault-path

# 플러그인이 들고 있는 제네릭 vault seed(콜드스타트 스캐폴드). 설치 시 빈 vault 로 복사.
# 제네릭화 = '선별'(byte-동일 유지 가능한 프로젝트 무관 노트만) — 손편집 금지(update-seed 가 되돌림).
# 사적 데이터(project/*) 는 seed 에 절대 없음.
SEED          := _seed
SEED_GUIDANCE := karpathy-guidelines tdd-iron-law regression-by-set-diff residual-only delegation-ownership pr-merge-discipline artifact-locations dw-dependencies dw-user-facing-copy denver-workflow dispatch-discipline graphify-search
# 예외: senior-backend-engineer·senior-mobile-engineer 는 _seed 에 손-제네릭화 변형으로 존재
# (vault 본은 프로젝트 특화) — update-seed 화이트리스트에 넣지 말 것(넣으면 특화본이 seed 를 덮어씀).
SEED_AGENTS   := code-review security-qa design-review perf-tester dw-governed dw-ratifier dw-orchestrator senior-front-engineer senior-infra-engineer senior-qa-engineer

.PHONY: build dry-run test clean distclean help doctor review ratify install-project workflow-report venv

# venv 부트 — CLI 에 위임(멱등: 이미 있으면 즉시 반환). `mcp<2` 핀은 `dw_runtime.DEPS` 한 곳에만
# 있다 — 종전엔 이 레시피와 런처 양쪽에 리터럴로 있어 갈릴 여지가 있었다(2.15.0 에서 통합).
# .stamp 파일을 없앤 이유: "stamp 는 있는데 바이너리는 없는" 상태가 부트를 건너뛰게 만드는
# 버그 클래스였다. phony 로 두고 CLI 가 실제 바이너리 존재를 매번 확인한다.
venv:                        ## venv 부트스트랩(멱등 — 이미 있으면 즉시 반환)
	@$(DW) bootstrap

build:                       ## vault 를 컴파일해 .claude/skills 생성
	$(DW) build

dry-run:                     ## 쓰기 없이 검증/요약(CI 용, 경고도 에러)
	$(DW) dry-run

# 엔진 자기검사. 픽스처는 _seed 복사본 — 사용자 vault(`dw.py vault-path`)는 건드리지 않는다.
# (dry-run/doctor 는 live vault 를 컴파일할 뿐이라 엔진 동작을 증명하지 못한다 — 그 몫이 이 타깃.)
test: venv                   ## 엔진 자기검사(stdlib unittest, 임시 vault 픽스처)
	$(VPY) _build/dw-selftest.py

.PHONY: scaffold-vault update-seed seed-check
scaffold-vault:              ## 빈/없는 vault 에 제네릭 seed(축B 거버넌스+폴더 구조+VAULT-STRUCTURE) 복사 (no-clobber)
	$(DW) scaffold-vault

update-seed: venv            ## live vault 의 제네릭 축-B 노트를 _seed 로 갱신(화이트리스트 verbatim; 사적 project 제외)
	@V="$$($(VAULT_CMD))"; \
	echo "→ _seed 갱신: live $$V → $(SEED) (화이트리스트만, project 사적 데이터 미포함)"; \
	for g in $(SEED_GUIDANCE); do cp "$$V/governance/guidance/$$g.md" $(SEED)/governance/guidance/; done; \
	for a in $(SEED_AGENTS); do cp "$$V/governance/agents/$$a.md" $(SEED)/governance/agents/; done; \
	cp "$$V/governance/_skills/engineering.md" $(SEED)/governance/_skills/; \
	cp "$$V"/_templates/*.md $(SEED)/_templates/ 2>/dev/null || true
	@$(MAKE) -s seed-check

# ⚠️ 위임하지 않은 개발자 전용 타깃 — find|wc|tr 파이프라인은 POSIX 셸에 의존한다.
#    커맨드(슬래시)에서 부르지 않으므로 이식 범위 밖이다(의도적 잔여 — CHANGELOG 명시).
seed-check: venv            ## seed 자기충족 검증(strict 컴파일 + 사적 데이터 0)
	@$(VPY) _build/dw-compile.py --vault $(SEED) --out /tmp/seed-skills --dry-run --strict >/dev/null 2>&1 && echo "  [ok] seed strict 컴파일(자기충족·위키링크 폐쇄)" || { echo "  [!!] seed 컴파일 실패 -> .venv/bin/python _build/dw-compile.py --vault $(SEED) --dry-run --strict"; exit 1; }
	@n=$$(find $(SEED)/project -type f ! -name .gitkeep | wc -l | tr -d ' '); [ "$$n" = "0" ] && echo "  [ok] seed 에 사적 project 데이터 0" || { echo "  [!!] seed/project 에 사적 파일 $$n 개 — 제거 필요"; exit 1; }

# 권한 확대는 민감한 자기수정이라 install 과 분리 — 사용자가 명시적으로 실행.
#
# ⚠️ P 가드(`@test -n`)는 **의도적 비대칭**이다. CLI 는 `--project` 생략 시 현재 디렉토리를
#    기본값으로 삼지만(커맨드 문서에서 `$(pwd)` 셸 치환을 없애려면 그래야 한다), make 는
#    종전처럼 P 없이 부르면 사용법을 내고 멈춘다 — 그러지 않으면 무심한 `make install-project`
#    가 **플러그인 루트 자신**에 설치해 버린다(make 의 cwd). 가드는 로직이 아니라 입력 검증이라
#    "구현이 둘" 이 되지 않는다.
.PHONY: plugin-scope-user plugin-scope-project plugin-scope-off
plugin-scope-user:           ## 플러그인을 사용자 전역 활성(모든 프로젝트). CLAUDE_CONFIG_DIR 계정 기준.
	$(DW) plugin-scope-user
plugin-scope-project:        ## 플러그인을 이 프로젝트만 활성. 사용: make plugin-scope-project P=/path/to/project
	@test -n "$(P)" || { echo "사용법: make plugin-scope-project P=/절대경로"; exit 1; }
	$(DW) plugin-scope-project --project "$(P)"
plugin-scope-off:            ## 플러그인 비활성(계정 전역, P 주면 프로젝트도)
	$(DW) plugin-scope-off $(if $(P),--project "$(P)",)

install-project:             ## 한 프로젝트에 설치: make install-project P=/절대경로 [SCOPES=engineering,...]
	@test -n "$(P)" || { echo "사용법: make install-project P=/절대경로 [SCOPES=scope1,scope2]  (SCOPES 생략 = 전체 union)"; exit 1; }
	$(DW) install-project --project "$(P)" $(if $(SCOPES),--scopes $(SCOPES),)

.PHONY: plugin-update
plugin-update:               ## 플러그인 한 방 업데이트(클론 pull + 버전기반 update). ⚠️ plugin.json version 을 먼저 올려야 갱신됨.
	@echo "→ 마켓플레이스 최신화 + plugin update (CC 는 version 기반 — install 은 already-installed no-op)"
	@echo "  ⚠️ plugin.json/marketplace.json version 을 올리지 않으면 'already latest' 로 갱신 안 됨."
	claude plugin marketplace update denver-workflow
	claude plugin update denver-workflow@denver-workflow
	@echo "✓ 새 세션부터 반영. (스케줄로 자동화하려면 cron/launchd 에 이 타깃 등록)"

doctor:                      ## 콜드스타트 헬스체크(venv·컴파일러·MCP·vault·외부 의존)
	$(DW) doctor

# ⚠️ 종전엔 이 레시피 끝에 `$(MAKE) -s doctor` 가 붙어 있었다. 헬스체크는 이제 CLI 의 review
#    안에서 돈다 — 여기 남겨두면 두 번 출력된다.
review:                      ## OBEY draft 큐(자동 비준 대상/hold) + 헬스체크
	$(DW) review

# 자동 비준 — 결정론적으로 안전한 OBEY draft 를 승격한 뒤, **이 타깃이 직접** 등록된 모든
# 프로젝트에 compile+install 한다(멱등).
#
# ⚠️ 종전엔 dw-ratify.py 가 "실제 컴파일·설치는 호출자가 한다" 고 위임했는데 이 레시피는 @echo 두
#    줄이 전부였다 — 승격돼도 어느 레포에도 반영되지 않았다(2.13.0 에서 수정). 문구도 함께 고쳤다.
#
# 평시 자동 실행은 **세션 시작 훅**(_build/dw-ratify-session.py)이 담당한다 — 호스트 스케줄러
# (launchd/cron/Task Scheduler)를 정본으로 쓰지 않는 이유는 이 플러그인의 훅이 전부 순수 python3
# (플랫폼 중립)이라서다. 이 타깃은 같은 일을 지금 당장 하는 수동 경로다.
#
# check 패턴을 가진 규칙은 **실제 코드에 돌려 오탐 0** 을 확인한 뒤에만 승격된다. 스캔·설치 대상은
# `<vault>/.dw-state/projects.json`(= `make install-project` 가 자동 등록)에서 읽는다.
# 일회성으로 다르게 주려면: make ratify RATIFY_PROJECTS="/abs/repo1 /abs/repo2"
RATIFY_PROJECTS ?=
ratify:                      ## draft OBEY 자동 비준 → 등록된 모든 프로젝트에 compile+install(멱등)
	$(DW) ratify $(foreach p,$(RATIFY_PROJECTS),--project "$(p)")

workflow-report: venv        ## dw 워크플로우 리포트(3대 규율 준수율·절차/memory 재사용). 사용: make workflow-report [V=/abs/vault] [DAYS=30]
	@V="$(or $(V),$$($(VAULT_CMD)))"; $(VPY) _build/dw-workflow-report.py --vault "$$V" --days $(or $(DAYS),30)

clean:                       ## 산출물(.claude/skills) 제거
	rm -rf .claude/skills

distclean: clean             ## 산출물 + .venv 까지 제거
	rm -rf $(VENV)

help:                        ## 타겟 목록
	@grep -E '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  %-10s %s\n", $$1, $$2}'
