---
description: 신규 기능 풀사이클 — 요구사항→배포 11단계 멀티에이전트 워크플로우(멀티레포 디스패치)
---
신규 기능을 **요구사항 → 배포**까지 11단계로 진행한다. 이 워크스페이스는 **멀티레포
오케스트레이터**이므로 원본의 "FE/BE worktree 2개"(한 레포 안)가 아니라 **레포별 do-er
디스패치**로 분기한다. 엔진은 `dw-orchestrator` 에이전트(분류·순차 디스패치·게이트·계약 흐름)고,
이 커맨드는 그 위의 **단계 순서 + 단계별 도구**다. 중복 규율은 vault 정본을 참조한다.

> **🟡 Karpathy 코딩 원칙은 모든 단계의 전제** — 가정 명시·단순함 우선·외과적 변경·목표주도
> 검증. 정본 `governance/guidance/karpathy-guidelines.md`(= `dev-engineering-charter` 스킬에 자동
> 주입). 11단계 어느 지점에서든 단계 도구보다 **먼저** 적용한다.
>
> **단발 수정 제외:** typo·1줄 fix·docs-only 는 11단계 불필요 → 해당 레포 do-er 에게 git flow
> 직행(브랜치→commit→PR→레포 CI→머지). 게이트(마이그레이션·시크릿·authz·데이터 손실)는 동의.
> **단, 태스크 등록은 면제가 아니다** — 착수 전 최소 1건을 올린다(아래 ②.5).

## 0단계: repo-map 부트스트랩 (라우팅 토대 — 기술자 1회 셋업)

11단계 진입 전 **레포 맵**(어떤 레포에 어떤 do-er 를 붙이는지)을 확보한다. 보통 기술자가 한 번
설정하면 이후 사용자는 일상 실행만 한다. **각 질문엔 짧은 설명을 붙이고, 자동 감지값·기본값을
먼저 제시하되 "직접 입력" 도 허용**한다(비숙련자도 따라가고 전문가는 정밀 입력 — 친화·전문 양립).

1. **존재 확인**: 현재 세션 digest 에 "## 레포 맵 (라우팅)" 이 있으면(또는 vault `project/repo-map.md`
   존재) → 그 레포 맵을 라우팅 정본으로 쓰고 0단계 건너뜀.
2. **없으면 대화식 수집**(`AskUserQuestion`, 한 항목씩, 설명 포함):
   - 레포 개수(단일/멀티). 단일레포면 1행만.
   - 각 레포: 이름 · 절대경로(현재 디렉토리·형제 디렉토리 자동 감지 제시) · 변경 면(프론트/백엔드/QA/
     인프라 등) · 스택(파일 마커로 추론 제시: package.json→JS/TS, pubspec.yaml→Dart/모바일,
     Cargo.toml→Rust계열, composer.json→PHP계열 등).
   - **do-er 배정(자유 입력 아님 — 메뉴)**: 스택→do-er 자동 매핑 후 확인받는다. 후보 = 탑재된 제네릭
     do-er `senior-front-engineer`(프론트/UI)·`senior-backend-engineer`(API/DB/서비스)·
     `senior-qa-engineer`(테스트/QA)·`senior-infra-engineer`(CI/배포) + 이미 설치된 프로젝트 특화 do-er.
   - checks 경로: 기본 `<레포>/.claude/dw-checks.json`(설명: "완료 검사 규칙 파일 위치", 비숙련자는
     기본값 그대로). CI/배포 규율: 자유 한 줄(모르면 비워둠 — 기본 "레포 표준").
   - 교차레포 순서(멀티레포 시): 기본 "계약 먼저 → 공급측 → 소비측". 배포 게이트: 기본 "마이그레이션·
     시크릿·authz·데이터 손실은 사용자 동의".
3. **작성**: vault 경로 해석(`DW_VAULT_DIR` > `~/denver-workflow-vault`) →
   `<vault>/project/repo-map.md` 를 `_seed/_templates/repo-map.md` 골격으로 채워 **Write**
   (`type: repo-map`, `status: stable`).
4. **빌드**: `/dw-install`(또는 `python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw.py" install-project`)로 digest 재생성 → "## 레포 맵" 주입.
5. **현재 세션 반영**: 방금 쓴 repo-map 본문을 읽어 당 세션 라우팅에 즉시 사용(차기 세션부턴 digest 자동).

> 11단계 진행 중 사용자에게 닿는 프롬프트(요구사항 확인·디자인 승인·머지/배포 동의 등)는 **평이한
> 언어**로 쓰고 전문 용어엔 짧은 설명을 붙인다(타겟=비숙련 일상 사용자). 단계 골격·게이트 자체는 불변.

## 레포 라우팅 (do-er)

라우팅은 **세션 digest 의 "## 레포 맵 (라우팅)"** 을 정본으로 한다(0단계에서 부트스트랩). 변경 면 →
레포 → do-er 매핑, 절대경로, checks 경로, 레포별 CI/배포 규율 모두 그 레포 맵을 따른다.

교차(2레포+) 작업은 **계약면 먼저 확정 → 공급측 → 소비측 순차**(orchestrator §3·§5).

## 11단계

```
신규 기능 ─ 단발 수정? ─YES─▶ [해당 레포 do-er git flow 직행]
              │ NO
   ┌── 설계 ────────────────────────────────────────────────┐
   │ ①  요구사항 분석   superpowers:brainstorming + ★advisor │
   │     └▶ vault specs/ (dw_write_spec, kind=spec)          │
   │ ②  상세 기획       superpowers:writing-plans            │
   │     └▶ 영향 레포별 plan (vault specs/ kind=plan)        │
   │ ②.5 태스크 등록  TaskCreate + addBlockedBy 의존성 잠금   │
   │     └▶ 남은 전 단계·레포별 태스크(게이트·검증 포함)      │
   │ ③  UI/UX 시안(앱) impeccable + gstack:design-consultation│
   │ ③.5 디자인 HTML   gstack:design-html + ★advisor         │
   └────────────────────────────┬───────────────────────────┘
   ┌── 분기 + 계약 GATE ─────────▼───────────────────────────┐
   │ ④  업무 배분       레포별 do-er + worktree 격리(레포 안) │
   │ 🔒 GATE: BFF 계약  vault contracts/ SSOT + ★advisor 합의 │
   │     request/response shape 확정 전 ⑤ 진입 금지(§5)       │
   └────────────────────────────┬───────────────────────────┘
   ┌── 구현 — 순차 디스패치 ─────▼───────────────────────────┐
   │ ⑤  구현 + 회귀가드 계약→공급측→소비측 do-er 순차          │
   │     사고 fix 는 회귀 가드 RED 먼저(tdd-iron-law)         │
   └────────────────────────────┬───────────────────────────┘
   ┌── 검증 ─────────────────────▼───────────────────────────┐
   │ ⑥  PR + 리뷰 + CI  레포별 워크플로우(아래 "레포별 CI")   │
   │     완료 게이트 = 대상 레포 dw-checks.json(§4)           │
   │ ⑦  기획↔구현 비교  ★advisor + 수동 체크리스트            │
   │ ⑦.5 디자인 QA      gstack:design-review + gstack:browse  │
   │ ⑧  기능 QA         gstack:qa + browse(앱/웹 스모크)      │
   │ ⑧.5 회귀 스위트    대상 레포 테스트 전체 green           │
   └────────────────────────────┬───────────────────────────┘
   ┌── 배포 ─────────────────────▼───────────────────────────┐
   │ ⑨  머지 + 배포     레포별. 머지·배포 게이트 사용자 동의  │
   └─────────────────────────────────────────────────────────┘
   ★ = advisor 에스컬레이션   🔒 = GATE
```

| # | 단계 | 도구 | 산출물 |
|---|------|------|--------|
| 1 | 요구사항 분석 | `superpowers:brainstorming` + advisor | vault `specs/`(spec) |
| 2 | 상세 기획 | `superpowers:writing-plans` | 영향 레포별 plan(vault `specs/`) |
| 2.5 | **태스크 등록(의무)** | `TaskCreate` + `TaskUpdate(addBlockedBy)` | 세션 태스크 목록 — 남은 전 단계·레포별, 순차 규율이 의존성으로 잠김 |
| 3 | UI/UX 시안(앱) | `impeccable` + `gstack:design-consultation` | 시안·critique |
| 3.5 | 디자인 HTML | `gstack:design-html` + advisor | HTML/CSS 목업(레퍼런스) |
| 4 | 업무 배분 + 브랜치 | `superpowers:using-git-worktrees`(do-er 가 자기 레포에서) | do-er별 worktree |
| 🔒 | **GATE: BFF 계약** | vault `contracts/` + advisor 합의 (진입 전 `API 명세 — 전체 인덱스` 읽기) | `dw_write_contract` |
| 5 | 구현 + 회귀가드 | `superpowers:subagent-driven-development`(순차) + advisor | 구현 + 회귀가드 |
| 6 | PR + 리뷰 + CI | `gh pr create` → 레포별 CI | PR + 대상 레포 checks green |
| 7 | 기획↔구현 비교 | advisor + 수동 체크리스트 | PR diff vs plan |
| 7.5 | 디자인 QA | `gstack:design-review` + `gstack:browse` | 3.5 목업 vs 구현 |
| 8 | 기능 QA | `gstack:qa` + `gstack:browse` | 앱/웹 스모크 |
| 8.5 | 회귀 스위트 | 대상 레포 테스트 전체 | 기존 기능 깨짐 차단 |
| 9 | 머지 + 배포 | 레포별 git/PR/deploy 규율 | 배포 + **API·배치/크론 명세 갱신·변경 이력 기록**(`dw_write_reference`) |

## ②.5 태스크 등록 — 계획이 끝나면 **무조건** 등록하고 진행한다

② 기획 산출물(영향 레포별 plan)이 확정되면 **③ 이후로 넘어가기 전에** 남은 전 단계를 세션
**태스크 목록**(작업 항목 체크리스트 — 사용자가 진행 상황을 실시간으로 본다)에 등록한다. 등록
없이 구현에 들어가지 않는다.

> **11단계가 아니어도 마찬가지다.** 이 워크플로우로 하는 **모든 실질 작업**은 태스크로 등록하고
> 관리한다 — 단발 수정(typo·1줄 fix·docs-only)도 착수 전에 **최소 1건**(브랜치→커밋→PR→CI→머지)을
> 올린다. 등록 시점만 다르다: 11단계는 **② 계획 확정 직후 전 단계**, 그 외는 **착수 직전**.
> 등록이 면제되는 건 순수 질의응답·조회처럼 **바꾸는 게 없는 작업**뿐이다.

1. **도구** — `TaskCreate`(생성) · `TaskUpdate`(상태·의존성) · `TaskList`(현황). 세션에 스키마가
   안 보이면 `ToolSearch` 로 `select:TaskCreate,TaskUpdate,TaskList` 를 **먼저 로드**한다(지연 로드
   하네스 대비). Task 계열이 아예 없는 하네스면 `TodoWrite` 로 대체하되 **등록 자체는 생략 금지**.
2. **무엇을 등록하나** — 한 태스크 = 한 단위 작업. **구현만 등록하지 않는다**: 🔒 계약 GATE,
   레포별 구현(⑤), ⑥ PR+리뷰+CI, ⑦ 기획↔구현 비교, ⑦.5 디자인 QA, ⑧ 기능 QA, ⑧.5 회귀 스위트,
   ⑨ 머지+배포까지 **게이트·검증도 태스크**다. 멀티레포면 레포별로 쪼갠다(제목에 레포명).
3. **순차 규율을 의존성으로 못 박는다** — `TaskUpdate` 의 `addBlockedBy` 로
   **계약 GATE → 공급측 → 소비측 → 검증 → 배포** 순서를 잠근다. "병렬 금지" 를 문장이 아니라
   **데이터**로 강제하는 지점이다(orchestrator §3).
4. **목록 주인은 오케스트레이터 하나** — 생성과 모든 상태 전이는 orchestrator(단일 레포 세션이면
   dw-governed)가 한다. do-er 는 도구를 상속받아 쓸 수 있지만 **목록을 건드리지 않는다**(중복·
   낡은 상태 방지). 상태 갱신 전엔 `TaskGet` 으로 최신 상태를 먼저 읽는다.
5. **전이 시점** — 디스패치 **직전** `in_progress`, **대상 레포 checks green 을 재검증한 뒤에만**
   `completed`(§4 완료 게이트). 막히면 `in_progress` 를 유지하고 **차단 사유를 새 태스크로** 남긴다.
   검사 실패 상태로 `completed` 로 넘기지 않는다.
6. **적용 범위 = 바꾸는 모든 작업** — 11단계 진입 작업은 물론 단발 수정도 등록한다(위 인용문).
   면제는 읽기·질의응답뿐. 단발 수정은 태스크 1건이면 충분하다 — 규모에 맞춰 쪼개되, "작아서
   생략" 은 없다.
7. **이 규칙은 grep 검사 대상이 아니다** — `dw-checks.json` 은 **파일 내용** 패턴(deny/require)이고
   `enforced_by` 검증자도 diff 를 본다. 태스크 목록은 **세션 상태**라 어느 쪽도 볼 수 없다. 즉
   이건 자동 게이트가 아니라 **오케스트레이터 자기 규율**이다 — 검사가 안 잡아준다는 뜻이므로
   더 엄격히 지켜라. (사용자는 태스크 목록이 비어 있는 것으로 위반을 즉시 본다.)

## 핵심 규칙 (정본 참조 — 여기서 재정의하지 않음)

1. **gitflow + PR 의무 · `--admin` 금지 · 머지 보류 게이트** → `guidance/pr-merge-discipline.md`
2. **worktree 격리(do-er 가 자기 레포에서)** → `guidance/worktree-isolation.md` + orchestrator §3
3. **API 계약 GATE = vault contracts/ SSOT** → orchestrator §5. shape 확정 전 ⑤ 진입 금지.
   계약은 **앞으로 만들 것**(협상·signoff·완결 시 archive), vault `reference/API 명세 — *` 는
   **이미 머지된 현재 상태**다. GATE 진입 전 명세 인덱스를 읽어 기존 엔드포인트·규약과 충돌하는지
   확인하고, ⑨ 머지 후 명세를 갱신해야 GATE 가 닫힌다(api-spec-update)
4. **순차 디스패치(병렬 금지)** → orchestrator §3. 계약 먼저 → 백엔드 → 앱/채팅
5. **회귀 2지점** → `guidance/tdd-iron-law.md`·`regression-by-set-diff.md`. ⑤ 사고 fix 는 RED 먼저 / ⑧.5 배포 전 전체 green
6. **완료 게이트 = 대상 레포 checks** → orchestrator §4. green 전 완료 선언 금지
7. **gap-detector 미사용** — `docs/02-design/` 포맷 의존이라 ⑦ 은 수동 체크리스트
8. **계획 완료 = 태스크 등록** — ② 이후 ②.5 를 건너뛰고 구현 진입 금지. 목록 주인은
   오케스트레이터 하나, 완료 전이는 대상 레포 checks green 뒤에만(위 ②.5)

## 레포별 CI/배포 (보편 보장 아님 — 레포마다 다름)

각 레포의 CI/배포 규율은 **레포 맵의 "CI/배포" 열**에 적힌다. do-er 에게 **자기 레포 워크플로우를
따르게** 하고, 완료 검증은 항상 그 레포의 `<repo>/.claude/dw-checks.json` + `enforced-by` 검증자로
한다(orchestrator §4). 머지·배포 게이트(마이그레이션·시크릿·authz·데이터 손실)는 사용자 동의.

> **(선택) GitHub Actions Claude PR 리뷰어** — ⑥단계 리뷰를 CI 에서 자동화하려면 `/dw-ci-review` 로
> 저장소에 Claude 기반 PR 리뷰 워크플로우(`.github/workflows/dw-pr-review.yml`)를 설치할 수 있다.
> PR 마다 Claude 가 그 레포 커밋 거버넌스(skills·dw-checks·CLAUDE.md) 기준으로 리뷰하고 합격/불합격을
> 판정 — 브랜치 보호 required check(`review`)에 넣으면 리뷰 통과 전 머지 차단. 저장소별 옵인이다.

## advisor 에스컬레이션 트리거

```
① 요구사항 확정 후(구현 전 설계 검증)   🔒 API 계약 GATE 합의
⑥ 리뷰/CI FAIL(레포 auto-iterate 한도 초과 시)   ⑦ 스펙 대비 갭
⑦.5 디자인 리그레션   ⑧.5 회귀 발견
+ do-er 가 스스로 해결 못 하는 문제 → 즉시 advisor
```

## 흔한 실수

| 실수 | 교정 |
|------|------|
| 레포 간 병렬 디스패치 | 순차 — 계약 먼저 → 백엔드 → 앱/채팅 |
| API 계약 없이 ⑤ 진입 | GATE 먼저 — vault contracts/ shape 확정 |
| 특정 레포 CI 를 전 레포 보장으로 가정 | 레포별 CI 다름 — 대상 레포 checks 로 게이트 |
| `--admin` 강제 머지 | 레포 규율 따름. `--admin` 금지 |
| 마이그레이션/시크릿 변경 무동의 머지 | escalate — 사용자 동의 |
| gap-detector 로 ⑦ | 포맷 불일치 — 수동 체크리스트 |
| union checks 로 완료 게이트 | 대상 레포 checks 로(§4) — 오적용 방지 |
| 계획만 세우고 바로 구현 진입 | ②.5 태스크 등록 먼저 — 게이트·검증까지 포함해 등록 |
| 단발 수정이라 태스크 생략 | 작아도 최소 1건 등록 — 면제는 읽기·질의응답뿐 |
| 구현 태스크만 등록 | 🔒 GATE·⑥·⑦·⑧.5·⑨ 도 태스크. 검증이 빠지면 완료가 안 보인다 |
| do-er 가 태스크 상태를 갱신 | 목록 주인은 오케스트레이터 하나 — do-er 는 건드리지 않는다 |
| checks 확인 전 `completed` 전이 | green 재검증 뒤에만 완료. 막히면 `in_progress` 유지 |

## 외부 플러그인 의존 (미설치 시 그 자리에서 설치 — 자가치유)

이 워크플로우가 호출하는 외부 플러그인. 단계 진입 시 세션에 없으면 **사용자에게 알린 뒤 아래
명령으로 직접 설치하고 계속한다** (guidance `dw-dependencies` — 실패 시에만 수동 안내).
**주의: gstack 은 CC 플러그인이 아니라 git clone + setup 으로 설치**(나머지는 플러그인 마켓플레이스).

```bash
# superpowers (①②④⑤): brainstorming·writing-plans·using-git-worktrees·subagent-driven-development
#   → 공식 마켓플레이스(claude-plugins-official, 빌트인) 제공 — marketplace add 불요
claude plugin install superpowers@claude-plugins-official

# impeccable (③): UI 설계/비평
claude plugin marketplace add pbakaus/impeccable && claude plugin install impeccable@impeccable


# gstack (③③.5⑦.5⑧, 프론트/앱 작업 시): design-consultation·design-html·design-review·browse·qa
#   → 플러그인 아님. 유저 스코프 스킬로 git clone 후 setup. 업그레이드는 /gstack-upgrade
git clone --single-branch --depth 1 https://github.com/garrytan/gstack.git ~/.claude/skills/gstack \
  && cd ~/.claude/skills/gstack && ./setup
```

- **advisor**: 빌트인(이 하네스 제공) — 별도 설치 불요.
- **denver-workflow(dw-vault)**: 이 플러그인 자체 — `/dw-setup` 으로 설치.
- 미설치 플러그인의 단계는 **건너뛰지 말고** 사용자에게 설치 안내 후 진행(검증 전 완료 선언 금지).

_관련: 오케스트레이터 `governance/agents/dw-orchestrator.md` · 정본 가이던스 `governance/guidance/`
(karpathy·pr-merge-discipline·worktree-isolation·tdd-iron-law) · 계약 SSOT vault `contracts/`._
