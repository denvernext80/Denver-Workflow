# Changelog

## 2.8.0 — 2026-07-11

### 개선 — 에이전트·스킬 전수 점검(최신화·전문화)
- **검증자(reviewer) 4종 전문화 — code-review·security-qa·design-review·perf-tester.** 2~4줄 요약문이던
  에이전트를 실전 검증자로 재작성: 검토 절차(diff 실측→항목별 검사), 보고 형식(🔴 차단/🟡 권고 ·
  file:line · 근거 규칙), 오탐 규율(증거 없는 지적 금지·확인 필요 표기), "구현하지 않는다" 역할 경계.
  vault 와 seed 를 byte-동일로 재정렬(verbatim 화이트리스트 불변식 복원).
- **도구명 최신화 `Task` → `Agent`.** Claude Code 서브에이전트 도구 개명 반영 — dw-governed·
  dw-orchestrator·dispatch-discipline·agent-delegation-preference 의 위임/디스패치 문구 갱신(구명 병기).
- **죽은 `tools:` frontmatter 제거(에이전트 6종).** 컴파일러는 name/description 만 emit 하고 설치
  에이전트는 세션 도구 전체를 상속(MCP 포함) — 오해 유발 메타데이터를 소스에서 제거하고
  `_templates/agent.md` 에 명문화.
- **senior-backend-engineer 리뷰 경로 갱신.** `bkit:code-analyzer` 1순위 참조를 dw 자체 검증자
  (`code-review`·`security-qa`) 1순위로 교체(bkit 은 설치 시 병행 옵션으로 강등).
- **dw-ratifier 죽은 타깃 수정.** 존재하지 않는 `make install` 참조 → `make ratify` + `/dw-install`.

### 수정 — seed 파이프라인 정합
- **Makefile 화이트리스트 stale 해소.** `SEED_AGENTS` 4→10종(승격된 do-er/reviewer 반영),
  `SEED_GUIDANCE` 9→12종(denver-workflow·dispatch-discipline·graphify-search). 손-제네릭화 변형
  (senior-backend·senior-mobile)은 화이트리스트 제외를 주석으로 명문화 — update-seed 가 특화본으로
  seed 를 덮어쓰는 사고 방지.
- **live vault 결손 복구.** seed 에만 있던 guidance 2종(dw-dependencies·dw-user-facing-copy)을 vault 에
  복사, 구판으로 드리프트된 denver-workflow guidance·engineering 차터를 seed 신판으로 동기.
- 검증: `make dry-run`(에러 0·경고 0) · `make seed-check` green · 추적 4개 프로젝트 재설치 완료.

## 2.7.4 — 2026-07-07

### 추가
- **범용 do-er/reviewer 3종 seed 승격 — senior-mobile·perf-tester·design-review.** vault 에만 있던
  에이전트를 프로젝트 종속을 걷어내고 `_seed/governance/agents/` 로 올려, 신규 vault scaffold(`/dw-setup`)가
  이들을 받도록 seed 자기충족 세트를 보강했다.
  - `senior-mobile-engineer`: 발리픽/Flutter 종속 제거, 스택 무관(Flutter·RN·네이티브 iOS/Android)으로
    재작성. codegen 전체 재생성·공유 에뮬 경합·adb 드리프트·DNS flaky·실기기 빌드 등 모바일 특화 지혜는
    일반화해 보존. `install: always`.
  - `perf-tester`: 종속 0 이라 verbatim 승격.
  - `design-review`: `BalipickColors`·`Pretendard`·다크모드-위반 제거 → 토큰/폰트/테마 정책 일반화.
    "정적 grep 가능분만 강제, 시각 심사는 사람 몫" 원칙 보존.
  - 기존 프로젝트·개인 vault 는 무변경(프로젝트 전용본 유지). `make seed-check` green.

### 수정
- **dw-pr-review 하드닝 마감.** 유예됐던 verdict 게이트 하드닝 3건 반영 + MEDIUM 카운트 교차검증의
  `grep -c`/`set -e` 상호작용 오탐 FAIL 수정.

### 문서
- `roster/` 디렉토리 개념 폐기 정리(에이전트 정본 = `governance/agents/`), BOOTSTRAP·README 최신화
  (backlog·reference 타입, 11 도구, `dw_resolve`), PDCA 용어 정합.

## 2.7.3 — 2026-07-05

### 수정
- **PR 리뷰어 verdict 라인앵커 — 산문 자기참조 오탐 FAIL 종식.** verdict 판정 체크(#1 FAIL·#4 PASS)가
  코멘트 **전체 본문**에서 `Verdict: FAIL` 문자열을 grep 해, 리뷰어가 finding 산문에서
  `` `## Verdict: FAIL` `` 을 인용(백틱)하기만 해도 정당한 PASS 를 오탐 FAIL 시켰다(#616 재리뷰에서
  발현). 판정 검사를 **라인앵커**(`^[[:space:]]*#*[[:space:]]*Verdict:`)로 바꿔 판정 라인만 인정하고
  줄 중간 인용은 무시한다. 이로써 verdict·severity 신호가 전부 라인/불릿 앵커로 통일돼 자기참조
  false-match 부류가 종식된다. 로컬 테스트 하네스 9케이스 통과(실제 #616 오탐 픽스처 포함).
  - 템플릿 + 3개 PR 브랜치(#616·#441·#21) 반영.

## 2.7.2 — 2026-07-05

### 수정
- **PR 리뷰어 verdict 게이트 오탐 FAIL 수정 + MEDIUM 카운트 교차검증.** 2.7.1 의 `[CRITICAL]/[HIGH]`
  교차검증이 **코멘트 전체 본문**을 grep 해, 리뷰어가 finding 텍스트에서 `` `[CRITICAL]` `` 를 산문·
  백틱으로 언급만 해도 매치돼 정당한 PASS 를 오탐 FAIL 시켰다(리뷰어가 자기 PR #616 에서 발견).
  - 심각도 태그를 **불릿 맨 앞**(`^\s*[-*]\s*\**\[(CRITICAL|HIGH)\]`)일 때만 실제 finding 으로 판정 —
    산문·백틱 언급은 무시(오탐 제거). 로컬 테스트 하네스 11케이스 통과(실제 #616 본문 포함).
  - **MEDIUM 3개 이상 → FAIL** 카운트 교차검증 추가(프롬프트 판정규칙과 shell 게이트 일치).
  - 중복·prose-prone 하던 Severity `-A2` 백업 grep 제거(불릿 앵커 교차검증이 대체). Verdict 정규식
    `[[:space:]*]*`→`[[:space:]]*` 교정.
  - 템플릿 + 3개 PR 브랜치(#616·#441·#21) 반영.

## 2.7.1 — 2026-07-05

### 보안
- **PR 리뷰어 verdict 게이트 하드닝(3건).** 새 리뷰어를 balipick-app #441 에 적용하자 리뷰어가 **자기
  워크플로우를 리뷰하며 실제 결함을 발견**(자기 도입 PR 을 CRITICAL 로 FAIL — 도구 정상 작동). 발견분 수정:
  - **[CRITICAL] 작성자 미검증 게이트 우회** — verdict 스텝이 `review-sha` 마커 코멘트를 작성자 확인
    없이 채택 → PR 코멘트 권한자가 위조 `## Verdict: PASS` 로 게이트 통과 가능. `jq select` 에
    `author.login == "github-actions"` 필터 추가(실측: `gh --json` 은 `[bot]` 접미 없이 반환).
  - **[MEDIUM] Findings 교차검증 부재** — overall Verdict 가 PASS 라도 본문에 `[CRITICAL]`/`[HIGH]`
    태그가 있으면 FAIL(prompt-injection 등으로 overall 만 뒤집히는 것 차단).
  - **[LOW] Severity 백업체크** `grep -A1`→`-A2`(헤더-값 사이 빈 줄 대비).
  - 템플릿 + 이미 열린 3개 PR 브랜치(Balipick #616·App #441·chat #21)에 모두 반영.

## 2.7.0 — 2026-07-05

### 추가
- **`reference` 타입 + `project/reference/` — 스냅샷형 참조 문서.** DB 스키마 덤프·API 전수 인덱스·
  아키텍처 다이어그램 등 "현재 시스템 상태의 캡처"를 두는 LIVE 타입. "할 일"(backlog)이나 "구현
  계획"(spec)이 아니라 "지금 어떻게 생겼나"라, **완료/미완료가 없고 최신 vs 드리프트(stale)만 있다** —
  따라서 `dw_resolve`/archive 대상이 아니다.
  - **`dw_write_reference(scope, title, body, source)`** — `project/reference/{slug}.md`(날짜 없는
    파일명)로 기록. 드리프트 시 **같은 title 로 다시 부르면 덮어써 교체**(최신 1개 유지, 추출 시점은
    frontmatter `date` 가 추적). 계획/설계면 `dw_write_spec`.
  - `CONTENT_DIRS`·`dw_list` 필터에 `reference` 추가(dw_search·dw_list 로 조회). `_RESOLVABLE_DIRS`
    에는 **미포함**(reference 는 resolvable 아님).
  - seed `project/reference/`(archive/ 없음 — 라이프사이클상 불필요), VAULT-STRUCTURE 에 타입·분류
    규칙·라이프사이클 문서화.

## 2.6.0 — 2026-07-05

### 추가
- **GitHub Actions Claude PR 리뷰어(선택 기능).** 11단계 ⑥(PR + 리뷰 + CI)를 CI 에서 자동화하는
  Claude 기반 PR 리뷰 워크플로우를 플러그인이 저장소에 설치할 수 있다. PR 이 열리거나 갱신되면
  `anthropics/claude-code-action` 이 PR 브랜치를 checkout 한 워킹트리에서 코드를 읽어 인라인 코멘트 +
  최종 요약(PASS/FAIL 판정)을 남기고, 불합격이면 `review` job 이 실패한다(브랜치 보호 required check 에
  넣으면 리뷰 통과 전 머지 차단).
  - **`assets/gh-workflows/dw-pr-review.yml`** — generic 템플릿. 리뷰 기준을 특정 언어에 묶지 않고,
    리뷰어가 저장소에 커밋된 거버넌스(`.claude/skills`·`.claude/dw-checks.json`·`CLAUDE.md`)를 먼저
    발견해 그 기준으로 리뷰하고 없으면 일반 시니어 원칙으로 폴백(레포마다 커밋 상태가 달라 자기적응형).
    검증된 verdict 기계장치(이번-commit review-sha stale 코멘트 가드·응답 부재 시 fail-safe FAIL·
    severity 판정)는 보존. 인증은 **Claude Pro/Max OAuth 토큰**(`CLAUDE_CODE_OAUTH_TOKEN` — 별도 API
    과금 없이 구독으로).
  - **`_build/dw-ci-review.py`** — `.github/workflows/dw-pr-review.yml` no-clobber 설치(저장소 소유
    커밋 코드라 install-project 재생성·seed 대상이 아님). `--project`·`--apply`.
  - **`/dw-ci-review` 커맨드** — 저장소별 옵인 설치 + 사람 작업(토큰 시크릿·커밋·브랜치 보호) 안내.
  - **`/dw-setup`** 에 선택 단계로 편입(설치 시 옵셔널), `/denver-workflow` ⑥단계에 옵션 언급.

## 2.5.2 — 2026-07-05

### 추가
- **계약 sign-off·차단성 플래그.** `dw_write_contract` 에 `signoff`(`pending`|`agreed` — 양측 최종
  합의 여부)·`blocking`(`blocking`|`non-blocking` — 소비측 차단 여부) 파라미터 추가. 기존엔 계약을
  읽어도 **합의 상태·차단성을 구조적으로 알 수 없어** 본문 산문에 묻혔던 것을 frontmatter 필드로
  구조화한다(`status` 는 비준상태라 이 용도가 아님). `dw_list` 가 계약의 `signoff`/`blocking` 을
  항목별로 노출(다른 타입엔 없으니 노이즈 0). 안전 기본값 `pending`·`blocking`. 잘못된 값은 거부.
  - 오케스트레이터 §5(교차레포 계약 흐름)를 "sign-off·차단성은 `signoff=`/`blocking=` 파라미터로 명시,
    `dw_list` 로 상태 조회"로 갱신. 요청=`pending`, 합의된 최종 계약=`agreed`.

## 2.5.1 — 2026-07-05

### 추가
- **`dw_resolve(name, resolution)` — LIVE 프로젝트 산출물 완료/적용 처리.** backlog·spec·contract 는
  모두 `status:stable`(비준상태)만 있어 **완료/미완료·적용 여부를 표시할 수 없던** 갭을 닫는다. 항목을
  해당 폴더의 `archive/` 로 옮기고 본문에 `**완료/적용:** {resolution} ({날짜})` 를 남긴다. `_iter_notes`·
  지식 인덱스·세션 다이제스트가 `archive/` 를 이미 제외하므로 **활성 뷰(dw_search·dw_list)엔 미완료만**
  남고, 완료분은 경로로 직접 `dw_read` 하면 이력이 보존된다. 대상: backlog(완료)·spec(구현/적용 완료)·
  contract(완결). memory·decision 은 완료 개념이 없어 제외.
  - `dw_write_backlog`·`dw_write_spec` 도크스트링에 완료 시 `dw_resolve` 안내 추가. `dw_write_contract`
    는 기존 "완결분 archive 이동" 약속을 실제 도구(`dw_resolve`)로 연결.
  - `no-project-backlog-files` rule 에 완료 라이프사이클(dw_resolve) 명시. seed `project/backlog/archive/` 추가.

## 2.5.0 — 2026-07-05

### 추가
- **vault 전용 backlog + 프로젝트 Backlog 파일 금지(rule).** 후속·백로그 항목을 프로젝트 repo 에
  `BACKLOG.md`·`TODO.md` 류로 흩뿌리면 worktree 청소·브랜치 삭제 시 휘발하고 팀·다음 세션이 못 본다 —
  대신 **vault SSOT** 로 남긴다.
  - 새 MCP 도구 **`dw_write_backlog(scope, title, item, context)`** — vault `project/backlog/` 에
    LIVE(status:stable)로 기록, `dw_search`·`dw_list(note_type=backlog)`로 즉시 조회. memory 패턴(비준 불요).
  - 새 rule **`no-project-backlog-files`**(enforced-by: code-review) — repo 에 백로그 파일 작성 금지,
    vault backlog 로 유도. README·CHANGELOG·인라인 `// TODO` 주석은 대상 아님(경계 명시).
  - `dw-artifact-guard.py`(PostToolUse)가 vault 밖 `backlog`/`백로그` 파일 쓰기를 감지해
    `dw_write_backlog` 로 유도(차단 아님, additionalContext). generic todo 는 노이즈라 제외.
- **코드 탐색 Grep→graphify MCP 게이트.** `dw-graphify-gate.py`(PreToolUse)가 이제 `Grep` 도구도 가로챈다 —
  패턴이 **심볼형**(식별자·점경로)일 때만 "raw grep·graphify CLI 대신 세션 graphify MCP(`query_graph`/
  `get_neighbors`, `project_path`)로" nudge. 리터럴 문자열·정규식·구절(에러메시지·설정키·주석)은 AST
  그래프가 답 못 하니 **침묵**(과다발화로 무시당하는 것 방지). graphify 미등록 세션 무영향(불변식).

### 변경
- **guidance `graphify-search`** — 코드 **구조** 탐색은 세션 graphify **MCP**(CLI 셸아웃·raw grep 아님),
  grep 은 리터럴 문자열 전용임을 명시. `hooks.json` 에 PreToolUse `Grep` 매처 추가.

## 2.4.3 — 2026-07-04

### 추가
- **dw_search 가로채기 게이트** — graphify 활성 세션에서 `dw_search`(substring) 호출 **직전**에
  PreToolUse 훅(`dw-graphify-gate.py`)이 "graphify(`query_graph`/`project_path`)로 먼저 발견했는가"를
  additionalContext 로 주입(차단 아님, self-correct 유도). SessionStart 1회 nudge(2.4.2)보다 강한 개입
  시점 — 매 dw_search 시도마다 발화. `dw_read`(원문 확정)는 매처에서 제외(정상 흐름 방해 방지).
  프로젝트 `.mcp.json` 의 graphify 등록으로 게이트 — 미등록 세션 무영향(불변식).

## 2.4.2 — 2026-07-04

### 수정
- **오케스트레이터의 graphify proactive 사용 강화(구조적 nudge).** graphify 활성 세션에서도 vault
  dw_search/dw_read 를 먼저 쓰는 문제 — digest 가 vault-일색(memory·계약·스펙 인덱스가 dw_read 로 유도,
  graphify-search 는 중간에 묻힘)이라 별도 guidance·§1 문구로는 부족했다. SessionStart 훅이 **graphify
  등록 세션(`.mcp.json`)에서만** 주입 컨텍스트 **최상단**에 "지식·코드 탐색은 graphify 그래프 먼저,
  아래 인덱스의 dw_read 는 발견 후 원문 확정용" 지시를 prepend — vault-일색 인덱스의 pull 을 읽기 순서
  최상위에서 상쇄. graphify 미등록 세션엔 미주입(불변식 유지). 컴파일러가 아닌 훅에서 처리(런타임
  등록 상태를 알아야 옵셔널 불변식을 지킴).
  ※ 프롬프트 기반 유도라 **보장이 아닌 nudge** — 확정적 강제는 프롬프트로 불가.

## 2.4.1 — 2026-07-04

### 추가
- **graphify 가시성 태그 복원** — SessionStart systemMessage 에 프로젝트 `.mcp.json` 에 graphify MCP
  서버가 등록돼 있으면 ` · 🕸 graphify` 표시. v2.3.0 에서 CLI-안내를 MCP 로 교체하며 태그가 사라졌던 것을
  MCP 모델에 맞게 되살림 — **가시성 표시만**(additionalContext 주입 없음), `.mcp.json` 등록 여부로 감지
  (graphify 바이너리 PATH 비의존). 미등록 프로젝트엔 표시 없음(무영향).

### 수정
- **오케스트레이터가 문서 탐색에 graphify 를 기본으로 쓰도록** `dw-orchestrator` §1 강화. 기존 §1 은
  LIVE pull 에 `dw_search` 만 명시해, graphify 활성 세션에서도 vault(substring)를 먼저 쓰는 문제가 있었다.
  이제 `🕸 graphify` 활성 시 지식·문서·계약 탐색은 graphify 그래프 우선(`query_graph`/`get_neighbors`,
  코드는 `project_path`), 원문 확정만 `dw_read`, graphify 미활성 시에만 `dw_search` 로 명시.

## 2.4.0 — 2026-07-04

### 추가
- **멀티레포 graphify 1급(옵셔널) 반영.** graphify 감지 시: (A) 지식=vault 기본 그래프 / 코드=레포
  `project_path` 라우팅 명문화(서버가 project_path 네이티브 지원), (B) `dw-graphify-register --apply` 가
  대상 레포 `.gitignore` 에 `graphify-out/` 자동 추가(additive·멱등) + 네이티브 혼재(Flutter/node) 시
  `.graphifyignore` 스캐폴드 제안(옵트인 `--graphifyignore`), (C) guidance 에 지식/코드 라우팅·AST-전용·
  INFERRED 근거인용 금지·global 신뢰 금지 명시, (D) graphify 자체 installer 의 CLAUDE.md 블록 관련 안내.
- **불변식**: graphify 미설치/그래프 미빌드 시 100% 무영향 — MCP 미등록·레포 파일 무변경·에러 0.
  모든 동작은 감지 게이트(`detect()`) 아래.

## 2.3.1 — 2026-07-04

### 추가
- **에이전트가 지식 탐색 시 graphify 우선** — 신규 guidance `graphify-search`(digest 상시 주입):
  graphify MCP 도구가 세션에 있으면 substring `dw_search` 보다 `query_graph`·`shortest_path` 등을
  우선하고, 없으면 폴백. 설치 에이전트는 `tools:` 없이 emit(전체 상속)돼 graphify 도구를 자동 획득 —
  오케스트레이터·do-er 모두 활용. 오케스트레이터는 디스패치에도 이 우선순위를 relay.

### 수정
- `dw-graphify-register` 그래프 해석에 **vault 그래프 폴백** 추가 — 프로젝트 로컬 `graphify-out/graph.json`
  이 없어도 `<vault>/graphify-out/graph.json`(vault 에 ingest 한 지식 그래프)을 자동으로 찾는다
  (vault 해석은 dw-config `vault_root` > `DW_VAULT_DIR` > 규약 경로 순, 런처와 동일). 이전엔 `--graph`
  를 명시하지 않으면 balipick 처럼 vault-ingest 사용 환경에서 "등록 스킵"이 됐다.
- README: graphify 연동을 전용 섹션(MCP·그래프 해석·노출 도구·에이전트 활용)으로 재작성.

## 2.3.0 — 2026-07-04

### 변경
- **graphify 통합을 CLI-안내(2.2.x) → MCP 서버 등록으로 전환.** graphify 는 CLI 조회뿐 아니라 MCP
  stdio 서버(`graphify.serve`)를 제공한다 — 이를 프로젝트 `.mcp.json` 에 등록하면 `query_graph`·
  `shortest_path`·`get_neighbors` 등 **네이티브 그래프 도구**가 세션에 노출돼, 2.2.x 의 SessionStart
  CLI-안내 주입(`explain`/`path`)보다 깔끔하고 풍부하다.
- 제거: `dw-session-context.py` 의 graphify 감지·주입, `dispatch-discipline`/`dw-orchestrator §3` 의
  graphify relay 항목(2.2.0/2.2.1).

### 추가
- `/dw-setup` 옵인 단계 + `_build/dw-graphify-register.py` — graphify 감지 시 프로젝트별 `.mcp.json` 에
  등록(mcp SDK 는 `pipx inject` 로 확보, 기존 mcpServers 키 보존 병합). optional 이라 전역 plugin.json
  미포함, 미구축 환경엔 무영향.

## 2.2.1 — 2026-07-04

### 추가
- **graphify 안내를 서브에이전트 디스패치에 전파** — SessionStart 주입은 메인 세션에만 닿고 Task 로
  디스패치된 do-er 컨텍스트엔 안 닿는다. graphify 가 활성인 세션이면(`🕸 graphify` 블록 존재)
  디스패처가 디스패치 프롬프트에 "자료 탐색 시 `graphify explain`/`path` 를 `dw_search` 보다 우선"을
  graph.json 경로와 함께 relay 하도록, `dispatch-discipline` guidance 와 `dw-orchestrator` §3 에
  조건부 항목 추가. graphify 미활성 환경이면 조건이 거짓이라 무영향.

## 2.2.0 — 2026-07-04

### 추가
- **선택적 graphify 연동** — `graphify` CLI 와 `graphify-out/graph.json` 이 둘 다 감지되면
  SessionStart 시 세션 컨텍스트에 시멘틱 탐색 안내를 주입한다(자료를 찾을 때 substring `dw_search`
  대신 `graphify explain`/`path` 를 그래프 위에서 우선, 실패 시 `dw_search` 폴백). graphify 환경이
  없으면 완전히 무시(현행 동작 무변경) — 팀 공용 설치자 대다수에 영향 없음. 훅 시점 subprocess
  없이 파일 존재만 검사하며, 감지 실패는 조용히 무시해 digest 주입을 막지 않는다.

## 2.1.2 — 2026-07-04

### 수정
- **vault 기록 실패 근본 수정** — 매니페스트 개명(`.ssot-agents.json`→`.dw-agents.json`)으로
  추적 이탈한 1.x do-er 에이전트가 죽은 `ssot_write_*` 도구 grant 를 문 채 방치돼, 디스패치돼도
  `dw_write_*` 를 못 써 vault 기록이 조용히 실패하던 문제. 파일명은 멀쩡하고 내용만 stale 이라
  파일명접두 정리·vault전용 치환 양쪽 그물을 통과하던 사각을 메움:
  - `dw-migrate-vault` `--project` 모드 — 설치된 `.claude/agents/*.md` 의 죽은 식별자를 `dw_*` 로
    제자리 치환(skills 는 재설치가 재생성, agent-memory 는 사용자 데이터라 제외).
  - `/dw-install`·`/dw-setup` 레거시 감지를 파일명 접두(`ssot-`) → 내용 grep 으로 확장.

### 추가
- **디스패치 규율 강화** — `dw-orchestrator` §3 디스패치 프롬프트에 브랜치/워크트리 격리 강제 +
  마감 기록 지시, §4 do-er 학습 취합, §6 기록 규율 강화. 신규 `dispatch-discipline` guidance
  (digest:full — 절대경로·워크트리·대상레포 checks·마감 기록, 세션 유형 무관 항상 주입).

### 정합성
- `marketplace.json` metadata 설명의 구 제품명 `Denver Agent` → `Denver AI Workflow` 정정.

## 2.1.1 — 2026-07-04

### 수정
- venv 부트 스킵 버그 — 플러그인 설치가 stale `.venv/.stamp`(바이너리 없이)를 배포하면
  `make` 가 venv 를 이미 부트된 걸로 오판해 `install-project`/`dw-install` 이
  `.venv/bin/python: No such file` 로 실패하던 문제. `.stamp` 를 실제 바이너리 `$(VPY)` 에
  의존시켜 바이너리 부재 시 재생성하도록 교정.

## 2.1.0 — 2026-07-04

### 추가
- `/dw-setup` 레거시 정리 보강 — 로컬 훅·settings 배선 제거, 커스텀 vault 경로 감지,
  `dw-migrate-vault` 구 이름 리터럴 치환 스크립트.

### 수정
- `make` 가 `DW_VAULT_DIR` 의 리터럴 `$HOME` 을 못 풀어 vault 경로가 깨지던 버그 교정
  (`install-project`/`dw-setup` 실패 원인).

## 2.0.0 — 2026-07-03 (브레이킹)

팀 공용 전환 릴리스. **1.x 에서 올리는 경우 아래 마이그레이션 필수.**

### 변경
- **이름 전면 변경 `ssot-*` → `dw-*`**: 에이전트(dw-governed·dw-orchestrator·dw-ratifier),
  커맨드(/dw-build·/dw-install·/dw-ratify·/dw-review·/dw-scope), MCP 서버(dw-vault)·도구(dw_*),
  검사/다이제스트 파일(.claude/dw-checks.json·dw-session-digest.md).
- **플러그인·마켓플레이스 이름**: `denver-agent` → `denver-workflow`.
- **vault 규약 경로**: `~/denver-agent-vault` → `~/denver-workflow-vault`
  (env `DENVER_VAULT_DIR` → `DW_VAULT_DIR`).
- **신규 `/dw-setup`**: 초기 설정 도우미 — 외부 프로그램(Obsidian·superpowers·impeccable·gstack)
  설치 대행, vault 준비, 프로젝트(신규/기존/멀티레포) 설치까지 한 번에.
- SessionStart 가 설정 미완료를 감지해 `/dw-setup` 을 안내. 실행 중 미설치 의존은 자가치유.
- 특정 프로젝트 종속 잔재 전면 제거 — 완전 범용 플러그인.

### 1.x → 2.0 마이그레이션 (1회)
1. 구 플러그인 제거: `claude plugin uninstall denver-agent@denver-agent`
2. 신 설치: `claude plugin marketplace add https://github.com/denvernext80/Denver-Workflow`
   → `claude plugin install denver-workflow@denver-workflow`
3. 세션에서 `/dw-setup` 실행 — 구 산출물(`ssot-*`)과 구 vault 경로를 감지해 정리·이전을 안내한다.
