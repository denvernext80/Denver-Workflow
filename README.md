# Denver AI Workflow

**팀의 지식(규칙·계약·학습)을 한 폴더에 모아 두고, Claude Code 에이전트가 그걸 읽고 따르고 되쓰게
만드는 시스템.** 지식 폴더 하나를 **단일 진실 원천**(SSOT — "한 곳만 믿는 원본")으로 삼습니다.

> **비개발자도 씁니다.** 아래 〈빠른 시작〉 3단계면 준비 끝입니다. 그 아래는 필요할 때만 읽으세요.

---

## 이게 뭔가요? (한 문단)

프로젝트가 커지면 "우리 팀은 이렇게 일한다"·"이 API 는 이런 계약이다"·"저번에 이걸 이렇게 고쳤다"
같은 지식이 여기저기 흩어집니다. Denver 는 이 지식을 **Obsidian**(노트 앱) 폴더 하나에 모으고,
Claude Code 가 매 작업에서 **자동으로 그 규칙을 지키고, 새로 배운 걸 다시 그 폴더에 적어** 넣게 합니다.
사람이 매번 규칙을 붙여넣거나 검토·승인하는 병목이 없습니다 — 검증·컴파일·주입이 자동입니다.

```
          사람 (주로 규칙 저작)
               │
     Obsidian vault (SSOT · 팀 지식 폴더)
       OBEY  규칙·지침·절차 ── dw-ratify(자동 검증·승인) → [컴파일] → .claude/skills
       LIVE  학습·계약·스펙·백로그·참조 ── MCP 가 즉시 저장 ←── 에이전트가 읽고/쓰기
               │                                              │ dw-vault MCP (11 도구)
               ▼                                              ▼
     세션 시작: 훅이 "지켜야 할 규율 + 규칙 + 지식 인덱스"를 자동 주입 → 복종·강제
       대상 프로젝트 세션        ·        Claude Code
```

> 이 문서는 **사용법·운영**입니다. 설계 원리·불변식은 [BOOTSTRAP.md](./BOOTSTRAP.md).

---

## 🚀 빠른 시작 (3단계)

1. **플러그인 설치** — 터미널에서 Claude Code 를 열고 두 줄을 붙여넣기:
   ```
   claude plugin marketplace add https://github.com/denvernext80/Denver-Workflow
   claude plugin install denver-workflow@denver-workflow
   ```
2. **초기 설정** — 세션에서 `/dw-setup` 입력. 도우미가 필요한 프로그램(Obsidian 등) 설치, 지식
   폴더(vault) 준비, 이 프로젝트 연결까지 알아서 안내합니다(새 프로젝트·기존 프로젝트·멀티레포 자동 판별).
3. **사용 시작** — `/denver-workflow` 입력. 기능 개발 전 과정(요구사항 → 배포)을 11단계로 안내합니다.

> 단발 수정(오타·1줄 fix)은 11단계가 아니라 바로 git 흐름으로 갑니다. 신규 기능일 때만 풀사이클.

---

## 커맨드 (슬래시 명령)

| 커맨드 | 하는 일 |
|---|---|
| `/dw-setup` | **초기 설정 도우미** — 프로그램 설치·vault 준비·프로젝트 연결을 한 번에 |
| `/denver-workflow` | **기능 개발 풀사이클** — 요구사항 → 배포 11단계(멀티레포 디스패치) |
| `/dw-install` | vault 최신 상태(규칙·검사·에이전트·세션 다이제스트)를 프로젝트에 설치/갱신 |
| `/dw-build` | vault 를 컴파일(`.claude/skills`) — dry-run strict 검증 후 빌드 |
| `/dw-ratify` | draft 규칙·절차를 **자동 검증·승인** → 통과분 stable·컴파일·설치(사람 불요) |
| `/dw-review` | 자동 승인이 보류한 "판단 필요" 큐 + 헬스체크 |
| `/dw-scope` | 플러그인 활성 범위 — 사용자 전역 vs 이 프로젝트만 |
| `/dw-ci-review` | **(선택) GitHub PR 자동 리뷰어** 설치 — PR 마다 Claude 가 코드 리뷰(11단계 ⑥ 자동화) |

---

## 기능 개발 풀사이클 — `/denver-workflow`

신규 기능을 **요구사항 → 배포**까지 **11단계**로 안내하는 멀티에이전트 워크플로우입니다. 여러
저장소를 함께 쓰면(멀티레포) 변경 면(프론트·백엔드·QA…)에 맞는 저장소와 담당 에이전트(do-er)로
**자동 분기(dispatch)** 합니다. 각 단계엔 전담 스킬/에이전트가 있고, 막히면 **advisor**(더 강한
리뷰어 모델)로 **에스컬레이션**합니다.

> - **단발 수정은 제외** — 오타·1줄 fix·문서만 바꾸는 건 11단계를 건너뛰고 바로 git 흐름으로.
> - **첫 1회 준비(0단계)** — 멀티레포면 `/denver-workflow` 가 **저장소 지도(repo-map)**를 대화식으로
>   만듭니다(어느 저장소에 어떤 담당자를 붙일지). 기술자가 한 번 설정하면 이후엔 일상 실행만.

### 4국면(PDCA) 흐름 — 설계 → 구현 → 검증 → 배포

11단계는 크게 **네 국면**으로 묶입니다(PDCA: Plan·Do·Check·Act). 설계와 구현 사이에는
**API 계약 GATE**(관문)가 있어, 계약이 확정돼야 구현에 들어갑니다.

| 국면 | # | 단계 | 도구(스킬/에이전트) |
|---|---|---|---|
| **① 설계** (Plan) | 1 | 요구사항 분석 | brainstorming + ★advisor |
| | 2 | 상세 기획 | writing-plans |
| | 3 · 3.5 | UI/UX 시안 · 디자인 HTML | impeccable · gstack |
| **② 구현** (Do) | 4 | 업무 배분 + worktree 격리 | 레포별 do-er |
| | 🔒 | **API 계약 GATE** — shape 확정 전 구현 진입 금지 | vault `contracts/` + ★advisor |
| | 5 | 구현 + 회귀 가드 | subagent-driven (순차: 계약→공급측→소비측) |
| **③ 검증** (Check) | 6 | PR + 리뷰 + CI | `gh pr create` → 레포 CI (선택: `dw-pr-review.yml`) |
| | 7 · 7.5 | 기획↔구현 비교 · 디자인 QA | ★advisor · gstack |
| | 8 · 8.5 | 기능 QA · 회귀 스위트 | gstack · 대상 레포 테스트 전체 green |
| **④ 배포** (Act) | 9 | 머지 + 배포 | 레포별 규율(머지·배포 게이트는 사용자 동의) |

★ = advisor 에스컬레이션 · 🔒 = GATE (통과 전 다음 단계 금지)

### 핵심 규율

- **API 계약 먼저** — 교차 레포 작업은 계약(vault `contracts/`)을 확정한 뒤에야 구현 진입(shape 없이 ⑤ 금지).
- **순차 디스패치** — 계약 → 공급측(백엔드) → 소비측(앱/프론트) 순서. 병렬 금지(디렉토리 상이 시 계약 합의 후만).
- **회귀 2지점** — ⑤ 사고 fix 는 실패 테스트(RED) 먼저 · ⑧.5 배포 전 전체 테스트 green.
- **완료 게이트** — 대상 레포의 `.claude/dw-checks.json` 로 검증. **green 전 완료 선언 금지.**
- **머지·배포 게이트** — 마이그레이션·시크릿·권한·데이터 손실 변경은 **사용자 동의**.

> 이 워크플로우는 외부 스킬(superpowers·impeccable·gstack)을 호출합니다 — 미설치 시 그 자리에서
> 안내·설치(자가치유, 아래 〈외부 의존〉). 각 단계의 상세·게이트는 `/denver-workflow` 실행이 안내합니다.

---

## vault 에 무엇을 어디에 두나

지식 폴더(vault)는 두 축으로 나뉩니다. **폴더는 사람이 보기 좋으라고 나눈 것이고, 실제 라우팅은
각 노트의 `type`(frontmatter)으로 합니다** — 그래서 노트를 다른 폴더에 둬도 컴파일은 정확합니다.

### 축 B — 운영체계 `governance/` ("어떻게 일하나", 프로젝트 무관, 컴파일됨)

| 폴더 | 용도 | type | 컴파일 |
|---|---|---|---|
| `governance/_skills/` | scope 묶음 정의(skill-manifest) | `skill-manifest` | ✅ |
| `governance/rules/` | **강제 규칙**("법") — 검증자(`enforced-by`) 필수 | `rule` | ✅ stable |
| `governance/guidance/` | 작업 규율 — 공유 원칙(강제 게이트는 아님) | `guidance` | ✅ stable |
| `governance/procedures/` | 재사용 절차(playbook) — 에이전트 저작(draft→자동 승인) | `procedure` | ✅ stable |
| `governance/agents/` | 역할 정의(검증자·하네스) | `agent` | 서브에이전트로 설치 |

### 축 A — 프로젝트 지식 `project/` ("무엇을 만들/합의/배웠나", LIVE · 비컴파일)

LIVE = 승인 게이트 없이 **즉시 저장·검색**됩니다(읽기가 승인 상태와 무관하므로).

| 폴더 | 용도 | type | 완료 처리 |
|---|---|---|---|
| `project/memory/` | 에이전트 학습(비자명한 것만) | `memory` | — |
| `project/contracts/` | 백엔드↔앱 등 인터페이스 계약(SSOT) | `contract` | `dw_resolve` → archive |
| `project/specs/` | 계획·스펙·설계(worktree 휘발 방지) | `spec` | `dw_resolve` → archive |
| `project/backlog/` | **후속·할 일**(범위 밖 — repo 에 BACKLOG 파일 만들지 말고 여기) | `backlog` | `dw_resolve` → archive |
| `project/reference/` | **스냅샷형 참조**(DB 스키마·API 인덱스·아키텍처 — "현재 상태 추출") | `reference` | 재추출로 교체(완료 없음) |
| `project/decisions/` | ADR(아키텍처 결정 기록) — append-only | `decision` | — |
| `project/repo-map.md` | 멀티레포 라우팅 토폴로지(예외 — digest 로 주입) | `repo-map` | — |

> **backlog vs reference**: backlog 는 "나중에 할 일"(완료되면 archive), reference 는 "지금 시스템이
> 이렇게 생겼다"의 캡처(완료 개념 없음 — 낡으면 새로 추출해 **교체**). `project/` 는 사적 데이터라
> 공개 플러그인 seed 에 **절대 포함하지 않습니다**.

---

## vault 지식 도구 — MCP `dw-vault` (11개)

vault 를 MCP 서버로 노출합니다. 에이전트는 raw 파일이 아니라 **타입별 도구**로 읽고 씁니다(잘못된
형식이 원천 차단). 쓰기 도구엔 status 파라미터가 없습니다 — LIVE 는 즉시 stable, OBEY 만 draft 제안.

| 구분 | 도구 | 설명 |
|---|---|---|
| **읽기** | `dw_search(query)` · `dw_read(name)` · `dw_list(type?)` | 검색 · 원문 열기 · 목록 |
| **쓰기 · LIVE** (즉시 사용) | `dw_write_memory` | 학습 기록 |
| | `dw_write_backlog` | 후속·할 일 |
| | `dw_write_reference` | 현재 상태 스냅샷(같은 title 재호출 시 덮어써 교체) |
| | `dw_write_contract` | 계약 — `signoff`(pending\|agreed) · `blocking`(blocking\|non-blocking) 명시 |
| | `dw_write_spec` | 계획·스펙·설계 |
| **쓰기 · OBEY** (자동 승인) | `dw_write_procedure` · `dw_propose_rule` | 절차 · 규칙 제안(draft→ratify) |
| **완료/폐기** | `dw_resolve(name, resolution)` | backlog·spec·contract 를 `archive/` 로 이동(완료 표시). memory·decision·**reference 는 대상 아님** |

> `status`(비준상태)로는 완료/미완료를 못 나눕니다 — 그래서 완료는 **archive 이동**(`dw_resolve`)으로
> 표현합니다. 활성 목록(dw_search·dw_list)엔 미완료만 남고, 완료분은 경로로 직접 `dw_read` 하면 이력이 남습니다.

등록은 자동입니다 — `plugin.json` 의 `mcpServers.dw-vault` 가 플러그인 켜진 모든 세션에
`plugin:denver-workflow:dw-vault`(도구 `mcp__plugin_denver-workflow_dw-vault__*`)로 제공합니다.
계정마다 `claude mcp add` 하던 수동 등록이 불필요합니다. (도구는 **세션 시작 시 로드** — 플러그인
갱신 후엔 새 세션을 여세요.)

---

## 선택 기능

### GitHub Actions Claude PR 리뷰어 — `/dw-ci-review`

PR 이 열리거나 갱신되면 **Claude 가 PR 브랜치를 받아 실제 코드를 읽고 리뷰**해, 인라인 코멘트 +
최종 요약(합격/불합격 판정)을 남깁니다. 불합격이면 검사(`review`)가 실패 → 브랜치 보호 규칙에 넣으면
리뷰 통과 전 머지를 막습니다. **저장소별 옵인**입니다.

- 리뷰 기준은 특정 언어에 묶이지 않습니다 — 리뷰어가 그 저장소에 커밋된 거버넌스(`.claude/skills`·
  `.claude/dw-checks.json`·`CLAUDE.md`)를 발견해 그 기준으로 리뷰하고, 없으면 일반 시니어 원칙으로.
- 인증은 **Claude Pro/Max OAuth 토큰**(`CLAUDE_CODE_OAUTH_TOKEN` — 별도 API 과금 없이 구독으로).
- 설치: `/dw-ci-review`(미리보기 → 적용). 이후 사람 작업(토큰 시크릿 등록·커밋·브랜치 보호)을 커맨드가
  안내합니다. 템플릿: `assets/gh-workflows/dw-pr-review.yml`.
- verdict 게이트는 위조 방지(코멘트 작성자 검증)·stale 코멘트 차단·응답 부재 시 안전 FAIL 을 갖춥니다.

### graphify 시멘틱 그래프 (MCP)

코드·지식을 그래프로 인덱싱하는 외부 도구 `graphify` 가 있으면, 문자열 매칭인 `dw_search` 대신
**관계·경로 기반 탐색**을 씁니다. 옵인이라 구축한 사용자만 켭니다(미구축 환경엔 무영향).

- `/dw-setup` 옵인 단계가 graphify 를 감지하면 **프로젝트별 `.mcp.json`** 에 등록(헬퍼:
  `_build/dw-graphify-register.py`). 전역이 아니라 프로젝트별이라 모든 세션에 강요하지 않습니다.
- **지식**은 vault 기본 그래프, **특정 레포 코드**는 `project_path=<repo 절대경로>` 로 조회.
- guidance `graphify-search`(세션 상시 주입)가 "탐색은 graphify 우선, 코드 구조는 graphify **MCP**
  (raw grep·CLI 아님), 없으면 `dw_search` 폴백"을 지시합니다.

---

## 어떻게 강제되나 (거버넌스 하네스)

아래 레이어들은 그 자체로는 *권고*입니다("안다"이지 "못 어긴다"가 아님). **`dw-governed` 하네스
에이전트**가 이들을 *강제 루프*로 묶습니다: 규칙 pull → 작업 → 결정론 검사 → 검증자 호출 →
**통과까지 루프** → 완료 게이트. 프로젝트 `settings.local.json` 에 `"agent": "dw-governed"` 를 두면
모든 세션이 하네스로 시작합니다(항상 강제).

- **세션 주입**(SessionStart 훅) — 다이제스트(항상-적용 지침 + 강제 규칙 + 지식 인덱스)를 세션
  시작 시 컨텍스트에 주입(`🔒` 표시). CC 스킬 body 는 자동 로드되지 않으므로 이게 규칙·지식을 세션에 닿게 하는 실제 경로.
- **자동 비준**(`make ratify`, 스케줄) — draft 규칙·절차를 결정론 검증(스키마·검증자 실재·check 패턴을
  실제 코드에 돌려 오탐 0)해 안전분만 자동 stable·컴파일·설치. 판단 필요분만 `dw-ratifier`(LLM).
- **결정론 린터**(PostToolUse) — 규칙의 `check-deny`/`check-require` → `.claude/dw-checks.json` +
  `dw-lint.py`. 위반을 피드백(차단 아님, self-correct 유도).
- **worktree 가드**(PreToolUse, `Agent|Task`) — 격리 없이 파일 변경 에이전트를 spawn 하면 `ask`(공유 체크아웃 오염 방지).
- **vault 가드 / 산출물 가드**(PostToolUse) — raw `.md` frontmatter 계약 검사 + durable 문서·백로그를 vault 로 유도.
- **graphify 게이트**(PreToolUse, `dw_search`·`Grep`) — graphify 등록 세션이면 그래프 우선 탐색을 리마인드.
- **서브에이전트**(판단) — `enforced-by` 가 참조하는 검증자(security-qa·code-review 등)만 설치.

> 오탐 방지: 모든 검사는 `check-glob` 로 파일형 한정 + `check-exclude` 로 생성물·테스트·정본 파일 제외.
> grep 이 못 잡는 구조 규칙은 서브에이전트 리뷰가 담당합니다.

---

## 설정·운영

### 무엇이 설치되나

이 repo 자체가 플러그인입니다(`.claude-plugin/plugin.json`·`hooks/`·`commands/`). 한 번에 **MCP(dw-vault)
+ 거버넌스 하네스·검증자 에이전트 + 훅(린터·vault/산출물 가드·worktree 가드·세션 주입·graphify 게이트)
+ 슬래시 커맨드**가 설치됩니다. 단, **프로젝트별 스킬·검사·다이제스트는 `/dw-install`**(또는
`make install-project`)로 생성합니다 — 플러그인은 엔진, 프로젝트별 컴파일은 별도.

### vault 위치

vault 콘텐츠는 이 repo 가 아니라 **별도 폴더**(기본 `~/denver-workflow-vault`)에 있습니다. 사람은
Obsidian 으로 열어 편집, 에이전트는 MCP 로 read/write.

- 해석 순서: `DW_VAULT_DIR`(env, 존재하는 폴더) > `~/denver-workflow-vault`(규약) > 에러(폴더 없으면 서버 미기동).
- 커스텀 위치는 CC 시작 전 `export DW_VAULT_DIR="$HOME/My Vaults/denver"`.
- `make build|install-project|ratify` 는 **이 워크스페이스에서** 실행하되 `VAULT_DIR` 로 그 vault 를 읽습니다.

### advisor 모델 — Opus 4.8 권장

11단계의 ★advisor 에스컬레이션은 CC 빌트인 advisor(강한 리뷰어 모델)를 씁니다. 플러그인이 자동
설정할 수 없어 한 번 설정합니다: 세션에서 `/advisor opus`(→ `~/.claude/settings.json` 저장), 또는
`{ "advisorModel": "claude-opus-4-8" }`. (Anthropic API 필요, CC v2.1.98+.)

### 외부 의존 — `/dw-setup` 이 대신 설치

Denver 는 자기 영역(SSOT·거버넌스·MCP·가드·하네스)만 번들합니다. do-er 워크플로우가 호출하는 외부
스킬은 **사용자가 직접 설치**합니다(복사본 번들 금지 — 중복·라이선스·버전 드리프트 회피). 미설치가
발견되면 그 자리에서 설치(자가치유).

| 의존 | 용도 | 설치 |
|---|---|---|
| **Obsidian** (필수) | vault 편집 | https://obsidian.md/download · macOS `brew install --cask obsidian` |
| **superpowers** (권장) | brainstorming·writing-plans·TDD(①②④⑤) | `claude plugin install superpowers@claude-plugins-official` |
| **impeccable** (UI 시 필수) | 프론트 디자인 critique(③) | `claude plugin install impeccable@impeccable` |
| **gstack** (디자인/QA 권장) | design·browse·qa(③③.5⑦.5⑧) | `git clone --depth 1 https://github.com/garrytan/gstack.git ~/.claude/skills/gstack && cd ~/.claude/skills/gstack && ./setup` |

### 빌드·헬스체크

```bash
make build      # vault 컴파일 → .claude/skills
make dry-run    # 쓰기 없이 검증/요약 (CI: 경고도 에러)
make doctor     # 콜드스타트 헬스체크 (venv·컴파일러·MCP·설치 상태)
make ratify     # (스케줄 권장) draft 자동 비준 → compile+install
make review     # 판단 필요 큐 + 헬스체크
make scaffold-vault           # 빈 vault 에 제네릭 seed 복사(no-clobber)
make update-seed              # live vault 의 제네릭 분을 _seed 로 갱신(사적 데이터 제외)
make clean  /  make distclean # 산출물 제거 / 산출물+.venv 제거
```

`pyyaml`·`mcp` 만 외부 의존이며, `make` 가 프로젝트-로컬 `.venv` 에 자동 설치합니다(PEP 668 안전).

### 대상 프로젝트에 설치 (멀티레포)

`/dw-install`(또는 `make install-project`)이 프로젝트 `.claude/` 에 **관련 scope 스킬 + 결정론 검사 +
훅 + 서브에이전트 + 세션 다이제스트**를 설치합니다(계약은 vault 단일 SSOT 라 미러하지 않음).

```bash
make install-project P=/절대/경로/프로젝트                    # 전체 scope union
make install-project P=/절대/경로/프로젝트 SCOPES=engineering  # scope 지정(콤마 구분)
```

멀티레포는 레포 맵(vault `project/repo-map.md`)의 각 경로에 순회 실행 — `/dw-install` 은 세션 digest 의
레포 맵을 읽어 자동 순회합니다. 대상 repo 의 **기존 스킬·에이전트는 보존**됩니다(우리 매니페스트
기준으로만 정리). 설치 산출물은 **직접 편집 금지** — vault 를 고친 뒤 재설치.

### 콜드스타트

| Tier | 상황 | 할 일 |
|---|---|---|
| **1** | 매 새 세션(평상시) | 없음 — SessionStart 훅이 다이제스트 주입, 스킬·훅·에이전트·MCP 자동 로드. 점검 `claude mcp list \| grep dw-vault` |
| **2** | 재부팅 후 | 동일(절대경로 + `.venv` 영속). `make doctor` |
| **3** | 새 머신/재클론 | `/dw-setup` 한 번(의존 설치·vault scaffold·프로젝트 설치) |

---

## Frontmatter 계약 (vault 저작용)

노트 상단 frontmatter 가 사람(폴더)과 기계(컴파일러)를 잇는 유일한 계약입니다.

| 필드 | 값 | 동작 |
|---|---|---|
| `type` | `rule`·`guidance`·`procedure`·`memory`·`contract`·`spec`·`backlog`·`reference`·`decision`·`skill-manifest`·`agent` | 라우팅 시작점 |
| `scope` | kebab-case 도메인 | skill 묶음 단위 |
| `status` | `draft`·`stable`·`deprecated` | **`stable` 만 컴파일·강제** |
| `compiles-to` | `skill` | 있어야 스킬 포함 |
| `enforced-by` | 검증자 id | rule 필수(`agents/` 에 없으면 경고) |
| `check-deny`·`check-require` | 정규식/목록 | 린터 위반 판정(deny=있으면, require=없으면) |
| `check-glob`·`check-exclude`·`check-hint` | glob·문구 | 검사 대상 한정(**glob 없으면 검사 비활성**)·수정 안내 |

**type 별 필수 필드**
- `rule`: `type scope status enforced-by compiles-to`
- `guidance`·`procedure`: `type scope status compiles-to`
- `skill-manifest`: `type scope skill-name skill-description`
- `memory`·`contract`·`spec`·`backlog`·`reference`: `type status` (+`title`) · `agent`·`decision`: `type`

**Obsidian 저작**: 이 폴더 자체가 볼트(`.obsidian/` 포함). 명령 팔레트 → *Insert template* 로 frontmatter
를 채워 시작. 위키링크 `[[노트]]` 는 컴파일러가 평탄화. 저작 후 `make build`/`/dw-install`.

> seed 는 제네릭 축-B 만 배포합니다(엔지니어링 규율 + 검증자·하네스). 프로젝트 특화 규칙·계약·스펙은
> 사용자가 작성하며 공개 플러그인엔 포함되지 않습니다.

---

## 더 깊이

- **설계 원리·불변식(9개)·아키텍처 근거** → [BOOTSTRAP.md](./BOOTSTRAP.md)
- **개발·빌드 규약** → [CLAUDE.md](./CLAUDE.md)
- **변경 이력** → [CHANGELOG.md](./CHANGELOG.md)
