# Denver AI Workflow

**팀의 지식(규칙, 계약, 학습 내용)을 하나의 Vault에 통합하고, Claude Code 에이전트가 이를 읽고, 준수하며, 새롭게 학습한 내용을 지속적으로 반영하도록 하는 거버넌스 시스템입니다.** 하나의 지식 폴더를 팀과 에이전트가 함께 사용하는 **단일 진실 원천(SSOT, Single Source of Truth)**으로 삼습니다.

> **💡 비개발자도 바로 사용할 수 있습니다.** 아래 [🚀 빠른 시작](#-빠른-시작-3단계) 3단계만으로 준비가 완료됩니다. 하위의 상세 내용은 필요할 때 참조하십시오.

---

## 📌 개요

프로젝트가 확장될수록 협업 방식, API 계약, 장애 대응 이력과 같은 팀의 지식은 여러 곳에 흩어지기 쉽습니다. Denver는 이러한 지식을 **Obsidian** Vault 하나에 통합하여 관리합니다.

이후 Claude Code는 모든 작업 세션에서 **기존 규칙을 자동으로 준수(OBEY)** 하고, 새롭게 학습한 컨텍스트(LIVE)를 Vault에 실시간으로 기록합니다. 이를 통해 사람이 지식을 직접 검토하거나 복사해 붙여 넣고 승인하는 과정을 없애고, 검증·컴파일·컨텍스트 주입까지 전 과정을 자동화합니다.

```
               사람 (규칙 및 지식 저작)
                         │
        Obsidian Vault (SSOT · 팀 지식 폴더)
           ├── OBEY (규칙·지침·절차) ── dw-ratify(자동 검증·승인) → [컴파일] → .claude/skills
           └── LIVE (학습·계약·스펙) ── MCP 서버가 실시간 저장 ◀── 에이전트 읽기/쓰기
                         │                                             │ dw-vault MCP (11개 도구)
                         ▼                                             ▼
 ───────────────────────────────────────────────────────────────────────────────
 세션 시작 시점: 훅(Hook)이 "필수 준수 지침 + 강제 규칙 + 지식 인덱스"를 컨텍스트에 자동 주입
                         │
                         ▼
                대상 프로젝트 세션 ◀──────▶ Claude Code (규율 강제 준수)
```

> ℹ️ 이 문서는 **사용법 및 운영 가이드**입니다. 설계 원리 및 불변식은 [BOOTSTRAP.md](./BOOTSTRAP.md)을 참조하십시오.

---

## 🚀 빠른 시작 (3단계)

1. **플러그인 설치** — 터미널에서 Claude Code를 실행하고 아래 명령어를 순서대로 입력합니다:
   ```bash
   claude plugin marketplace add https://github.com/denvernext80/Denver-Workflow
   claude plugin install denver-workflow@denver-workflow
   ```
2. **초기 설정** — 세션에서 `/dw-setup`을 입력합니다. 설정 도우미가 필수 프로그램(Obsidian 등) 설치, 지식 폴더(Vault) 준비, 프로젝트 연결까지 자동으로 안내합니다 (신규·기존·멀티레포 프로젝트 유형 자동 판별).
3. **사용 시작** — `/denver-workflow`를 입력합니다. 요구사항 분석부터 최종 배포까지의 전체 기능 개발 과정을 11단계로 자동 안내합니다.

> 💡 오타 수정, 한 줄짜리 버그 픽스, 단순 문서 수정 등 단발성 작업은 11단계를 생략하고 바로 Git 흐름(Branch/PR)으로 진행합니다. **신규 기능 개발 등 전체 사이클 검증이 필요할 때만 적용합니다.**

---

## 💻 슬래시 커맨드 (Commands)

| 커맨드 | 설명 |
| --- | --- |
| `/dw-setup` | **초기 설정 도우미** — 필수 도구 설치, Vault 준비 및 프로젝트 연결 일괄 처리 |
| `/denver-workflow` | **기능 개발 풀사이클** — 요구사항 정의부터 배포까지의 11단계 프로세스 가동 (멀티레포 대응) |
| `/dw-install` | Vault의 최신 상태(규칙, 검사, 에이전트 설정, 다이제스트)를 타깃 프로젝트에 동기화/갱신 |
| `/dw-build` | Vault 내용을 컴파일하여 `.claude/skills`로 빌드 (Strict 검증 모드 적용) |
| `/dw-ratify` | Draft 상태의 규칙/절차를 **자동 검증 및 승인**하여 Stable 상태로 빌드·설치 (사람의 개입 불요) |
| `/dw-review` | 자동 승인이 보류된 수동 검토용 큐(Queue) 확인 및 시스템 헬스체크 수행 |
| `/dw-scope` | 플러그인 활성화 범위 설정 (사용자 전역 vs 현재 프로젝트 한정) |
| `/dw-ci-review` | **(선택) GitHub PR 자동 리뷰어** 설치 — PR 생성 시 Claude가 브랜치 단위 코드 리뷰 수행 |
| `/dw-api-spec` | **API 명세 점검·갱신** — 코드와 vault 명세가 어긋났는지 확인(인자 없음), `재추출`·`<도메인>` 으로 다시 훑기 |
| `/dw-batch-spec` | **배치·크론 명세 점검·갱신** — 실제 도는 정기 실행과 명세 대조(인자 없음), `재추출`·`<그룹>` 으로 다시 훑기 |

---

## 🔄 기능 개발 풀사이클 — `/denver-workflow`

신규 기능을 **요구사항 정의부터 배포**까지 안전하고 일관된 절차로 수행하는 멀티 에이전트 워크플로우입니다.

다중 저장소(멀티레포) 환경에서는 변경 범위(Frontend, Backend, QA 등)를 자동으로 분석하여 적절한 저장소와 담당 에이전트(**Do-er**)로 작업을 분기(Dispatch)합니다. 작업 진행 중 교착 상태가 발생하거나 추가 검토가 필요한 경우에는 상위 리뷰어 모델인 Advisor로 에스컬레이션(Escalation)하여 검토를 수행합니다.

* **최초 1회 준비 단계(0단계):** 멀티레포 환경에서는 대화형 인터페이스를 통해 저장소와 담당 에이전트를 매핑하는 **저장소 지도(Repo-Map)**를 생성합니다. 한 번만 구성하면 이후에는 추가 설정 없이 모든 워크플로우에서 자동으로 활용됩니다.


### 🛠️ 5 단계 흐름 (설계 ➔ 분기·계약 ➔ 구현 ➔ 검증 ➔ 배포)

| 국면 | 단계 | 세부 단계 | 도구 (스킬 / 에이전트) |
| --- | --- | --- | --- |
| **① 설계** | 1 | 요구사항 분석 | `brainstorming` + ★ `advisor` |
|  | 2 | 상세 기획 | `writing-plans` |
|  | 3 · 3.5 | UI/UX 시안 · 디자인 HTML | `impeccable` · `gstack` |
| **② 분기·계약** 🔒 | 4 | 업무 배분 + Worktree 격리 | 저장소별 `do-er` |
|  | 🔒 | **API 계약 GATE** (인터페이스 확정 전 구현 진입 금지) | Vault 내 `contracts/` + ★ `advisor` |
| **③ 구현** | 5 | 구현 및 회귀 방지 가드 구동 | `subagent-driven` (순차: 계약 ➔ 공급측 ➔ 소비측) |
| **④ 검증** | 6 | PR 생성 + 리뷰 + CI 빌드 | `gh pr create` ➔ 레포 CI (선택: `dw-pr-review.yml`) |
|  | 7 · 7.5 | 기획-구현 싱크 비교 · 디자인 QA | ★ `advisor` · `gstack` |
|  | 8 · 8.5 | 기능 QA · 회귀 테스트 스위트 구동 | `gstack` ➔ 대상 저장소 테스트 전체 Green 통과 |
| **⑤ 배포** | 9 | 머지(Merge) + 프로덕션 배포 | 레포지토리별 규율 준수 (**머지·배포 관문은 사용자 동의 필수**) |

> 📌 **표기 규약**
> * ★ = `advisor` 에스컬레이션 지점
> * 🔒 = **GATE** (조건 충족 및 통과 전에는 다음 단계 진입 절대 불가)


### 🚨 핵심 개발 규율 (Core Disciplines)

* **API 계약 우선 원칙 (Contract First):** 교차 레포지토리 작업 시 Vault의 `contracts/`에 인터페이스 계약 스펙이 확정되어야만 구현(5단계) 시작이 가능합니다. (인터페이스 정의 없는 5단계 진입 금지)
* **순차적 디스패치:** 구현 작업은 합의된 스펙을 바탕으로 **[계약] ➔ [공급측 (Backend)] ➔ [소비측 (Frontend/App)]** 순서로 순차 실행됩니다. 상호 디렉토리가 상이한 상태에서의 병렬 작업을 금지합니다.
* **회귀 테스트 2지점 방어:** 5단계 결함 수정 시에는 실패하는 테스트(RED)를 먼저 작성해야 하며, 배포 전(8.5단계)에는 전체 테스트 스위트가 통과(GREEN)되어야 합니다.
* **완료 게이트 (Completion Gate):** 대상 레포지토리의 `.claude/dw-checks.json` 검증 결과가 모두 **Green 상태가 되기 전에는 임의로 완료를 선언할 수 없습니다.**
* **머지·배포 게이트:** 데이터베이스 마이그레이션, 시크릿 키 변경, 인프라 권한 변경, 데이터 손실 위험이 있는 변경 사안은 **반드시 사용자의 명시적 승인**을 거쳐야 합니다.

---

## 📂 Vault 지식 구조 및 관리 원칙

지식 폴더(Vault)는 역할에 따라 두 가지 축으로 구성됩니다. **폴더 분류는 작업자의 가독성을 위한 것이며, 실제 에이전트 라우팅은 노트 상단 Frontmatter에 명시된 `type`을 기준으로 컴파일러가 수행합니다** 따라서 노트를 다른 폴더로 이동시켜도 컴파일 결과에는 영향을 주지 않습니다.

### B — 운영체계 `governance/` ("어떻게 일하는가" | 프로젝트 무관 | 컴파일 대상)

| 폴더 경로 | 용도 및 설명 | `type` | 컴파일 및 적용 |
| --- | --- | --- | --- |
| `governance/_skills/` | 스킬 범위 및 매니페스트 정의 | `skill-manifest` | ✅ |
| `governance/rules/` | **강제 규칙 (법률)** — 검증자(`enforced-by`) 필드 필수 명시 | `rule` | ✅ Stable만 적용 |
| `governance/guidance/` | 작업 규율 및 공유 원칙 (하드 게이트는 아님) | `guidance` | ✅ Stable만 적용 |
| `governance/procedures/` | 재사용 가능한 절차(Playbook) — 에이전트 자동 저작 지원 | `procedure` | ✅ Stable만 적용 |
| `governance/agents/` | 역할 정의 (보안·리뷰 전담 서브에이전트 및 하네스) | `agent` | 서브에이전트로 설치 |

### A — 프로젝트 지식 `project/` ("무엇을 만드는가" | 실시간 변동 | LIVE)

**LIVE 영역은 별도의 비준 게이트 없이 에이전트에 의해 즉시 저장되고 검색됩니다.**

| 폴더 경로 | 용도 및 설명 | `type` | 완료 처리 방식 |
| --- | --- | --- | --- |
| `project/memory/` | 작업 도중 축적된 에이전트의 비자명한 학습 내용 기록 | `memory` | 영구 누적 |
| `project/contracts/` | 백엔드 ↔ 앱/프론트엔드 간의 인터페이스 계약 (SSOT) | `contract` | 완료 시 `dw_resolve` ➔ archive |
| `project/specs/` | 기능 계획, 스펙 및 아키텍처 설계 문서 (휘발 방지) | `spec` | 완료 시 `dw_resolve` ➔ archive |
| `project/backlog/` | 후속 작업 및 To-Do (코드 내 BACKLOG 주석 대신 여기에 관리) | `backlog` | 완료 시 `dw_resolve` ➔ archive |
| `project/reference/` | 현재 시스템 스냅샷 (**API 명세 3종**, **배치·크론 명세 3종**, DB 스키마 등 추출 데이터) | `reference` | 최신 데이터 재추출 시 덮어쓰기 (단 `— 변경 이력` 노트는 append-only 누적) |
| `project/decisions/` | 아키텍처 결정 기록 (ADR) | `decision` | Append-only (누적) |
| `project/repo-map.md` | 멀티레포 라우팅 토폴로지 구조 정의 | `repo-map` | 다이제스트로 자동 주입 |

> ⚠️ **정리 및 보안 원칙**
> * `backlog`는 완료 시 archive 폴더로 이동하여 종결되지만, `reference`는 시스템의 현재 상태를 동기화하므로 완료 개념 없이 최신 데이터로 **교체**됩니다.
> * `project/` 하위 데이터는 비공개 도메인 자산이므로, 오픈소스 플러그인 Seed 배포본에 **절대 포함하지 않습니다.**

---

## 🛠️ Vault 지식 관리 도구 (MCP `dw-vault`)

Denver는 Vault를 MCP(Model Context Protocol) 서버 형태로 에이전트에 노출합니다. 에이전트는 원시 마크다운 파일을 직접 다루지 않고, 규격화된 **타입별 전용 도구**를 통해서만 읽고 씁니다. 포맷 오염을 원천 차단하기 위함입니다.

| 구분 | 도구 명칭 | 설명 |
| --- | --- | --- |
| **읽기 (Read)** | `dw_search(query)` <br> `dw_read(name)` <br> `dw_list(type?)` | 지식 검색 <br> 특정 노트 원문 조회 <br> 타입별 지식 목록 조회 |
| **쓰기 (Write) · LIVE** *(즉시 반영)* | `dw_write_memory` <br> `dw_write_backlog` <br> `dw_write_reference` <br> `dw_write_contract` <br> `dw_write_spec` | 실시간 에이전트 학습 내역 기록 <br> 후속 할 일 기록 <br> 시스템 스냅샷 기록 (동일 제목 호출 시 자동 덮어쓰기 교체) <br> 계약 기록 (`signoff` [pending\|agreed], `blocking` 여부 명시) <br> 기능 기획 및 설계서 기록 |
| **쓰기 (Write) · OBEY** *(검증 및 제안)* | `dw_write_procedure` <br> `dw_propose_rule` | 절차(Playbook) 및 규칙 제안 <br> *(작성 시 즉시 반영되지 않고 `draft` 상태로 대기)* |
| **종결 (Resolve)** | `dw_resolve(name, resolution)` | 완료된 backlog, spec, contract 노트를 `archive/` 폴더로 이동 처리 <br> *(※ memory, decision, reference는 이 도구의 대상이 아님)* |

> 💡 **자동 MCP 등록** — 에이전트 도구는 plugin.json에 정의된 설정을 기반으로, 플러그인이 활성화된 모든 세션에 자동으로 등록됩니다. 따라서 사용자별로 claude mcp add를 수동 실행할 필요가 없습니다. 도구는 세션 시작 시 로드되므로, 플러그인을 업데이트한 후에는 새 세션을 시작해 주세요.

---

## 🌟 선택 확장 기능

### 1. GitHub Actions 연동 Claude PR 리뷰어 (`/dw-ci-review`)

Pull Request가 생성되거나 업데이트되면, GitHub Actions가 자동으로 실행되며 **Claude가 PR 브랜치의 최신 상태를 체크아웃하여 정밀 코드 리뷰**를 수행합니다.

* 파일 단위의 인라인 코멘트를 남기고, 최종 요약(Pass/Fail 판정)을 제공합니다.
* Fail 판정 시 CI 체크가 실패하므로, 브랜치 보호 규칙(Branch Protection Rule)과 결합하여 품질 기준 미달 코드의 머지를 강제 차단할 수 있습니다.
* **저장소별 옵인(Opt-in) 방식**으로 동작합니다. 리뷰 기준은 특정 언어에 종속되지 않으며, 프로젝트 내에 커밋된 거버넌스 규칙(`.claude/skills`, `CLAUDE.md` 등)을 최우선 기준으로 삼습니다.
* **인증:** 별도의 API 과금 없이 사용자의 **Claude Pro/Max OAuth 토큰**(`CLAUDE_CODE_OAUTH_TOKEN`)을 활용합니다.
* **설치:** 세션에서 `/dw-ci-review` 입력 후 안내에 따라 시크릿 등록 및 워크플로우 템플릿(`assets/gh-workflows/dw-pr-review.yml`)을 커밋합니다.

### 2. Graphify 시맨틱 그래프 탐색 (MCP)

코드베이스와 지식 간의 관계를 그래프 구조로 인덱싱하는 외부 도구 **graphify**를 사용할 수 있는 경우, 기본 문자열 기반 검색인 dw_search 대신 **관계 및 탐색 경로 기반의 시맨틱 검색**을 우선 적용하도록 자동 전환됩니다.

* `/dw-setup` 실행 중 graphify 환경이 감지되면 프로젝트별 .mcp.json에 자동으로 등록됩니다. 전역 설정을 변경하지 않고, 프로젝트 단위로 독립적으로 구성됩니다.
* graphify가 설치되어 있지 않거나 정상적으로 응답하지 않는 경우에는 기존 dw_search로 자동 전환(Fallback)되어 기능을 계속 사용할 수 있습니다.

---

## 🔒 거버넌스 강제 메커니즘 (Governance Harness)

단순 권고 지침에 그치지 않도록, Denver는 **`dw-governed` 하네스 에이전트**를 통해 아래의 보호 레이어들을 결정론적 루프로 묶어 실행을 강제합니다. 프로젝트 `settings.local.json`에 `"agent": "dw-governed"` 설정을 추가하면 모든 세션이 하네스 제어하에 시작됩니다.

* **세션 다이제스트 주입 (SessionStart Hook):** 세션이 시작되는 즉시 상시 준수 지침, 강제 규칙, 지식 인덱스가 포함된 다이제스트(Digest) 컨텍스트를 에이전트 컨텍스트에 주입합니다. (`🔒` 표시) 이는 스킬 본문이 자동 로드되지 않는 Claude Code 환경에서 실제 규칙을 도달시키는 핵심 경로입니다.
* **자동 비준 루프 (`dw-ratify`):** 제안된 규칙과 절차(`draft`)들을 결정론적 검증 스크립트(스키마 일치, 검증자 실재 여부 등)로 자동 확인하여, 오탐이 없는 건에 한해 `stable` 상태로 자동 승격, 컴파일 및 설치합니다. 수동 판단이 필요한 케이스만 LLM 검증기(`dw-ratifier`) 큐로 이관합니다.
* **결정론적 린터 (PostToolUse Hook):** 지식 노트에 선언된 정적 규칙 위반 패턴(`check-deny`/`check-require`)을 실시간 검사하여 위반 발생 시 에이전트에게 즉각적인 피드백을 제공하고 자가 치유(Self-correct)를 유도합니다.
* **Worktree 오염 방지 가드 (PreToolUse Hook):** 변경 범위 격리(Worktree) 없이 공유 체크아웃 환경에서 다이렉트로 파일을 수정하려는 서브에이전트 스폰 시도를 감지하여 즉시 차단하고, 사용자 동의(`ask`)를 구합니다.
* **오탐 방지 장치:** 모든 정적 검사는 `check-glob`을 통해 지정된 파일 포맷으로 타깃을 한정하며, `check-exclude`를 통해 빌드 산출물이나 테스트 정본 파일 등은 검사 대상에서 제외합니다.
* **배치·크론 명세 하네스:** 정기 실행되는 작업(배치·크론)을 vault `project/reference/` 에 **현재 상태 + 변경 이력**으로 유지합니다. `/dw-setup` 최초 1회에 CI 스케줄·타이머 유닛·예약 잡·앱 스케줄러·크론 설치 스크립트를 전 표면으로 훑습니다. **API 와 달리 정본이 레포 밖(호스트 크론)에도 있어**, 레포 선언분과 호스트 설치분을 분리해 세고 확인하지 못한 호스트는 `미확인(최종 확인일·사유)` 으로 남깁니다 — 없다고 단정하지 않습니다. 호스트 설치분이 명세와 다르면 **임의로 맞추지 않고 사용자 판단을 받습니다**(무단 변경이 조용히 정본이 되는 것을 막습니다). 꺼진 잡도 `비활성` 상태와 사유로 남아 "이거 왜 꺼져 있죠?" 에 답할 수 있습니다. 점검은 `/dw-batch-spec`.
* **API 명세 하네스:** 프로젝트의 모든 API 를 vault `project/reference/` 에 **현재 상태 + 변경 이력**으로 유지합니다. `/dw-setup` 최초 1회에 기존 API 를 전수로 훑어 명세 3종(전체 인덱스 · 도메인별 상세 · 변경 이력)을 만들고, 이후 API 작업은 **인덱스를 읽는 것으로 시작해 명세 갱신으로 끝납니다**. 읽기 규율은 세션 다이제스트에 전문이 항상 주입되고(`api-spec-first`), 갱신 누락은 PR 리뷰에서 차단됩니다(`api-spec-sync-required`, enforced-by `code-review`). 명세가 코드와 벌어졌는지는 `/dw-api-spec` 으로 언제든 점검합니다. **삭제된 엔드포인트도 변경 이력에는 영구히 남아** "이 API 가 왜 없어졌나" 에 답할 수 있습니다.

---

## ⚙️ 설정 및 운영 가이드 (Ops)

### 1. 설치 구성 요소

이 레포지토리 자체가 하나의 플러그인 구조(`.claude-plugin/plugin.json`, `hooks/`, `commands/`)를 가집니다. 플러그인을 활성화하면 아래 요소들이 일괄 설치됩니다.

* **MCP 서버 (`dw-vault`)** + **거버넌스 하네스 및 검증자 에이전트**
* **런타임 훅(Hook) 시스템** (린터, 산출물 가드, Worktree 보호 가드, 세션 지식 주입 훅 등)
* **슬래시 커맨드 세트**

> ⚠️ 프로젝트별 고유 스킬, 검사 규칙, 세션 다이제스트 파일은 플러그인 설치와 별개로 **`/dw-install`**(또는 `make install-project`) 명령어를 실행하여 빌드 및 배포해야 합니다. 플러그인은 공통 '엔진'이며, 프로젝트별 컴파일 결과물은 독립적으로 관리됩니다.

### 2. Vault 위치 제어 및 우선순위

지식 데이터(Vault)는 플러그인 코드 내부가 아닌 사용자의 **독립 로컬 폴더**에 보관됩니다. 사람은 Obsidian으로 편집하고 에이전트는 MCP 서버를 통해 접근합니다.

* **경로 해석 우선순위:** 환경 변수 `DW_VAULT_DIR` 경로 ➔ 기본 규약 경로(`~/denver-workflow-vault`) ➔ 해당 경로에 폴더가 없을 경우 에러를 반환하며 서버 구동이 중지됩니다.
* 커스텀 위치를 사용하려면 Claude Code 실행 전 터미널 환경 변수를 선언하십시오:
  ```bash
  export DW_VAULT_DIR="$HOME/My Vaults/denver"
  ```

### 3. Advisor 모델 지정 (Claude Opus 권장)

11단계 워크플로우 진행 중 기술적 교착 상태가 되거나 강력한 리뷰가 필요할 때 호출되는 Advisor 에스컬레이션용 모델입니다.

* 세션 창에서 `/advisor opus` 명령어를 입력하거나, `~/.claude/settings.json` 내에 아래 설정을 적용하십시오:
  ```json
  { "advisorModel": "claude-opus-4-8" }
  ```
* *(※ Anthropic API Key 필요, Claude Code v2.1.98 이상 버전 요구)*

### 4. 외부 의존성 관리

Denver는 자체 거버넌스 코어 및 하네스 엔진만 포함하고 있습니다. 개발 워크플로우 도중 에이전트가 호출하게 되는 강력한 외부 플러그인/스킬들은 사용자가 직접 환경에 설치해야 합니다. 미설치 상태로 도구가 호출되면 시스템이 스스로 자가치유 설치 안내 메시지를 노출합니다.

| 의존 도구 | 용도 | 설치 방법 |
| --- | --- | --- |
| **Obsidian** *(필수)* | 지식 저작 및 편집용 IDE 환경 | 공식 홈페이지 다운로드 또는 `brew install --cask obsidian` |
| **superpowers** *(권장)* | 브레인스토밍, 기획서 작성, TDD 구현 리드 | `claude plugin install superpowers@claude-plugins-official` |
| **impeccable** *(선택)* | 프론트엔드 UI/UX에 대한 전문 비평 | `claude plugin install impeccable@impeccable` |
| **gstack** *(권장)* | 디자인 시안 구현, 브라우징, 종합 디자인 QA | `git clone` 후 스킬 디렉토리에 타깃팅하여 내장 `./setup` 실행 |

---

## 💻 주요 CLI 명령어 (Makefile)

```bash
make build                    # Vault 컴파일 ➔ .claude/skills 디렉토리로 빌드
make dry-run                  # 실제 파일 수정 없이 규칙 유효성 및 빌드 검증 (CI 환경용, 경고 발생 시 에러 처리)
make test                     # 엔진 자기검사(stdlib unittest, 임시 vault 픽스처 — 실제 Vault 무영향)
make doctor                   # 콜드스타트 상태 진입 시 venv, 컴파일러, MCP 상태 전수 점검
make ratify                   # Draft 규칙 자동 비준 스크립트 실행 (크론탭 등 스케줄러 등록 권장)
make review                   # 사람의 판단이 필요한 수동 검토 큐 확인 및 시스템 상태 체크
make scaffold-vault           # 새로운 빈 Vault 공간에 기본 템플릿(Generic Seed) 구성 (덮어쓰기 방지 적용)
make update-seed              # 활성화된 Vault의 공통 거버넌스 규칙 파트를 템플릿 Seed로 역업데이트 (개인정보 자동 제외)
make clean / make distclean   # 빌드 산출물 제거 / 빌드 산출물 및 로컬 가상환경(.venv)까지 완전 제거
```

*(※ 외부 의존 패키지는 `pyyaml`과 `mcp` 뿐이며, `make` 명령어 실행 시 시스템 환경을 오염시키지 않고 프로젝트 로컬 가상환경(`.venv`)에 안전하게 자동 격리 설치됩니다.)*

> ⚠️ **dw-vault MCP 도구가 세션에 보이지 않으면 `make distclean` 후 재빌드하세요.**
> `mcp` 는 **`<2`** 로 핀되어 있습니다(2.0.0 이 `mcp.server.fastmcp` 를 제거해 서버가 기동하지
> 못합니다 — 2.12.0 에서 수정). 다만 그 핀은 **새로 만드는 `.venv` 에만** 적용됩니다. 2.12.0 이전에
> 만들어진 `.venv` 가 `mcp` 2.0.0 을 들고 있으면 그대로 남아 서버가 죽으므로, `make distclean` 으로
> 가상환경을 지우고 다시 만들어야 합니다(플러그인으로 설치했다면 플러그인 캐시의 `.venv` 삭제 —
> 런처가 다음 실행 때 핀으로 재생성합니다).

### 타깃 프로젝트에 거버넌스 배포 (Multi-Repo 배포)

```bash
# 지정 프로젝트에 전체 거버넌스 스킬 묶음 배포
make install-project P=/절대경로/대상프로젝트

# 특정 업무 도메인(Scope) 영역만 지정하여 배포
make install-project P=/절대경로/대상프로젝트 SCOPES=engineering,qa
```


`/dw-install` 명령은 세션 다이제스트에 등록된 **저장소 지도(Repo-Map)**를 읽어 각 멀티레포 경로를 순회하며 동기화를 자동으로 수행합니다.
동기화 과정에서는 **대상 프로젝트의 기존 스킬과 에이전트 설정을 그대로 유지**하고, Denver 매니페스트가 관리하는 거버넌스 영역만 최신 상태로 갱신합니다.
동기화된 산출물은 타깃 프로젝트에서 직접 수정하지 마십시오. 변경이 필요한 경우에는 **원본 Vault를 수정한 뒤 /dw-install을 다시 실행**하여 변경 사항을 반영해야 합니다.

---

## 📝 Frontmatter 작성 계약 (Vault 저작 규칙)

노트 최상단의 **Frontmatter(YAML 메타데이터)**는 사람이 이해하는 문서 구조와 컴파일러가 해석하는 규칙을 연결하는 **유일한 인터페이스 계약(Interface Contract)**입니다.

```yaml
---
type: rule
scope: backend-engineering
status: stable
compiles-to: skill
enforced-by: security-qa
check-deny:
  - "exec\\s*\\("
check-glob: "*.js,*.ts"
check-hint: "프로덕션 코드 내에서 raw exec 명령어 사용은 엄격히 금지됩니다. 전용 래퍼 모듈을 사용하세요."
---
```

### Frontmatter 주요 필드 규약

* **`type`:** 노트를 분류하는 라우팅 메인 키입니다. (`rule`, `guidance`, `procedure`, `memory`, `contract`, `spec`, `backlog`, `reference`, `decision`, `skill-manifest`, `agent` 중 선택)
* **`scope`:** 지식이 적용될 도메인을 `kebab-case` 형태로 지정합니다. (예: `api-design`, `frontend-qa`)
* **`status`:** 비준 상태를 의미합니다. (`draft`, `stable`, `deprecated`) **오직 `stable` 상태의 지식 노트만 에이전트 스킬로 컴파일되고 실제 환경에서 강제력을 가집니다.**
* **`compiles-to`:** 에이전트의 실행 가능 스킬 매니페스트 포함 여부를 정의합니다. (`skill`로 지정)
* **`enforced-by`:** 해당 규칙을 런타임에 검증할 전담 서브에이전트 ID를 매칭합니다. (`rule` 타입 필수 필드이며, `agents/` 내에 해당 에이전트 정의가 없으면 컴파일러가 경고/에러를 반환합니다.)
* **정적 린터 필드 (`check-deny`, `check-require`, `check-glob`, `check-exclude`, `check-hint`):** 문맥 정규식 패턴과 타깃 파일 Glob 범위를 지정합니다. **(`check-glob` 필드가 명시되지 않은 지식 노트는 자동 린터 정적 검사 대상에서 제외됩니다.)**

---

## 🔗 관련 문서 링크

* **Denver 아키텍처 불변식 및 9대 설계 원칙** ➔ [BOOTSTRAP.md](./BOOTSTRAP.md)
* **플러그인 자체 코어 개발 및 빌드 규약** ➔ [CLAUDE.md](./CLAUDE.md)
* **버전별 상세 릴리즈 변경 이력** ➔ [CHANGELOG.md](./CHANGELOG.md)
