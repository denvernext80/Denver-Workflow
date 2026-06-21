# AI Native Workflow — SSOT 기반 에이전트 거버넌스

**Obsidian vault 를 단일 진실 원천(SSOT)** 으로 두고, 규칙·원칙·메모리·계약·스펙을 한 곳에 모아
Claude Code 에이전트가 **읽고 복종하고, 학습을 되써서 갱신**하게 하는 시스템. **사람은 비준·컴파일
바틀넥이 아니다** — 비준·컴파일·세션 주입이 자동화돼 있다.

```
        사람(주로 규칙 저작)
             │
   Obsidian vault (SSOT)
     OBEY  rules·guidance·procedures ─ ssot-ratify(자동 비준) → [컴파일] → .claude/skills
     LIVE  memory·contracts·specs ──── MCP 가 stable 직행(게이트 없음) ←─ 에이전트 read/write
             │ make ratify (비준+compile+install, 스케줄)        │ ssot-vault MCP (8 도구)
             ▼                                                  ▼
   세션 시작: SessionStart 훅이 다이제스트(규율·규칙·지식 인덱스) 주입 → 복종·강제
     Travel-One / Balipick 세션      ·      Claude Code
```

> 설계·불변식은 [BOOTSTRAP.md](./BOOTSTRAP.md). 이 문서는 **운영·사용법**.

## 플러그인으로 설치 (repo-as-plugin)

이 repo 자체가 Claude Code 플러그인이다(`.claude-plugin/plugin.json`·`hooks/`·`commands/`). 한 번에
**MCP(ssot-vault) + 거버넌스 하네스·검증자 에이전트 + worktree/lint/vault 가드 + SessionStart 지식 주입
+ 슬래시 커맨드**가 설치된다. MCP 는 `plugin.json` 의 `mcpServers` 에 단일 선언돼 플러그인이 켜진 모든
세션에 `plugin:denver-agent:ssot-vault`(도구 `mcp__plugin_denver-agent_ssot-vault__*`)로 **자동 제공**된다
— 계정마다 `claude mcp add` 하던 수동 등록이 불필요하다(`.mcp.json` 의 bare 등록은 제거됨, 1.3.3).

```bash
claude plugin marketplace add denvernext80/AI-Native-Workflow   # 또는 로컬 경로
claude plugin install denver-agent@denver-agent
```

### 신규 설치 — vault 준비 (Obsidian + scaffold)

SSOT vault 콘텐츠는 플러그인에 포함되지 않는다(사적 프로젝트 데이터 분리). 플러그인은 **제네릭 seed**
(`_seed/` = 축-B 운영체계 거버넌스 + 폴더 구조 + `VAULT-STRUCTURE.md`)만 들고 있다가 설치 시 빈 vault 로 복사한다.

1. **Obsidian 설치**: https://obsidian.md/download
2. **vault scaffold**: `make scaffold-vault` — `$(VAULT_DIR)`(기본 `~/denver-agent-vault`)가 비었으면 seed 를
   **no-clobber** 복사(기존 콘텐츠 보존). 폴더 구성원칙(축 A/B)이 구조·`VAULT-STRUCTURE.md` 로 박힌다.
3. Obsidian 에서 그 폴더를 **Open folder as vault** 로 열어 사적 콘텐츠(rules·contracts·specs…)를 저작한다.
4. `make build` / `make install`. **이미 vault 가 있으면** scaffold 불요 — vault 를 `~/denver-agent-vault`
   로 이동하거나, 다른 위치면 `DENVER_VAULT_DIR` 로 그 경로를 가리키면 된다.

> seed 는 제네릭 축-B 만(엔지니어링 작업 규율 + 검증자·하네스). 프로젝트 특화 rule·계약·스펙은 사용자가 작성.
> 유지보수: live vault 의 제네릭 분 갱신은 `make update-seed`(화이트리스트 verbatim, 사적 데이터 미포함).

- **MCP 자가 부트스트랩**: `plugin.json` 의 `mcpServers.ssot-vault` → `${CLAUDE_PLUGIN_ROOT}/_build/ssot-mcp-launch.sh`
  가 첫 실행 시 `.venv`(pyyaml·mcp)를 만들고 서버를 vault 경로(규약 해석 결과)로 띄운다(설치 직후 첫 MCP 호출만 느림).
- **vault 위치**: vault 콘텐츠는 이 repo 가 아니라 **별도 폴더**(기본 `~/denver-agent-vault`)에 있다.
  사람은 그 폴더를 Obsidian 으로 열어 편집, 에이전트는 MCP 를 통해 read/write. 이 repo 는
  빌드·플러그인 도구만. `make build|install|ratify` 는 **이 워크스페이스에서** 돌리되 `VAULT_DIR` 로 그 vault 를 읽는다.
- **에이전트**: `agents/*.md` 가 CC 서브에이전트로 로드(`name:` 추가로 Denver·CC 양립). 하네스를 항상-on
  하려면 프로젝트 `settings.local.json` 에 `"agent": "ssot-governed"` 를 둔다(플러그인이 강제하진 않음).
- **커맨드**: `/ssot-build` · `/ssot-ratify` · `/ssot-review` · `/ssot-install`(프로젝트에 스킬·검사·훅·다이제스트 적용) (make 타깃 래핑).
- **외부 의존 플러그인·스킬(번들 아님)**: Denver 워크플로우가 쓰는 외부 스킬은 **번들하지 않는다** —
  사용자가 직접 설치한다(아래 〈외부 의존〉 참조). 중복·라이선스·버전 드리프트를 피한다.
- **한계**: 훅·MCP·에이전트는 전역으로 제공되지만, **프로젝트별 스킬·검사·다이제스트는 여전히
  `make install`(아래)로 생성**한다 — 플러그인은 엔진, 프로젝트별 컴파일은 별도. Makefile 의
  `TRAVEL_ONE`/`BALIPICK` 경로는 이 머신 기준(개인 SSOT 용).

### 외부 의존 플러그인·스킬 (사용자가 직접 설치)

Denver 는 **자기 영역(SSOT·거버넌스·MCP·가드·하네스)만** 번들한다. do-er 에이전트의 워크플로우가
호출하는 외부 플러그인·스킬은 **각 마켓플레이스에서 사용자가 직접 설치**한다(복사본 번들 금지 —
중복·라이선스·버전 드리프트 회피). do-er 들은 이 스킬이 **이미 설치돼 있다고 가정**한다.

| 외부 의존 | 용도 | 요구 수준 | 설치 |
|---|---|---|---|
| **impeccable** (Apache-2.0) | 프론트엔드 디자인 critique·폴리시. `senior-mobile-engineer` 가 디자이너 관점 점검에 **필수** 호출(`balipick-design` 토큰과 병행) | 앱 UI 작업 시 **필수** | `claude plugin marketplace add pbakaus/impeccable`<br>`claude plugin install impeccable@impeccable` |
| **superpowers** | 플랜·스펙·디버깅·TDD 워크플로우. 산출물은 `docs/superpowers/` 관례 경로(durable 은 vault 메모리로) | 플랜/스펙 작업 시 **권장** | `claude plugin marketplace add anthropics/claude-plugins-official`<br>`claude plugin install superpowers@claude-plugins-official` |

- **설치 확인**: `claude plugin list` 에 노출돼야 한다(예: `impeccable@impeccable 3.1.1`,
  `superpowers@claude-plugins-official`). 미설치 시 디자인 게이트(impeccable critique)를 통과시킬 수 없다.
- **신규 외부 의존 추가 규율**: do-er 에이전트가 새 외부 스킬을 요구하게 되면 — **복사(벤더링) 금지.**
  이 표에 한 줄(용도·요구 수준·설치 명령)을 추가하고, 해당 do-er(`roster/*.md`)에 "○○ 스킬 필수"를 명시한다.

`pyyaml`·`mcp` 가 유일한 외부 의존성이며, PEP 668 환경을 깨지 않도록 `make` 가 전역이 아닌
프로젝트-로컬 `.venv` 에 자동 설치한다(수동 설치 불요).

## 빌드

```bash
make build      # vault 컴파일 → .claude/skills (vault 로컬)
make dry-run    # 쓰기 없이 검증/요약 (CI: 경고도 에러)
make doctor     # 콜드스타트 헬스체크 (venv·컴파일러·MCP·설치 상태)
make ratify     # (스케줄 권장) draft OBEY 자동 비준 → 항상 compile+install (사람·수동 불요)
make review     # OBEY draft 큐(ratify 가 hold 한 판단필요 건) + 헬스체크
make clean      # 산출물 제거    /  make distclean  # 산출물 + .venv 제거
```

## 콜드스타트

| Tier  | 상황             | 할 일                                                                    |
| ----- | -------------- | ---------------------------------------------------------------------- |
| **1** | 매 새 CC 세션(평상시) | 없음 — SessionStart 훅이 다이제스트(규율·규칙·지식 인덱스)를 컨텍스트에 주입(`🔒 SSOT … 주입됨` 표시). 스킬·훅·서브에이전트·MCP 자동 로드. 점검 `claude mcp list \| grep ssot-vault`(→ `plugin:denver-agent:ssot-vault … Connected`) |
| **2** | 재부팅 후          | 동일(절대경로 + `.venv` 영속). `make doctor`                                   |
| **3** | 새 머신/재클론       | 플러그인 설치(위 〈플러그인으로 설치〉)면 MCP 자동. vault scaffold 후 `make install` 로 프로젝트별 산출물 생성 |

```bash
# Tier 3 — 풀 부트스트랩
# 0) Makefile 상단 REPO_ROOT/TRAVEL_ONE/BALIPICK 경로를 이 머신에 맞게 수정
make build          # .venv(pyyaml·mcp) + 컴파일
make install        # 양 프로젝트에 스킬·검사·훅·에이전트 설치
make grant-access   # (선택) vault 쓰기 권한 사전 승인
make doctor         # 전체 [ok] 확인
# MCP 는 플러그인(plugin.json)이 plugin:denver-agent:ssot-vault 로 자동 제공 — 별도 등록 불요.
```

> **MCP 등록은 plugin.json 일원화(1.3.3)로 자동.** 플러그인이 켜진 세션엔 config-dir(계정/프로필)
> 마다 따로 `claude mcp add` 할 필요가 없다 — `plugin:denver-agent:ssot-vault` 가 모든 세션에 노출된다.
> roster 오케스트레이터·do-er 화이트리스트도 이 플러그인 prefix(`mcp__plugin_denver-agent_ssot-vault__*`)에
> 정합돼 있다. MCP 도구는 **세션 시작 시 로드**되므로 플러그인 갱신 후엔 새 세션을 연다. MCP 미가용
> 세션은 가드가 검사하는 직접 `.md` 쓰기로 폴백(백스톱).
> 〔legacy〕 `make register-mcp` 는 bare `claude mcp add` 명령을 출력하는 구(舊) 수동 경로다 —
> plugin.json 선언으로 대체됐고 roster 가 plugin prefix 를 쓰므로 bare 등록은 더는 소비되지 않는다.

## 대상 프로젝트에 설치

`make install-*` 은 그 프로젝트의 `.claude/` 에 **관련 scope 의 스킬 + 결정론적 검사 + 훅 4종
(린터·vault 가드·worktree 가드·SessionStart 컨텍스트) + 서브에이전트 + 세션 다이제스트**를 설치한다
(계약은 vault 단일 SSOT 라 미러하지 않는다).

```bash
make install                # 모든 대상 프로젝트
make install-travel-one     # backend-php·auth·api-contract·content-policy·engineering
make install-balipick       # mobile-flutter·design-system·auth·api-contract·engineering
```

- scope→프로젝트 매핑은 `Makefile` 상단(`TRAVEL_SCOPES`/`BALIPICK_SCOPES`).
- **부분 빌드**: 각 프로젝트의 `.ssot-manifest.json`/`.ssot-agents.json` 기준으로 우리 산출물만
  정리하므로 대상 repo 의 **기존 스킬·에이전트(예: denver-workflow)는 보존**된다.
- 설치된 산출물은 **직접 편집 금지** — vault 를 고친 뒤 `make install-*` 재실행.

## 강제 — 능동 하네스가 게이트를 돌린다

아래 게이트 레이어들은 그 자체로는 *권고*다(ambient 규칙·피드백 훅·on-demand 리뷰 — "안다"이지 "못 어긴다"가 아님).
**`ssot-governed` 하네스 에이전트**가 이들을 *강제된 루프*로 묶는다:
규칙 pull(`ssot_search`) → 작업 → 결정론 검사 → 검증자 호출 → **통과까지 루프** → 완료 게이트.
양 프로젝트는 `settings.local.json` 의 **`"agent": "ssot-governed"`** 로 **모든 세션이 하네스로 시작**(항상 강제).
하네스는 vault `agents/ssot-governed.md`(`install: always`)에서 컴파일된다.

게이트 레이어:
0. **세션 주입**(SessionStart 훅) — `ssot-session-context.py` 가 프로젝트 다이제스트(항상-적용 guidance +
   강제 규칙 목록 + 누적 지식 인덱스)를 세션 시작 시 컨텍스트에 주입(`🔒` 표시). CC 스킬 body 는
   자동 로드 안 되므로(progressive disclosure) 이 주입이 규칙·지식을 세션에 닿게 하는 실제 경로다.
1. **자동 비준**(`make ratify`, 스케줄) — OBEY draft 를 결정론적 검증(스키마·enforced-by 실재·check
   패턴을 실제 코드에 돌려 0매치)해 안전분만 자동 stable·compile·install. 판단필요 건만 `ssot-ratifier`(LLM).
2. **MCP 도구** — `ssot_write_*` 가 frontmatter 구성(status 파라미터 없음). LIVE 는 stable 직행, OBEY 만 draft 제안.
3. **결정론적 린터**(PostToolUse) — 규칙 `check-deny`/`check-require` → `.claude/ssot-checks.json` + `ssot-lint.py`.
   위반을 `additionalContext` 로 **피드백**(차단 아님, self-correct 유도).
4. **worktree 가드**(PreToolUse, `Agent|Task`) — 파일 변경 에이전트를 격리 없이 spawn 하면 `ask`(공유 체크아웃 main 오염 방지).
5. **vault 가드**(PostToolUse 백스톱) — raw `.md` 쓰기의 frontmatter 계약 검사.
6. **서브에이전트**(판단) — `enforced-by` 가 참조하는 검증자(security-qa/code-review/design-review)만 설치.

이들을 **`ssot-governed` 하네스**가 강제 루프로 묶는다(규칙 pull → 작업 → 검사 → 검증자 → 통과까지 루프).
하네스 콜드스타트는 **vault 전체 재검색 금지** — 규칙은 이미 로드(스킬+다이제스트), LIVE 만 작업이 호명한 대상을 좁게 pull.

**오탐 방지**: 모든 검사는 `check-glob` 로 파일형 한정 + `check-exclude` 로 생성물(`*/dist/*`)·
테스트(`tests/*`)·정본 정의 파일(`*balipick_colors.dart`)을 제외한다 — 실제 코드베이스 감사로 오탐 0.

> **검증 상태**: SessionStart 훅 발화는 실제 세션에서 `🔒 SSOT … 주입됨` 표시로 확인됨. grep 못 잡는
> 구조 규칙은 서브에이전트 리뷰(문서적)가 담당한다.

## MCP 게이트웨이 — `ssot-vault`

vault 를 stdio MCP 서버(`_build/ssot-mcp-server.py --vault <path>`)로 노출. 쓰기 도구에 status
파라미터 없음(validate-by-construction). 읽기는 status 무관 — LIVE 는 stable 직행, OBEY 만 비준 대상:

| | 도구 |
|---|---|
| **읽기** | `ssot_search(query)` · `ssot_read(name)` · `ssot_list(type?)` (draft·stable 모두) |
| **쓰기·LIVE(stable 직행)** | `ssot_write_memory` · `ssot_write_contract` · `ssot_write_spec` |
| **쓰기·OBEY(draft→자동 비준)** | `ssot_write_procedure` · `ssot_propose_rule` |

등록: 플러그인(`plugin.json` 의 `mcpServers.ssot-vault`)이 `plugin:denver-agent:ssot-vault` 로 자동 제공 —
별도 `claude mcp add` 불요. (legacy `make register-mcp` 는 bare 등록 명령을 출력하나 plugin.json 으로 대체됨.)

### vault 경로 — 규약 경로와 커스텀 위치

**기본(규약 경로)**: 런처(`ssot-mcp-launch.sh`)는 `~/denver-agent-vault` 를 vault 로 자동 해석한다.
별도 env 설정 없이도 에이전트 writes 가 이 폴더에 직접 기록된다. `make scaffold-vault` 도 이 경로를
기본 타깃으로 생성한다.

해석 순서: `DENVER_VAULT_DIR`(env, 존재하는 폴더) > `~/denver-agent-vault`(규약) > **에러(exit 1)**.
vault 폴더가 없으면 런처는 기동하지 않는다 — 플러그인 루트 캐시 폴백 없음.

**커스텀 위치**: vault 를 다른 경로에 두고 싶을 때만 `DENVER_VAULT_DIR` 를 설정한다(탈출구).
`plugin.json` 의 `mcpServers.ssot-vault.env` 는 `{}` — 런처가 환경·규약 경로를 해석하므로 선언에 박힌 값이 없다
(루트 `.mcp.json` 은 1.3.3 에서 비워짐 `{}`). 별도 export 나 선언 수정 없이 동작하는 것이 기본이다.

```sh
# 커스텀 vault 위치만 — 기본 ~/denver-agent-vault 쓴다면 불요
export DENVER_VAULT_DIR="$HOME/My Vaults/denver"   # CC 시작 전 export
```

**coherence**: 컴파일·비준은 같은 vault 를 읽어야 한다. `make build|install|ratify` 는 **이 워크스페이스에서**
실행하되, Makefile 의 `VAULT_DIR`(= `DENVER_VAULT_DIR` 우선, 기본 `~/denver-agent-vault`)로 그 vault 를 읽는다
(`--out` 산출물은 `TOOLS_ROOT` = 워크스페이스 절대경로). 도구·`.venv` 는 워크스페이스, vault 콘텐츠는 별도 폴더.

## 기존 vault 마이그레이션 (`~/denver-agent-vault` 규약으로)

기존에 `../Obsidian-Vault` 또는 다른 경로를 vault 로 쓰던 환경을 규약 경로로 이전하는 절차.
**수동 동의 절차** — 자동 스크립트 미채택.

**전제**: 플러그인 1.2.0 재설치 완료(규약-인식 런처).

1. **vault 이동**:
   ```sh
   mv ~/Desktop/Repository/Obsidian-Vault ~/denver-agent-vault   # 타깃 존재 시 중단
   ```
2. **3개 타깃 레포 grant 재생성**:
   ```sh
   python3 _build/grant-vault-access.py <repo> ~/denver-agent-vault   # Travel-One/Balipick-App/balipick-chat
   ```
   각 레포 `.claude/settings.local.json` 에서 옛 절대경로(`.../Obsidian-Vault/**`) 라인 수동 삭제.
3. **Obsidian 재지정**: Obsidian 에서 "Open folder as vault" → `~/denver-agent-vault`
4. **MEMORY.md 경로 확인**: `~/denver-agent-vault/memory/MEMORY.md` 로 갱신됐는지 확인.
5. **CLAUDE.md 참조 갱신**: 각 레포·워크스페이스의 CLAUDE.md 에 `../Obsidian-Vault` 참조가 있으면
   `~/denver-agent-vault` 로 수정.
6. **셸 export 제거**: `~/.zshrc` 의 `DENVER_VAULT_DIR` export 를 제거(규약 해석 실증).
7. **타 프로파일·CI 점검**: 다른 셸 프로파일이나 CI 환경에 `DENVER_VAULT_DIR` 가 남아 있으면 제거
   또는 새 경로로 갱신.

이후 `make doctor` 로 [ok] 전체 확인.

## 메모리 & 계약 — vault 단일 SSOT

- **메모리**(`memory/`): 라이브, 비컴파일. 에이전트가 `ssot_write_memory` 로 stable 기록(읽기가 status
  무관 → 게이트 무의미). CC **auto-memory 도 `autoMemoryDirectory` 로 vault 로 funnel** → 자동 캡처가
  vault 단일 SSOT 로 수렴(가드·도구가 CC 포맷 `name/metadata.type` 과 vault 포맷 `type:memory` 둘 다 수용).
- **계약**(`contracts/`): 라이브, 비컴파일, **repo 미러 없음**. `ssot_write_contract` 로 작성(stable).
  완결분은 `contracts/archive/`(활성 검색 제외, 경로 직접 읽기 가능).
- **자동 노출(읽기 절반)**: CC 스킬 body 는 자동 로드 안 됨(description 만) — 그래서 규칙·지식이 세션에
  안 닿았다(가이던스 무시의 근본 원인). 해결: `make install` 이 프로젝트별 **다이제스트**
  (`.claude/ssot-session-digest.md`: 항상-적용 guidance + 강제 규칙 목록 + 누적 지식 인덱스)를 만들고,
  `ssot-session-context.py`(**SessionStart 훅**)가 세션 시작 시 컨텍스트에 직접 주입한다. 전문은 `ssot_read`.
  scope 어휘는 `SCOPE_ALIASES` 로 정규화(freeform·skill-이름 흡수), orphan 은 `engineering` 인덱스로 흡수.

## vault 작성 규칙

**폴더는 사람용 정리, frontmatter 는 기계용 라우팅.** 규칙 노트를 엉뚱한 폴더에 둬도 컴파일은 정확하다.
최상위는 **governance/**(역할·기능·원칙·법)와 **project/**(프로젝트 작업 산출물)로 분리한다.

| 폴더 | 용도 | 컴파일 |
|---|---|---|
| `governance/_skills/` | skill-manifest (scope 묶음 정의) | ✅ |
| `governance/rules/` | "법" — 검증 가능한 강제(`enforced-by` 필수) | ✅ stable |
| `governance/guidance/` | 작업 규율 — 공유 원칙(enforced-by 불요) | ✅ stable |
| `governance/procedures/` | 재사용 절차(playbook) — **에이전트 저작**(draft→ssot-ratify 자동 비준) | ✅ stable |
| `governance/agents/` | 역할(검증자·하네스) 정의(`enforced-by` 대상) | (서브에이전트로 설치) |
| `project/decisions/` | ADR(아키텍처 결정 기록) — append-only | ❌ |
| `project/memory/` | 에이전트 학습 — 라이브 | ❌ |
| `project/contracts/` | 백엔드↔앱 계약 SSOT — 라이브(`archive/` 포함) | ❌ |
| `project/specs/` | 계획·스펙·설계 SSOT — 라이브(worktree 휘발 방지, `archive/`) | ❌ |
| `_build/` · `_templates/` · `.obsidian/` | 컴파일러 · 저작 템플릿 · Obsidian 설정 | ❌ |

> 폴더 경로는 사람·MCP·ratify·review 가 참조하지만, **컴파일러는 frontmatter `type` 으로만 라우팅**(rglob 전체 스캔)하므로 재배치에 안전하다.

**Obsidian 으로 열기**: 이 폴더 자체가 볼트(`.obsidian/` 포함). 명령 팔레트 → *Insert template* 로
`rule`/`guidance`/`memory`/`contract`/`agent`/`skill-manifest`/`decision` frontmatter 를 채워 시작.
위키링크 `[[노트]]` 는 컴파일러가 평탄화. 저작 후 `make build`/`make install`.

## Frontmatter 계약

| 필드 | 값 | 동작 |
|---|---|---|
| `type` | `rule`/`guidance`/`procedure`/`memory`/`contract`/`spec`/`decision`/`reference`/`skill-manifest`/`agent` | 라우팅 시작점 |
| `scope` | kebab-case 도메인 | skill 묶음 단위 |
| `status` | `draft`/`stable`/`deprecated` | **`stable` 만 컴파일·강제** |
| `compiles-to` | `skill` | 있어야 스킬 포함 |
| `enforced-by` | 검증자 id | rule 필수. `agents/` 에 없으면 경고 |
| `skill-name`·`skill-description` | — | skill-manifest 필수 |
| `title` | 사람용 제목 | 규칙 섹션 헤딩 |
| `check-deny`·`check-require` | 정규식/목록 | 린터 위반 판정(deny=있으면, require=없으면) |
| `check-glob`·`check-exclude` | glob/목록 | 검사 대상 한정 — **glob 없으면 검사 비활성** |
| `check-hint` | 문구 | 위반 시 수정 안내 |

**type 별 필수 필드**
- `rule`: `type scope status enforced-by compiles-to`
- `guidance`: `type scope status compiles-to` (enforced-by 불요 — 강제 게이트 아닌 작업 규율)
- `skill-manifest`: `type scope skill-name skill-description`
- `memory`/`contract`: `type status` (+`title`) · `agent`/`decision`: `type`

## 검증: 에러 vs 경고

| 상황 | 기본 | `--strict` |
|---|---|---|
| `type:rule` 인데 `enforced-by` 없음 | **에러(exit 1)** | 에러 |
| `enforced-by` 가 `agents/` 에 없음 | 경고 | **에러** |
| skill-manifest 필수 필드 누락 / scope 중복 / 고아 노트 | **에러** | 에러 |
| dataview/embed 정제, manifest 만 있고 규칙 없는 scope | 경고 | **에러** |

불변식 9개 + 설계 근거(스킬 body 비자동로드 → SessionStart 주입, 자동 비준 등)는 [BOOTSTRAP.md](./BOOTSTRAP.md) 참조.
