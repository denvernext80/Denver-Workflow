---
type: reference
title: vault 구성 원칙 (폴더 택소노미 + frontmatter 계약)
---

# 이 vault 의 구성 원칙

> denver-agent SSOT vault. **폴더는 사람용 정리, frontmatter `type` 은 기계용 라우팅.**
> 컴파일러는 `*.md` 를 전부 훑고 frontmatter 로만 라우팅하므로 폴더 위치는 안전하지만,
> 아래 두 축으로 정리해 탐색·관리·배포(공개/사적)를 가른다.

## 두 축

### 축 B — 에이전트 운영체계 (`governance/`) — "어떻게 일하나" · 프로젝트 무관 · 컴파일됨
| 폴더 | 용도 | type | 컴파일 |
|---|---|---|---|
| `governance/_skills/` | scope 묶음 정의(skill-manifest) | `skill-manifest` | ✅ |
| `governance/rules/` | "법" — 검증 가능한 강제(`enforced-by` 필수) | `rule` | ✅ stable |
| `governance/guidance/` | 작업 규율 — 공유 원칙(enforced-by 불요) | `guidance` | ✅ stable |
| `governance/procedures/` | 재사용 절차(playbook, 에이전트 저작 draft→ratify) | `procedure` | ✅ stable |
| `governance/agents/` | 검증자·하네스 역할 정의(`enforced-by` 대상) | `agent` | 서브에이전트로 설치 |

### 축 A — 프로젝트 지식 (`project/`) — "무엇을 만들/합의/배웠나" · 프로젝트 종속 · 비컴파일 LIVE
| 폴더 | 용도 | type | 컴파일 |
|---|---|---|---|
| `project/decisions/` | ADR(아키텍처 결정 기록) — append-only | `decision` | ❌ |
| `project/contracts/` | 백엔드↔앱 등 인터페이스 계약(`archive/` 포함) | `contract` | ❌ LIVE |
| `project/specs/` | 계획·스펙·설계(`archive/` 포함) | `spec` | ❌ LIVE |
| `project/memory/` | 에이전트 학습(날짜별, `archive/` 포함) | `memory` | ❌ LIVE |

### 예외 — `repo-map` (프로젝트 토폴로지/설정)
| 폴더 | 용도 | type | 컴파일 |
|---|---|---|---|
| `project/repo-map.md` | 멀티레포 라우팅 토폴로지(레포·do-er·스택·checks·CI) | `repo-map` | ✅ **digest 주입(예외)** |

`repo-map` 은 axis-A(프로젝트 종속)지만 **digest 로 주입되는 유일한 예외**다 — "프로젝트 지식"이 아니라
"프로젝트 설정/토폴로지"라 orchestrator 가 매 디스패치마다 always-on 으로 필요하기 때문. 다른 axis-A
타입(spec/contract/memory/decision)은 비컴파일 원칙 유지. 생성은 `/denver-workflow` 0단계 대화식 부트스트랩.

## 분류 규칙 (신규 노트가 어디로)
- 특정 기능/엔티티/계약에 종속 → **축 A**(spec/contract/decision/memory).
- "다음에도 이렇게 일한다"는 절차·규칙·원칙 → **축 B**(procedure/rule/guidance).
- 강제하고 싶으면 `rules/`(+ enforced-by 검증자 또는 결정론 검사), 강제 아닌 재사용 절차면 `procedures/`.

## 배포 경계 (공개 플러그인 seed vs 사적 vault)
- **축 B(governance)** = 재사용 운영체계 → 제네릭 분은 플러그인 seed 로 배포 가능.
- **축 A(project)** = 사적 프로젝트 지식 → **공개 플러그인에 절대 포함하지 않음.** 개인 vault 에만.

## frontmatter 계약 (필수 필드)
- `rule`: `type scope status enforced-by compiles-to`
- `guidance`: `type scope status compiles-to`
- `skill-manifest`: `type scope skill-name skill-description`
- `procedure`: `type scope status compiles-to`
- `memory`/`contract`/`spec`: `type status` (+`title`) · `decision`/`reference`/`agent`: `type`
- `status`: `draft`/`stable`/`deprecated` — **`stable` 만 컴파일·강제**.
- LIVE(memory/contract/spec)는 MCP write 시 stable 직행, OBEY(rule/procedure)는 draft→ratify 자동 비준.

저작: 명령 팔레트 → *Insert template* 로 `_templates/` 의 frontmatter 를 채워 시작. 저작 후 `make build`.
