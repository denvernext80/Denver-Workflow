---
description: 신규 기능 풀사이클 — 요구사항→배포 11단계 멀티에이전트 워크플로우(멀티레포 디스패치)
---
신규 기능을 **요구사항 → 배포**까지 11단계로 진행한다. 이 워크스페이스는 **멀티레포
오케스트레이터**이므로 원본의 "FE/BE worktree 2개"(한 레포 안)가 아니라 **레포별 do-er
디스패치**로 분기한다. 엔진은 `ssot-orchestrator` roster(분류·순차 디스패치·게이트·계약 흐름)고,
이 커맨드는 그 위의 **단계 순서 + 단계별 도구**다. 중복 규율은 vault 정본을 참조한다.

> **🟡 Karpathy 코딩 원칙은 모든 단계의 전제** — 가정 명시·단순함 우선·외과적 변경·목표주도
> 검증. 정본 `governance/guidance/karpathy-guidelines.md`(= `dev-engineering-charter` 스킬에 자동
> 주입). 11단계 어느 지점에서든 단계 도구보다 **먼저** 적용한다.
>
> **단발 수정 제외:** typo·1줄 fix·docs-only 는 11단계 불필요 → 해당 레포 do-er 에게 git flow
> 직행(브랜치→commit→PR→레포 CI→머지). 게이트(마이그레이션·시크릿·authz·데이터 손실)는 동의.

## 레포 라우팅 (do-er)

| 변경 면 | 레포 | do-er |
|---|---|---|
| 백엔드 BFF/API/DB | Travel-One | `backend-lead` |
| 모바일 화면/배선 | Balipick-App | `senior-mobile-engineer` |
| 채팅 서비스 | balipick-chat | `rust-chat-engineer` |

교차(2레포+) 작업은 **계약면 먼저 확정 → 공급측(백엔드) → 소비측(앱/채팅) 순차**.
(orchestrator §3·§5)

## 11단계

```
신규 기능 ─ 단발 수정? ─YES─▶ [해당 레포 do-er git flow 직행]
              │ NO
   ┌── 설계(Plan) ──────────────────────────────────────────┐
   │ ①  요구사항 분석   superpowers:brainstorming + ★advisor │
   │     └▶ vault specs/ (ssot_write_spec, kind=spec)        │
   │ ②  상세 기획       superpowers:writing-plans            │
   │     └▶ 영향 레포별 plan (vault specs/ kind=plan)        │
   │ ③  UI/UX 시안(앱) impeccable + gstack:design-consultation│
   │ ③.5 디자인 HTML   gstack:design-html + ★advisor         │
   └────────────────────────────┬───────────────────────────┘
   ┌── 분기 + 계약 GATE ─────────▼───────────────────────────┐
   │ ④  업무 배분       레포별 do-er + worktree 격리(레포 안) │
   │ 🔒 GATE: BFF 계약  vault contracts/ SSOT + ★advisor 합의 │
   │     request/response shape 확정 전 ⑤ 진입 금지(§5)       │
   └────────────────────────────┬───────────────────────────┘
   ┌── 구현(Do) — 순차 디스패치 ─▼───────────────────────────┐
   │ ⑤  구현 + 회귀가드 계약→backend-lead→앱/채팅 do-er 순차  │
   │     사고 fix 는 회귀 가드 RED 먼저(tdd-iron-law)         │
   └────────────────────────────┬───────────────────────────┘
   ┌── 검증(Check) ──────────────▼───────────────────────────┐
   │ ⑥  PR + 리뷰 + CI  레포별 워크플로우(아래 "레포별 CI")   │
   │     완료 게이트 = 대상 레포 ssot-checks.json(§4)         │
   │ ⑦  기획↔구현 비교  ★advisor + 수동 체크리스트            │
   │ ⑦.5 디자인 QA      gstack:design-review + gstack:browse  │
   │ ⑧  기능 QA         gstack:qa + browse(모바일 스모크)     │
   │ ⑧.5 회귀 스위트    대상 레포 테스트 전체 green           │
   └────────────────────────────┬───────────────────────────┘
   ┌── 배포(Act) ────────────────▼───────────────────────────┐
   │ ⑨  머지 + 배포     레포별. 머지·배포 게이트 사용자 동의  │
   └─────────────────────────────────────────────────────────┘
   ★ = advisor 에스컬레이션   🔒 = GATE
```

| # | 단계 | 도구 | 산출물 |
|---|------|------|--------|
| 1 | 요구사항 분석 | `superpowers:brainstorming` + advisor | vault `specs/`(spec) |
| 2 | 상세 기획 | `superpowers:writing-plans` | 영향 레포별 plan(vault `specs/`) |
| 3 | UI/UX 시안(앱) | `impeccable` + `gstack:design-consultation` | 시안·critique |
| 3.5 | 디자인 HTML | `gstack:design-html` + advisor | HTML/CSS 목업(레퍼런스) |
| 4 | 업무 배분 + 브랜치 | `superpowers:using-git-worktrees`(do-er 가 자기 레포에서) | do-er별 worktree |
| 🔒 | **GATE: BFF 계약** | vault `contracts/` + advisor 합의 | `ssot_write_contract` |
| 5 | 구현 + 회귀가드 | `superpowers:subagent-driven-development`(순차) + advisor | 구현 + 회귀가드 |
| 6 | PR + 리뷰 + CI | `gh pr create` → 레포별 CI | PR + 대상 레포 checks green |
| 7 | 기획↔구현 비교 | advisor + 수동 체크리스트 | PR diff vs plan |
| 7.5 | 디자인 QA | `gstack:design-review` + `gstack:browse` | 3.5 목업 vs 구현 |
| 8 | 기능 QA | `gstack:qa` + `gstack:browse` | 모바일 스모크 |
| 8.5 | 회귀 스위트 | 대상 레포 테스트 전체 | 기존 기능 깨짐 차단 |
| 9 | 머지 + 배포 | 레포별 git/PR/deploy 규율 | 배포 |

## 핵심 규칙 (정본 참조 — 여기서 재정의하지 않음)

1. **gitflow + PR 의무 · `--admin` 금지 · 머지 보류 게이트** → `guidance/pr-merge-discipline.md`
2. **worktree 격리(do-er 가 자기 레포에서)** → `guidance/worktree-isolation.md` + orchestrator §3
3. **API 계약 GATE = vault contracts/ SSOT** → orchestrator §5. shape 확정 전 ⑤ 진입 금지
4. **순차 디스패치(병렬 금지)** → orchestrator §3. 계약 먼저 → 백엔드 → 앱/채팅
5. **회귀 2지점** → `guidance/tdd-iron-law.md`·`regression-by-set-diff.md`. ⑤ 사고 fix 는 RED 먼저 / ⑧.5 배포 전 전체 green
6. **완료 게이트 = 대상 레포 checks** → orchestrator §4. green 전 완료 선언 금지
7. **gap-detector 미사용** — `docs/02-design/` 포맷 의존이라 ⑦ 은 수동 체크리스트

## 레포별 CI/배포 (보편 보장 아님 — 레포마다 다름)

- **Travel-One**: GH Actions 자동 path — `pr-review.yml`(리뷰) + `ci.yml`(phpstan·psalm·knip·
  phpunit·vitest·build) + `deploy.yml`(3-layer 가드 자동 배포). `gh pr merge --auto --squash`.
- **Balipick-App**: Flutter `analyze`/위젯테스트 + iOS/Android 스토어 절차(vault `procedures/`
  앱 릴리스·App Store 빌드 참조). 배포는 사용자 동의.
- **balipick-chat**: Rust(cargo test·clippy) + systemd/musl 경로(별 배포). 이 레포는 자동 배포 안 함.

do-er 에게 **자기 레포 워크플로우를 따르게** 한다. 완료 검증은 항상 그 레포의
`<repo>/.claude/ssot-checks.json` + `enforced-by` 검증자로 한다(orchestrator §4).

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
| Travel-One CI 를 전 레포 보장으로 가정 | 레포별 CI 다름 — 대상 레포 checks 로 게이트 |
| `--admin` 강제 머지 | `--auto`(Travel-One) / 레포 규율. `--admin` 금지 |
| 마이그레이션/시크릿 변경 무동의 머지 | escalate — 사용자 동의 |
| gap-detector 로 ⑦ | 포맷 불일치 — 수동 체크리스트 |
| union checks 로 완료 게이트 | 대상 레포 checks 로(§4) — 오적용 방지 |

## 외부 플러그인 의존 (미설치 시 사용자에게 설치 안내)

이 워크플로우가 호출하는 외부 플러그인. 세션에 없으면 해당 단계 전에 사용자에게 설치를 안내한다.
**주의: gstack 은 CC 플러그인이 아니라 git clone + setup 으로 설치**(나머지는 플러그인 마켓플레이스).

```bash
# superpowers (①②④⑤): brainstorming·writing-plans·using-git-worktrees·subagent-driven-development
#   → 공식 마켓플레이스(claude-plugins-official, 빌트인) 제공 — marketplace add 불요
claude plugin install superpowers@claude-plugins-official

# impeccable (③): UI 설계/비평
claude plugin marketplace add pbakaus/impeccable && claude plugin install impeccable@impeccable

# bkit (⑥ 리뷰 미러·auto-iterate): code-analyzer·pdca-iterator
claude plugin marketplace add popup-studio-ai/bkit-claude-code && claude plugin install bkit@bkit-marketplace

# gstack (③③.5⑦.5⑧): design-consultation·design-html·design-review·browse·qa
#   → 플러그인 아님. 유저 스코프 스킬로 git clone 후 setup. 업그레이드는 /gstack-upgrade
git clone --single-branch --depth 1 https://github.com/garrytan/gstack.git ~/.claude/skills/gstack \
  && cd ~/.claude/skills/gstack && ./setup
```

- **advisor**: 빌트인(이 하네스 제공) — 별도 설치 불요.
- **denver-agent(ssot-vault)**: 이 워크스페이스 자체 — `make install-orchestrator` 로 설치.
- 미설치 플러그인의 단계는 **건너뛰지 말고** 사용자에게 설치 안내 후 진행(검증 전 완료 선언 금지).

_관련: orchestrator roster `roster/ssot-orchestrator.md` · 정본 가이던스 `governance/guidance/`
(karpathy·pr-merge-discipline·worktree-isolation·tdd-iron-law) · 계약 SSOT vault `contracts/`._
