# AI-Native Workflow — 설계 & 아키텍처

> 원래는 "Obsidian vault → `.claude/skills` 일방향 컴파일러" 부트스트랩 브리프였다.
> 이후 **양방향 살아있는 SSOT**(에이전트가 직접 읽고/쓰고/갱신)로 진화했다.
> 이 문서는 *무엇을, 왜*(설계·불변식)를, README 는 *어떻게*(운영·명령)를 다룬다.

## 목표 (한 문장)

이 repo 의 **Obsidian vault 를 단일 진실 원천(SSOT)** 으로 두고 — 규칙·원칙·메모리·계약을
한 곳에 모아 — 에이전트가 그 SSOT 를 **읽고 복종하고, 학습을 되써서 갱신**하게 한다.

## 아키텍처 — 양방향 살아있는 SSOT

```
            사람(저작·비준)
                 │
                 ▼
        ┌──────────────────  Obsidian vault (SSOT)  ──────────────────┐
        │  rules · guidance   →  [컴파일] → .claude/skills  (복종, stable만) │
        │  memory · contracts →  라이브(비컴파일)                            │  ← 에이전트가
        └──────────────┬───────────────────────────────┬───────────────┘     read/write(draft)
                       │ make install                  │ ssot-vault MCP 서버
            프로젝트 스킬·검사·훅·에이전트       (8 도구; LIVE stable 직행·OBEY draft)
                       │                               │
                       ▼                               ▼
                 대상 프로젝트 세션          ·  Claude Code (구독)
```

- **사람은 저작**한다(주로 규칙·원칙). **에이전트는 컴파일된 규칙에 복종**하고, 학습·계약·규칙을 기록·제안한다.
- **비준은 자동**이다 — LIVE(memory/contract/spec)는 게이트가 없고, OBEY(rule/guidance/procedure)는
  `ssot-ratify`(결정론) + `ssot-ratifier`(LLM 판단)가 비준한다. **사람은 더는 비준 바틀넥이 아니다.**
- 사람·기계를 잇는 유일한 계약면은 **frontmatter** 다.
- vault = 소스. `.claude/skills` = 빌드 산출물(소스 → 바이너리). **산출물 직접 편집 금지.**

## 두 경로 — 복종 vs 학습·협업

| 경로 | 콘텐츠 | 흐름 | 컴파일? |
|---|---|---|---|
| **복종** | `rules` · `guidance` · `procedures` | 저작/제안 → 자동 비준 → 스킬 → 에이전트 복종 | ✅ `stable` 만 |
| **학습** | `memory` | 에이전트가 stable 기록(게이트 없음) (자동 캡처도 vault 로 funnel) | ❌ 라이브 |
| **협업** | `contracts` | 백엔드↔앱 에이전트 read/write, stable (게이트 없음) | ❌ 라이브 |
| **설계** | `specs` | 계획·스펙·설계, 에이전트 작성, stable (worktree 휘발 방지) | ❌ 라이브 |

핵심 교정: 메모리·계약은 **컴파일하지 않는다**. 에이전트가 vault 를 라이브로 읽고 쓴다.
읽기 도구는 status 를 안 거르므로 **LIVE 의 draft↔stable 구분은 무의미** — 그래서 MCP 가 LIVE 를
바로 stable 로 쓴다(비준 게이트 제거). `draft` 는 OBEY(컴파일·강제 대상)에서만 의미를 가지며,
`ssot-ratify` 가 안전성을 **경험적으로 검증**(check 패턴을 실제 코드에 돌려 오탐 0)한 뒤 자동 승격한다.

## 절대 불변식 (하나라도 깨지면 잘못된 것)

1. **폴더는 사람용, frontmatter 는 기계용 라우팅.** 컴파일러는 폴더로 분기하지 않는다 —
   vault 전체를 `*.md` 로 훑고 오직 frontmatter(`type`/`compiles-to`/`scope`)로 라우팅한다.
2. **컴파일은 순수·결정론적.** 같은 vault → 같은 산출물(정렬). 노트 삭제 → 산출물에서도 삭제.
3. **검증 불가 규칙은 규칙이 아니라 소망.** `type:rule` 은 반드시 `enforced-by` 를 가진다.
   `guidance`(작업 규율)는 강제 게이트가 아니므로 enforced-by 불요.
4. **ADR(`decisions/`)은 절대 컴파일되지 않는다.** 규칙은 "무엇을", ADR 은 "왜". 메모리는 에이전트에 안 내려간다.
5. **`scope` = skill 묶음/로드 단위.** 같은 scope 노트는 하나의 skill 로 합쳐진다.
6. **`status` = 컴파일·강제 게이트.** `stable` 만 컴파일된다. `draft`/`deprecated` 는 산출물에서 빠진다.
7. **skill 은 점진적 노출.** description 은 항상, body 는 관련될 때만 로드.
8. **사용자/테넌트 데이터 격리는 1급 규칙** — 검증자(`enforced-by: security-qa`)를 붙인다.
   (구현은 프로젝트마다 다르다.)
9. **비준은 자동, 강제 입법만 검증된다.** LIVE(memory/contract/spec)는 MCP가 stable 로 바로 쓴다
   (읽기가 status 무관 → 게이트 무의미). OBEY(rule/guidance/procedure)는 status:draft 로 제안되고,
   `ssot-ratify`(결정론: 스키마·enforced-by 실재·check 패턴 코드 0매치)가 **안전한 것만** 자동 stable
   승격한다. 판단 필요 건(check 가 기존 코드에 매치)만 `ssot-ratifier`(LLM)로 에스컬레이션 — 사람은 불요.
   **불변식의 핵심은 "사람 비준"이 아니라 "강제되는 규칙은 발효 전 경험적으로 검증된다"** 이다.

## 강제 — 능동 하네스 + 게이트 레이어

게이트 레이어(1-4)는 그 자체로 *권고*다 — 컴파일된 규칙은 ambient("안다"), 훅은 피드백,
서브에이전트는 on-demand. 협조에 의존하므로 "안다 ≠ 못 어긴다". 진짜 강제성은 **능동 하네스**에서 나온다.

**`ssot-governed` 하네스 에이전트**(`agents/ssot-governed.md`, `install: always`)가 게이트를
*빠져나갈 수 없는 루프*로 묶는다: 규칙 pull → 작업 → 결정론 검사 → 검증자 → **통과까지 루프** → 완료 게이트.
프로젝트 `settings.local.json` 의 `agent: ssot-governed` 로 모든 세션이 하네스로 시작한다(항상 강제).

게이트 레이어:
0. **자동 비준**(`make ratify`, 스케줄) — OBEY draft 를 결정론적으로 검증해 안전분 자동 stable·
   compile·install. 사람·수동 make 제거. 판단 필요 건만 `ssot-ratifier`(LLM)로 넘긴다.
1. **MCP 도구**(주 경로) — `ssot_write_*` 가 frontmatter 를 *구성*한다. LIVE 는 stable 직행,
   OBEY(rule/procedure)는 draft 제안(status 파라미터 없음 → validate-by-construction).
2. **결정론적 린터**(자동) — 규칙의 `check-deny`/`check-require` 를 PostToolUse 훅이 검사,
   위반을 `additionalContext` 로 피드백(차단이 아니라 self-correct 유도).
3. **vault 가드**(백스톱) — raw `.md` 직접 쓰기의 frontmatter 계약·draft 게이트 검사.
4. **서브에이전트**(판단) — grep 못 잡는 구조 규칙은 `enforced-by` 검증자(security-qa 등)가 리뷰.

**중대 교정 — 스킬 body 는 자동 로드되지 않는다.** CC 스킬은 progressive disclosure(불변식 7):
description 만 항상 컨텍스트에 있고, **body(규칙 전문·누적 지식 인덱스)는 스킬 활성화 시에만 로드**된다.
세션이 실제로 관측됨 — 스킬 내용을 묻자 컨텍스트에 없어 파일을 직접 `Read` 했다. 이것이 "컴파일된
가이던스를 세션이 무시"한 **근본 원인**이다: 규칙·지식이 body 에만 있어 자동으로 닿지 못했다.
**해결 — SessionStart 다이제스트 주입(레이어 5).** `make install` 이 프로젝트별 다이제스트
(`.claude/ssot-session-digest.md`: 항상-적용 guidance + 강제 규칙 목록 + 누적 지식 인덱스)를 만들고,
`ssot-session-context.py`(SessionStart 훅)가 이를 **세션 시작 시 컨텍스트에 직접 주입**한다 —
additionalContext 는 body 와 달리 항상 주입된다(bkit 등 검증된 메커니즘). 전문은 `ssot_read`/스킬로 pull.

## MCP 게이트웨이 — `ssot-vault`

vault 를 stdio MCP 서버(`_build/ssot-mcp-server.py`)로 노출 → Claude Code(및 모든 MCP
클라이언트)가 타입 도구로 접근. 쓰기 도구에 status 파라미터 없음(validate-by-construction):

- **읽기**: `ssot_search` · `ssot_read` · `ssot_list` (status 무관 — draft·stable 모두 검색)
- **쓰기·LIVE(stable 직행)**: `ssot_write_memory` · `ssot_write_contract` · `ssot_write_spec`
- **쓰기·OBEY(draft 제안 → ssot-ratify 자동 비준)**: `ssot_write_procedure` · `ssot_propose_rule`

메모리는 **CC auto-memory(`autoMemoryDirectory`)도 vault 로 funnel**되어, 자동 캡처·큐레이션
모두 vault 단일 SSOT 로 모인다(가드·도구가 CC 포맷·vault 포맷 둘 다 수용).

## frontmatter 계약

type 별 필수 필드·검사 필드(`check-*`)·라우팅 규칙은 **README 의 "Frontmatter 계약"** 참조.
요지: `type` 이 라우팅 시작점, `compiles-to: skill`+`status: stable` 이어야 스킬에 포함,
`rule` 은 `enforced-by` 필수.

## 진화 기록 (초기 브리프 → 현재)

- **초기**: vault → `.claude/skills` 일방향 컴파일러 + auth 샘플(수용 기준 통과).
- **확장**: 실제 프로젝트 분석 → 규칙·검증자·결정론 린터.
- **양방향**: 메모리·계약을 vault 라이브 read/write 로(비컴파일). draft 게이트.
- **게이트웨이**: `ssot-vault` MCP 서버(8 도구) — CC 가 직접 읽고/쓰고/검색(라이브 검증 완료).
- **일원화**: 계약 vault 단일 SSOT(repo 미러 제거), bkit·CC auto-memory 를 vault 로 수렴.
- **MCP 선언 일원화**: MCP 를 `plugin.json` 의 `mcpServers` 에 단일 선언 — 플러그인이
  `plugin:denver-agent:ssot-vault`(도구 `mcp__plugin_denver-agent_ssot-vault__*`)로 자동 제공.
  루트 `.mcp.json` 의 bare 이중 등록은 제거(`{}`), roster 화이트리스트도 plugin prefix 로 정합.
  계정별 `claude mcp add`(legacy `make register-mcp`) 불요.
