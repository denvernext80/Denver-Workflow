# Changelog

## 2.13.0 — 2026-08-08

비준이 **언제 어떻게 도는가**를 정한다. 두 시점으로 쪼갰다 — 제안 시엔 **검증만**, 세션 시작 시
**승격+설치**.

### 수정 — `make ratify` 가 위임만 하고 아무도 설치하지 않았다

`dw-ratify.py` 는 스스로 *"이 스크립트는 status 만 바꾼다 — 실제 컴파일·설치는 **호출자(make
ratify)가 한다**"* 고 적어놨다. 그런데 `ratify` 레시피는 스크립트 실행 + **`@echo` 두 줄**이
전부였다. compile 도 install 도 없는데 help 문구는 "→ 항상 compile+install" 이라고 주장했다.
실증: 승격 후 사람이 `make install-project` 를 4번 손으로 돌려야 검사가 14→15건이 됐다.
**책임을 호출자에게 넘겼는데 호출자는 안내문만 출력하던** 형태다(이번 세션에서 네 번째로 만난
"주석·문구가 코드보다 더 주장하는" 결함).

- `_build/dw-install-registered.py` 신설 — 레지스트리(`<vault>/.dw-state/projects.json`)의 모든
  프로젝트에 compile+install(멱등). `ratify` 레시피가 이제 **실제로** 이걸 호출한다.
- 경계 정책(의도적 선택):
  - 레지스트리 **비었음** → 경고, exit 0. 요청된 일이 없으므로 실패가 아니다.
  - 등록 경로 **사라짐** → 경고 + 제거 방법 안내, exit 0. 삭제된 레포 하나가 매 실행을 빨갛게
    만들면 아무도 로그를 안 보게 된다(게이트가 의미를 잃는 그 형태). 자동 제거는 상태를 조용히
    바꾸므로 하지 않고, 매 실행 보고서에 계속 드러낸다.
  - 설치 **실패** → 남은 프로젝트를 계속 처리, 끝에 모아 보고, **exit 1**. 부분 실패를 성공으로
    넘기지 않는다.
- 비준기가 0/10 이 아닌 코드로 죽으면 그 사실을 출력한다(종전 `-` 접두는 크래시를 숨겼다).
- **help 문구·주석을 코드와 일치시켰다.**

### 추가 — 제안 시점에 검증 결과를 즉시 돌려준다(승격은 하지 않는다)

`dw_propose_rule` 이 check 패턴을 받으면 **비준기와 동일한 검증**을 그 자리에서 돌려 반환 문구에
예측을 담는다. 종전엔 제안자가 며칠 뒤에야 보류 사실을 알았다.

- `_build/dw_verify.py` 신설 — 검증의 **단일 정본**. 비준기와 제안 시점이 같은 코드를 쓴다
  (구현이 갈라지면 예측과 실제가 어긋나 예측이 없는 것보다 나쁘다. 테스트로 일치를 고정했다).
- 매치에는 **파일:행**을 함께 낸다 — 어느 해석인지 판단하려면 그 줄을 봐야 한다.
- **문구 규율(테스트로 고정)** — 비준기 자신의 계약(`dw-ratify.py:7,14`: *"진짜위반인지 오탐인지는
  판단 필요"*)을 반환 문구도 지킨다:
  - **매치를 「오탐」으로 단정하지 않는다.** 패턴이 잘못됐을 수도, 기존 코드가 실제로 규칙을
    어겼을 수도 있고 **조치가 정반대다**(패턴 수정 vs 코드 수정·예외 명시). 두 해석과 각 조치를
    함께 제시하고 판단은 사람·LLM 에 남긴다.
  - **검사대상 N 을 반드시 함께 낸다** — "위반 0" 만으로는 아무것도 검사하지 않은 0 과 구분되지
    않는다(stable 규칙 「0건을 성공으로 보고하는 게이트 금지」).
  - **hold 를 거절·실패로 읽히게 쓰지 않는다** — 실제 의미는 "자동 승격 보류, 판단 필요" 이고
    원인이 해소되면 다음 비준에서 승격되며 `<!-- ratify-hold: -->` 주석도 자동 제거된다.
    문구가 이를 오해시키면 제안자가 규칙을 포기해 버린다.
  - 검사대상 0 도 **원인별로 갈라** 안내한다(레지스트리 미등록 vs glob 이 아무것도 잡지 못함).
- 예: `검증 예측: 기존 코드에 3건 매치(검사대상 41건) — 이대로면 자동 승격이 보류됩니다(거절이
  아니라 '판단 필요'). 매치가 패턴 문제면 check_deny 를 좁히거나 check_exclude 로 예외를 주고,
  실제 위반이면 코드를 고치거나 예외를 명시하세요 … 매치: app/lib/a.dart:42: 금지패턴 /…/ 매치` /
  `검증 예측: 검사대상 1건 · 위반 0 (등록 레포 4개) — 검증 통과 예측. 다음 세션 시작 시 자동 승격`.
- **`status: draft` 는 그대로.** 즉시 승격하지 않는 이유: 승격의 순간을 제안한 에이전트 자신의
  턴 안으로 들이면 경계가 무너진다(규칙은 *다른* 에이전트의 게이트를 규율하고, 비준기는
  "현명한가" 를 보지 않는다). `dw_propose_rule` 독스트링의 "절대 stable 아님" 은 의도적 경계다.

### 추가 — 세션 시작 시 자동 비준 + 설치 (`_build/dw-ratify-session.py`)

승격 결과가 실제로 필요해지는 순간은 **다음 세션이 컴파일 산출물을 읽는 그때**다. 어떤
에이전트의 턴 밖이라 위 경계도 지켜진다.

**호스트 스케줄러(launchd/cron/Task Scheduler)를 쓰지 않는다.** 이 플러그인의 훅은 전부
`python3 <script>` 형태의 **플랫폼 중립**이고, macOS 전용 launchd 를 정본으로 삼으면 OS 의존이
새로 생긴다(Windows·Linux 사용자). 셋을 다 실으면 유지 비용도 3배다.
`StartCalendarInterval`(잠자기 보충·누락 없음)은 launchd 후보 중 최선이었지만, 플랫폼 문제는
그대로다. `WatchPaths` 는 Apple 이 *"highly race-prone… entirely possible for modifications to be
missed"* 로 명시해 **거버넌스 게이트를 그 위에 세우지 않는다** — 이번 세션의 결함이 전부
"오류없이 안 도는 장치" 였다.

예산 규율(SessionStart 훅 `timeout 15`) — **실측**:

| 경로 | 시간 |
|---|---|
| draft 0 · 산출물 최신 → 무작업(대부분의 세션) | **0.03s** |
| draft 1건 승격 + 등록 4레포 설치 | **3.01s** |

- draft 유무를 먼저 값싸게 본다(200 노트 0.013s — 헤더 400바이트만 읽는다).
- **승격이 있을 때만** 등록 레포 전체에 설치한다. 승격이 없고 이 레포 산출물만 낡았으면(사람이
  Obsidian 에서 stable 을 고친 경우) **이 레포 하나만** 설치한다.
- 내부 예산 11s 를 넘기면 설치를 다음 세션으로 넘기고 그 사실을 알린다.
- **조용히 죽지 않는다**: 결과(승격/hold 건수·설치 대상·실패)를 `<vault>/.dw-state/ratify.log`
  (1MB 넘으면 `.1` 로 1세대 회전 — 상한 ≈2MB)와 세션 additionalContext 양쪽에 남긴다.
  hold 가 생기면 세션이 즉시 보게 된다.
- **어떤 예외도 세션 시작을 막지 않는다**(전부 삼키고 exit 0).

### 정리

- `_build/dw_state.py` 신설 — 레지스트리 계약의 단일 정본(소비자 3곳: 비준기·wire-hook·설치기).
  `dw-ratify.py`·`wire-hook.py` 는 이제 여기에 위임한다.
- `make test` 25 → **40 케이스**(사슬 6 · 제안시 검증 4 · 세션 훅 5). 전부 임시 vault 픽스처 +
  임시 프로젝트 — 실제 vault·실제 레포는 건드리지 않는다.

## 2.12.1 — 2026-08-07

### 수정 — 비준기의 "check 패턴을 실제 코드에 돌려 오탐 0" 검증이 **한 번도 실행되지 않았다**

`dw-ratify.py` 는 규칙을 stable 로 승격하기 전에 check 패턴을 기존 코드에 돌려 오탐이 0 인지
확인한다고 문서화돼 있었다(BOOTSTRAP.md·README.md). **세 겹으로 무력했다**:

1. **스캔 대상이 없었다.** 유일한 호출부 `Makefile` 의 `ratify` 가 `--project` 를 넘기지 않아
   `projects=[]` → `scan_codebase` 의 for 루프가 **한 번도 돌지 않고** `hits=[]` → 매치 여부와
   무관하게 **무조건 승격**. 실측 A/B: `--project` 없음 → 승격 1·hold 0(매치가 있는데도) /
   `--project` 지정 → 승격 0·hold 1.
2. **`--project` 를 줘도 iOS/Android 는 안 봤다.** `SKIP` 에 `ios`·`android` 가 있어
   `ios/**/project.pbxproj` 를 노리는 규칙은 **검사 대상이 0 건**이었다. 즉 ①만 고쳐도
   이 사건의 동기였던 dSYM/pbxproj 규칙은 여전히 검증되지 않았다(실측 확인).
3. **검사 대상 0 을 "깨끗함" 으로 보고했다.** 위반 0 은 ⓐ 대상이 있고 깨끗함 ⓑ **대상이 아예
   없음**(검증 불가) 두 가지를 뜻하는데 구분이 없었다. 이미 stable 규칙
   「검증 장치는 비교 대상이 비어있지 않음을 먼저 증명하라 — 0건을 성공으로 보고하는 게이트
   금지」가 있는데, 엔진 자신이 그 규칙을 위반하고 있었다.

**대조 실측** (현 stable dSYM 규칙 `deny:['upload-symbols']`·`glob:['*.pbxproj']`·
`exclude:['ios/Pods/*','legacy/*']` 을 4개 레포에 적용):

| | 위반 | 검사대상 | 시간 |
|---|---|---|---|
| 종전 | 0건 | **0건(공허)** — 반환하지도 않음 | 9.94s |
| 이번 | 0건 | **1건** (`balipick-app/ios/Runner.xcodeproj/project.pbxproj`) | 0.14s |

같은 "0" 이지만 종전은 **아무것도 비교하지 않은 0** 이었다. 오탐 0 이라는 결론 자체가 유효함은
이번에 처음으로 **증명**됐다.

- **스캔 대상 레포의 정본 = `<vault>/.dw-state/projects.json`.** `make install-project`
  (`wire-hook.py`)가 설치 시 자동 등록한다 — 설치가 곧 등록이라 크론·스케줄에서 인자가 필요 없다.
  vault CONTENT_DIRS **밖**이라 검색·graphify·컴파일을 오염시키지 않는다(`dw_access_log.py` 와
  동일 규약). 엔진 코드에 사용자 경로를 하드코딩하지 않는다(`~/.claude.json` 은 한 번도 열지 않은
  레포를 빠뜨려 정본으로 쓸 수 없다 — 실측 3개 중 2개 누락).
  일회성 지정: `make ratify RATIFY_PROJECTS="/abs/repo1 /abs/repo2"`.
- **`SKIP` 을 좁혔다** — `ios`·`android` 를 열고, 그 아래 무거운 산출물·벤더 트리만 계속 건너뛴다
  (`Pods`·`DerivedData`·`.symlinks`·`ephemeral`·`.gradle`·`Carthage`). `ios/` 878 → 102 파일.
  `ios/Pods/` 엔 벤더된 `project.pbxproj` 사본이 3개 있어(실측) 열어두면 그대로 오탐이 된다.
  스캔 성립을 위한 산출물 skip 추가: `target`·`.next`·`coverage`. 또 git worktree 디렉터리
  (`.worktrees`·`_worktrees`)는 같은 코드의 사본이라 검사대상을 부풀리므로 건너뛴다.
- **walk 를 프루닝했다** — `rglob` 전수 순회 + 사후 필터를 `os.walk` + `dirnames` 프루닝으로 바꿔
  SKIP 트리에 **내려가지 않는다**. 규칙 1건당 4레포 **9.94s → 0.14s**(방문 278k → 12k 경로).
  `scan_codebase` 는 규칙마다 호출되므로 종전 방식은 check 규칙 12건이면 순수 walk 만 2분이었다
  — 스케줄 실행에서 죽는 수치다.
- **검증 불가는 통과가 아니라 hold.** 사유를 두 원인으로 갈랐다(조치가 다르므로):
  `스캔 대상 프로젝트 0`(레포 등록 필요) vs `검사대상 파일 0건`(glob 오타 또는 대상이 아직 없는
  선제 규칙 → 사람 승인 필요). hold 는 기각이 아니라 `dw-ratifier`/리뷰 큐로 가는 「판단 필요」다.
- **승격에도 근거를 남긴다** — `검사대상 N건 · 위반 0` 을 출력한다. "무엇에 비추어 0 인가" 없이
  0 을 보고하지 않는다. 실행 머리에 스캔 대상 레포 목록을 먼저 찍는다.
- **큐 정체 방지** — 이 게이트는 **check 패턴이 있는 규칙에만** 적용된다. 검사 없는 서술 규칙·
  guidance·procedure 는 검증 대상이 없으므로 스캔 대상 0 이어도 정상 승격된다(테스트로 고정).
- **이미 stable 인 규칙은 소급 강등하지 않는다** — 앞으로의 승격 판정만 바뀐다.

`make test` 16 → **25 케이스**(비준 게이트 9건 추가: A/B 재현, glob 0매치 hold, 스캔대상 0 hold,
검사 없는 OBEY 무영향, pbxproj 는 스캔되고 Pods 사본은 제외, 프루닝, 설치-등록 멱등, 레지스트리 격리).

> **업데이트 후 조치** — 레지스트리는 설치 시 채워진다. 각 레포에 `/dw-install`(또는
> `make install-project P=/절대경로`)을 한 번 돌려 등록하라. 등록 전에는 check 패턴을 가진 규칙이
> "스캔 대상 프로젝트 0" 사유로 hold 된다(조용히 승격되지 않는다 — 의도된 동작).

## 2.12.0 — 2026-08-07

> ⚠️ **업데이트 후 조치 — `.venv` 를 가진 환경은 `make distclean` 이 필요할 수 있다.**
> 이 릴리스 전에 만들어진 venv 는 `mcp` **2.0.0** 을 들고 있을 수 있고, 2.0.0 은
> `mcp.server.fastmcp` 를 제거해 **dw-vault MCP 서버가 기동하지 못한다**. 아래 핀은 *새로 만드는*
> venv 만 고친다(`$(VENV)/.stamp` 는 stamp 가 있으면 재설치하지 않고, 런처도 python 부재만 본다).
> 증상: dw-vault 도구가 세션에 보이지 않음 / 서버 spawn 실패.
> **해법: `make distclean` 후 재빌드**(플러그인 설치본이면 플러그인 캐시의 `.venv` 삭제 — 런처가
> 다음 spawn 때 핀으로 다시 만든다).

### 추가 — `dw_propose_rule` 이 결정론 검사를 제안할 수 있게 됐다 (규칙만 남고 강제는 0 이던 결함)

`dw_propose_rule` 은 프론트매터를 **고정 딕셔너리**로 만들어 `check-*` 를 넣을 파라미터가 없었다.
컴파일러 `collect_checks` 는 그 키를 **프론트매터에서만** 읽으므로 에이전트가 결정론 검사를 제안할
경로가 **아예 없었다**(본문에 yaml 로 적어도 무시). 우회는 SSOT 가드가 차단한다 — 정상 동작이지만
정상 경로가 없으니 막다른 길이었다.

실증: 2026-08-07 dSYM 규칙 보강 제안이 stable 까지 갔는데도 `dw-checks.json` 의 pbxproj glob 항목은
**0 건**. "규칙은 생겼는데 검사는 없는" 상태 — stable 규칙 「0건을 성공으로 보고하는 게이트 금지」와
같은 실패형이다.

- 옵션 파라미터 5개 — `check_deny`·`check_require`·`check_glob`·`check_exclude`(리스트) +
  `check_hint`(문자열). 주어졌을 때만 프론트매터에 기록한다.
  `check_require` 를 포함한 이유: `collect_checks` 는 `deny or require` 가 있어야 항목을 만들어서,
  deny 만 열면 검사 어휘 절반이 계속 닫힌 채 남는다.
- **`status: draft` 불변.** 이 도구는 stable 을 만들 수 없다(비준은 사람·비준기 몫).
  검사는 규칙이 stable 로 비준된 뒤에만 생성된다(`is_compilable_rule`).
- **입구 가드 3종** — 죽은 검사 양산 방지:
  ① deny/require 를 주면서 `check_glob` 이 없으면 거부(컴파일러가 warn 후 검사 비활성 → 규칙만 남음)
  ② 정규식이 `re.compile` 되지 않으면 거부(dw-lint 의 `re.finditer` 가 모든 프로젝트·모든 파일에서 터진다)
  ③ 패턴 없이 `check_glob`/`check_exclude`/`check_hint` 만 주면 거부(항목이 생성되지 않고 경고조차
  없어 '검사처럼 생긴 죽은 키' 만 남는다)
- 하위호환 — `check-*` 를 프론트매터 **맨 뒤에** 조건부로 붙여, 파라미터 미제공 시 산출물이 종전과
  **바이트 동일**하다(이전 버전 서버와 md5 대조 확인). 반환 문구에는 새 기능을 알리는 한 문장이 붙는다.
- ⚠️ **MCP 도구 스키마는 서버 재시작 후 세션에 반영된다** — 스키마는 클라이언트가 서버를 spawn 할 때
  읽힌다. 기존 세션은 계속 옛 시그니처를 본다.

### 수정 — 콜드스타트가 깨진 MCP 서버를 설치하고 있었다

`pip install mcp` 가 이제 **2.0.0** 을 가져오고, 2.0.0 은 `mcp.server.fastmcp` 를 **제거**해
`dw-mcp-server.py` 가 임포트에서 즉사한다. 신규 venv 에서만 발현해(기존 venv 는 1.x 보유) 무증상이었다.

- `Makefile`(`$(VENV)/.stamp`)·`_build/dw-mcp-launch.sh` 양쪽에 **`mcp<2` 핀**. 서버를 2.x API 로
  마이그레이션한 뒤에만 해제(두 곳을 반드시 함께 유지).
- 이미 오염된 venv 는 이 핀으로 치유되지 않는다 — 위 상단 조치 안내 참조.

### 추가 — `make test`(엔진 자기검사) 신설

레포에 테스트 하네스가 없었다(pytest·pyproject·conftest 부재). venv 에 의존성을 추가하지 않는
**stdlib unittest** 로 `_build/dw-selftest.py` 를 만들고 `make test` 로 노출했다. 픽스처는 `_seed`
복사본(`make seed-check` 가 strict 컴파일을 이미 보증) — **사용자 vault 는 읽지도 쓰지도 않는다.**

16 케이스: 왕복(제안 → 프론트매터 5키 → 컴파일 → `dw-checks.json` 항목 실재 → **dw-lint 실제 발화**),
draft 동안 검사 0, 파라미터 미제공 시 바이트 동일, 거부 6종, MCP 스키마에 옵션으로 노출.

`make dry-run`·`make doctor` 는 live vault 를 컴파일할 뿐 엔진 동작을 증명하지 못한다(무회귀만) —
그 몫이 `make test` 다.

## 2.11.7 — 2026-08-07

### 수정 — SSOT 쓰기 가드의 guidance 안내가 「금지」로만 끝나 사용자 지시까지 거절시켰다

`TOOL_HINT` 세 항목 중 **guidance 만 대체 경로가 없었다**. rule 은 `dw_propose_rule`, procedure 는
`dw_write_procedure` 를 안내하는데, guidance 는 전용 쓰기 도구가 없다는 이유로 `"에이전트 직접편집
금지."` 로 끝났다. 뒤에 붙는 `"(정말 직접 편집이 필요하면 override.)"` 는 **주체가 없어** 누가 무엇을
푸는지 알 수 없었다.

결과: 이 가드는 대화형에서 `ask`(= 사용자 결정 요청)인데도 에이전트가 「금지」로 읽고, 사용자가
명시적으로 지시한 편집까지 **스스로 포기하고 사용자에게 패치 붙여넣기를 요구**했다(2026-08-07 실측,
왕복 1회 낭비). 강제력이 아니라 **문구가 만든 과잉 준수**다.

- `TOOL_HINT["guidance"]` — 원칙(사람 저작)만 남기고 「금지」 단정 제거.
- soft(`ask`) tail — "사용자가 승인하면 그대로 진행된다. '못 한다' 가 아니라 '승인해 주시면 넣겠다'
  로 요청하라" 로 **주체와 행동**을 명시.
- hard(`deny`) tail — "승인자가 없으니 올바른 경로로 재시도하라" 로 분리.
  ⚠️ 승인 안내를 모드 무관한 `TOOL_HINT` 에 두면 automode 에서 "승인받아라 / (차단)" 자기모순이
  된다 — 초안에서 실제로 그렇게 만들었다가 실행 검증으로 잡았다. 모드별 문구는 `tail` 에만 둔다.
- docstring — `ask` 는 금지가 아니라 사용자 결정 요청임을 명시.

**강제 로직(`_hard`·`permissionDecision`)은 무변경.** 차단 범위는 그대로다 — 문구만 바꿨다.

## 2.11.6 — 2026-08-07

### 수정 — graphify 게이트가 「관측 불가」를 「위반」으로 읽어 automode 를 영구 차단하던 결함

`_graphify_used_this_session()` 은 **두 경우 모두 False** 를 돌려준다: ① 로그가 있는데 이번 세션
graphify 이벤트가 없다(= 진짜 미사용) ② **로그 파일이 아예 없다**(= 관측 불가). 호출부가 이 둘을
구분하지 않아, ②에서도 게이트가 발화하고 automode 에선 `deny` 가 됐다.

**이건 영구 차단이다.** 텔레메트리와 이 게이트는 같은 릴리스(2.11.2)에 실렸지만 훅은 새 세션부터
로드되므로, `access.jsonl` 이 한 번도 안 써진 창이 **반드시** 생긴다. 그 창에서 automode 서브에이전트는
`dw_search` 를 열 방법이 없다. 2026-08-07 실측: 서브에이전트가 이 게이트에 막혀 vault 를 직접 뒤져
우회했고, 우회 사실을 백로그로 보고해서야 드러났다.

`_telemetry_observing(vault)` 신설(= `access.jsonl` 존재 여부)로 갈랐다:
- 관측 중 + 이번 세션 미사용 → 게이트(종전대로, automode=deny)
- **관측 불가 → 조언(additionalContext)까지만.** 규율은 전하되 근거 없이 막지 않는다.
- 이번 세션 사용 → self-release(종전대로)

⚠️ 이 결함은 이 플러그인이 다른 곳에서 반복해 경고하는 실패의 **역방향**이다 — "0건을 성공으로 보고
하지 마라"(검증 장치가 비어 있는데 통과로 읽는 것)의 거울상으로, **관측이 없는데 유죄로 읽었다.**
게이트를 만들 때는 "무엇을 못 봤을 때 어떻게 행동하는가" 를 명시적으로 설계해야 한다.

검증 5/5: 로그 부재 → `default`·`bypassPermissions` 둘 다 조언 / 로그 있고 미사용 → `ask`·`deny` /
이번 세션 사용 → 조언(self-release).

## 2.11.5 — 2026-08-07

### 수정 — 훅 5종이 워크트리에서 vault 를 못 찾던 잔여 맹점

2.11.4 가 `dw-lint` 의 같은 결함을 닫았고, 이번엔 **나머지 5종**이다:
`dw-vault-guard` · `dw-artifact-guard` · `dw-telemetry` · `dw-vault-write-guard` · `dw-graphify-gate`.

`_vault_root()` 가 `<project>/.claude/dw-config.json` **한 곳만** 봤다. 워크트리는 `.claude/` 가
gitignore 라 그 파일이 없어, 실환경에서는 `DW_VAULT_DIR` **env 폴백에만 의존**해 살아 있었다.
env 가 없는 환경(러너·다른 셸·다른 사용자)에서는 vault 를 못 찾아 훅이 조용히 무력화된다 —
차단이 아니라 무발화라 아무도 모른다.

`_cfg_dirs(project)` 신설: `project` → 조상(최대 8) → **본체 레포**(`git rev-parse --git-common-dir`
의 부모) 순으로 후보를 만들고 첫 번째로 발견되는 `dw-config.json` 을 쓴다. git 실패·타임아웃(3s)·
비-git 디렉토리는 전부 종전 폴백으로 넘어간다(fail-open — 훅은 절대 죽지 않는다).

`except` 절이 파일마다 달라(`(json.JSONDecodeError, OSError)` vs `Exception`) 각 파일의 기존 절을
보존한 채 탐색부만 교체했다.

검증(전부 `DW_VAULT_DIR` **제거** 상태 — 종전이라면 실패했을 조건):
- 5/5 훅이 레포 안 워크트리에서 vault 해석 성공
- 레포 밖 워크트리(`/tmp/...`)도 성공
- 본체 체크아웃 회귀 없음 · 비-git 디렉토리는 `None`(fail-open)
- e2e: 워크트리에서 OBEY 규칙 편집 시 `dw-vault-write-guard` 가 실제로 `ask` 반환

## 2.11.4 — 2026-08-07

### 수정 — dw-lint 가 do-er 워크트리에서 조용히 죽어 있던 결함

`dw-lint` 는 `<project>/.claude/dw-checks.json` 을 읽는데, **워크트리는 `.claude/` 가 gitignore 라
체크아웃되지 않는다.** 매니페스트가 없으면 `return 0` 으로 조용히 통과하므로, **do-er 서브에이전트가
일하는 바로 그곳에서 결정론 검사 전량이 inert** 였다. 오탐이 아니라 무발화라 아무도 못 알아챈다
(실제로 2026-08-07 PR 검증 중 "둘 다 통과" 로 보이는 거짓 green 을 만들어 발견됐다).

`_roots(file_path, payload) -> (work_root, checks_root)` 신설 — **두 루트를 분리**한다:
- `work_root` = `git rev-parse --show-toplevel`. 상대경로 계산 기준이라 워크트리 루트여야
  `lib/main.dart` 같은 rel 이 나오고 경로 glob 이 맞는다.
- `checks_root` = work_root 에 매니페스트가 없으면 `git rev-parse --git-common-dir` 의 부모(본체 레포).

레포 안(`<repo>/.claude/worktrees/x`)·밖(`/tmp/x`) 워크트리 양쪽에서 동작한다. git 이 없거나 실패하면
전부 종전 동작으로 폴백(fail-open — 훅은 절대 죽지 않는다, `subprocess` 타임아웃 3s).

검증 4/4: 레포 안 워크트리→포착(rel `lib/_probe.dart` 정확) · 레포 밖 워크트리→포착 ·
본체 체크아웃→회귀 없음 · git 아닌 디렉토리→침묵.

⚠️ 같은 뿌리의 잔여: 다른 훅들(`dw-vault-guard`·`dw-artifact-guard`·`dw-telemetry`·게이트 2종)은
`dw-config.json` 을 못 찾아도 `DW_VAULT_DIR` env 폴백으로 살아난다 — 그래서 이 결함은 `dw-lint`
단독이었다. env 가 없는 환경에서는 그쪽도 같은 방식으로 죽는다(별건).

## 2.11.3 — 2026-08-07

### 수정 — graphify 게이트가 do-er 워크트리에서 발화하지 않던 구간

게이트가 `cwd/.mcp.json` 만 봐서, do-er 서브에이전트가 `<repo>/.claude/worktrees/<n>` 에서 도는
동안에는 침묵했다. **do-er 는 세션 MCP 를 상속하므로 graphify 를 호출할 수 있다** —
`project_path=<repo 절대경로>` 로 그 레포 그래프를 질의한다(실측: balipick 11,295노드 조회 성공).
즉 능력은 있는데 게이트만 없는 구간이었다.

`_graphify_registered(project)` → `_graphify_applicable(project, vault)` 로 교체:
- ① cwd **와 그 조상**의 `.mcp.json` 에 graphify → 적용(워크스페이스 경로).
- ② 조상에 `graphify-out/graph.json` 이 있고 **텔레메트리 로그에 graphify 이벤트가 있으면** 적용.
  그래프 존재 = 유용함, 로그 이벤트 = 서버가 이 환경에 실재한다는 증거.

②가 사용 증거를 함께 요구하는 이유: graphify 는 옵셔널 불변식이라 미설치 환경을 막으면 안 된다.
그래프 파일만 보고 걸면 서버 없는 환경에서 `dw_search` 가 대안 없이 차단되고, automode 에선 그게
`deny` 라 러너가 멈춘다. 사용 증거가 그 fail-open 을 지킨다.

⚠️ 실환경에서 이 판정은 `DW_VAULT_DIR` 환경변수에 의존한다 — do-er 워크트리엔 `.claude/` 가
gitignore 라 `dw-config.json` 이 없어 `_vault_root` 가 env 폴백으로만 vault 를 찾는다.
(같은 이유로 워크트리에선 `dw-checks.json` 도 없어 dw-lint 가 조용히 통과한다 — 별건.)

## 2.11.2 — 2026-08-07

### 추가 — 워크플로우 텔레메트리 + SSOT 쓰기 가드 + graphify 하드 게이트

진단에서 세 병목이 관측됐고 근본은 하나였다 — **조언(additionalContext)형 훅은 라우팅당한다.**
에이전트는 넛지를 읽고도 원래 하려던 도구를 그대로 호출한다. 강제하려면 PostToolUse(이미 일어난 뒤)
가 아니라 **PreToolUse 에서 결정**을 내려야 한다.

- **텔레메트리**(`dw-telemetry.py`, PostToolUse·비파괴): graphify / dw_* / Grep / vault 파일 접근을
  `<vault>/.dw-state/access.jsonl` 에 기록. 결코 차단하지 않는다(항상 exit 0). vault 밖 코드
  Read/Edit 는 노이즈라 미기록. `dw-workflow-report.py` + `make workflow-report` 로 3대 규율
  준수율과 절차·memory 재사용을 집계한다.
- **SSOT 쓰기 가드**(`dw-vault-write-guard.py`, PreToolUse): OBEY(rule/guidance/procedure) 직접편집
  차단, LIVE(memory/contract/spec/…) 통과. 기존 `dw-vault-guard` 는 PostToolUse 라 구조적으로
  조언만 가능했고 우회를 못 막았다.
- **graphify 게이트 v2**(`dw-graphify-gate.py`): 세션에 graphify 미사용이면 `dw_search`·심볼 grep 을
  차단한다. 한 번 쓰면 텔레메트리 세션 로그로 판별해 조언 모드로 self-release. graphify 미등록이나
  로그 부재 시 침묵(안전 폴백).

**automode 인지**: `permission_mode` 를 읽어 `auto`/`dontAsk`/`bypassPermissions`(쓰기 가드는
`acceptEdits` 도)에서 `ask` → `deny` 로 상향한다. automode 에선 `ask` 가 auto-approve 로 폴백돼
무력화되지만 훅의 `deny` 는 bypassPermissions 에서도 항상 차단된다(훅이 권한모드보다 상위).
`DW_GATE_HARD=1|0` 로 명시 오버라이드 — 러너 런처에 `export DW_GATE_HARD=1` 권장.

`wire-hook.py` 의 `WIRING` 을 event→(matcher, hooks) 단일 튜플에서 **(matcher, hooks) 리스트**로
넓혔다. 같은 PreToolUse 라도 worktree 가드는 `Agent|Task`, 쓰기 가드는 `Edit|Write|MultiEdit` 를
봐야 한다. 멱등성은 마커가 그 이벤트의 어느 그룹에든 있으면 skip 으로 유지.

⚠️ **marketplace.json 이 2.11.0 에 멈춰 있던 것을 함께 정정**했다(2.11.1 릴리스 때 누락). 캐시
갱신은 version 비교로 이뤄지므로 어긋나 있으면 `claude plugin update` 가 조용히 no-op 한다.

관찰(수정 안 함): 텔레메트리의 graphify target 추출이 `query|node|symbol|start` 만 봐서
`query_graph` 의 `question` 을 못 잡아 target 이 빈다. 리포트는 graphify 를 개수만 세고 target 은
vault 노트 재사용 분석에만 쓰므로 기능 영향 0.

## 2.11.1 — 2026-08-03

### 수정 — `dw_search` 가 자연어 질의에 조용히 0 건을 반환하던 결함

`dw_search` 는 검색이 아니라 `grep -F` 였다. 질의 문자열 **전체**를 본문에서 substring 으로만 찾아
(`if q not in text.lower(): continue`), 어순·띄어쓰기까지 정확히 일치해야 잡혔다. 다단어 자연어
질의는 거의 항상 0 건이다.

**피해가 조용하다는 게 핵심이다.** 0 건은 에러가 아니라 정상 응답으로 보이고, 받는 쪽은 "vault 에
없다"로 읽는다. 그 결과 ① 이미 기록된 함정을 다시 밟고 ② 중복 노트를 만든다(SSOT 분기). 백로그
`2026-07-30-dw-vault-도구-신뢰성-2건` 에 3회 독립 재현과 실제 피해(중복 노트 2~3건·함정 재발 1건)가
기록돼 있었다.

수정: 공백 토큰 OR 매칭 + 관련도 정렬. 종전 동작(질의 전체 일치)은 최상위 신호(+10)로 보존해 기존
결과가 밀리지 않는다. 제목 일치 +10, 토큰별 제목 +3 / 본문 +1, 토큰 커버리지 비례 가산.
`if len(out) >= limit: break` 도 제거했다 — 점수·정렬 없이 순회 앞에서부터 채우고 끊어서, 가장 관련
있는 노트가 뒤쪽에 있으면 영영 안 나왔다.

실측(vault 1,934 노트, 재현 질의 7개): 전 4/7 이 0 건 → 후 7/7 정확한 최상위. `API 명세 변경 이력`
은 무관한 노트만 주던 것이 정확한 주제 노트로 교체됐다. 질의당 ~0.35s.

회귀: `dw_list`·`dw_read` 정상, 응답 계약 키 4종(`path`·`type`·`title`·`snippet`) 불변,
빈 질의·공백·미존재 토큰 전부 0 건.

**남은 것**: 같은 백로그의 ②(`DW_VAULT_DIR` 에 확장되지 않은 리터럴 `$HOME`)는 별건으로 미해결.

## 2.11.0 — 2026-07-27

### 추가 — 배치·크론 명세 하네스 (정기 실행 작업을 vault 에 명세로 유지)

2.10.0 의 API 명세 하네스와 같은 구조(노트 3종 · guidance+rule 짝 · 절차 2종 · 커맨드 ·
`/dw-setup` 최초 1회)를 정기 실행 작업에 적용한다. **다만 배치·크론은 API 와 세 가지가 근본적으로
달라 그대로 복사하지 않았다:**

* **정본이 레포 밖에도 있다.** API 의 라우트 정본은 항상 레포 안이지만 정기 실행은 절반이 호스트에
  산다(호스트 크론 목록·레포에 없는 타이머·콘솔에만 있는 클라우드 스케줄러). 명세는 **레포 선언분과
  호스트 설치분을 분리해 세고**, 확인하지 못한 호스트는 `미확인 (최종 확인 YYYY-MM-DD, 사유)` 로
  남긴다. **접근을 얻으려고 보안 설정을 바꾸지 않는다.** 모른다고 적는 것이 없다고 적는 것보다
  정확하다 — 이 도메인 최대 사고는 틀린 명세가 아니라 아무도 모르는 채 도는 잡이다.
* **드리프트 판정이 표면마다 다르다.** 레포 선언분은 "코드가 이긴다"(API 와 동일). 호스트 설치분은
  누가 수동으로 심었을 수 있어 **자동으로 명세를 맞추지 않고 사용자 판단을 받는다** — 조용히
  맞추면 무단 변경이 정본으로 승격된다.
* **비활성도 상태다.** 꺼진 스케줄은 삭제된 스케줄이 아니다. `활성/비활성/보류` 상태와 **끈 사유**를
  기록해 "이거 왜 꺼져 있죠?" 에 답할 수 있게 한다.

구성:

* **명세 3종**: `배치·크론 명세 — 전체 인덱스`(공통 규약 + 표면별 집계 + 호스트 확인 상태) ·
  `배치·크론 명세 — <그룹>` · `배치·크론 명세 — 변경 이력`(append-only).
* **잡 1건 기록 필드**: 선언 표면 · 스케줄 + **타임존** · 실행 호스트 · 실행 대상 · 상태 ·
  중복 실행 정책 · 타임아웃 · 실패 시 동작 · 최종 실측 확인일.
* **읽기 강제** (`guidance/batch-cron-spec-first`, `digest: full`): 공통 규율은 `api-spec-first` 를
  참조하고 **차이점만** 담아 다이제스트 증가를 최소화했다.
* **갱신 강제** (`rule/batch-cron-spec-sync-required`, enforced-by `code-review`).
* **절차 2종**: `batch-cron-spec-bootstrap`(전 표면 탐색) · `batch-cron-spec-update`.
* **do-er 배선**: `senior-infra-engineer` 주담당(조사에서 읽고 마감에서 갱신),
  `senior-backend-engineer` 는 앱 스케줄러 몫으로 읽기+갱신.
* **`/dw-batch-spec` 커맨드**: 드리프트 점검(문서 미수정) · `재추출` · `<그룹>`.
  호스트를 못 본 상태에서는 "일치합니다" 라고 보고하지 않는다.
* **적용 시점이 API 와 다르다**: 코드 머지가 아니라 **실제로 그 스케줄이 도는 상태가 된 때**
  (배포·설치 후)를 기준으로 명세에 반영한다.

*엔진 코드 변경 없음.*

## 2.10.0 — 2026-07-27

### 추가 — API 명세 하네스 (프로젝트 API 전체를 vault 에 명세로 유지)

프로젝트가 제공하는 모든 API 를 vault `project/reference/` 에 **현재 상태 + 변경 이력**으로
유지하고, 모든 API 작업이 명세를 읽고 시작해 갱신하고 끝나도록 강제한다.

* **명세 3종 구조**: `API 명세 — 전체 인덱스`(공통 규약 + 도메인 지도 + 총계) ·
  `API 명세 — <도메인>`(엔드포인트 상세) · `API 명세 — 변경 이력`(append-only).
  인덱스·도메인은 재추출 시 덮어써 최신을 유지하고, 이력은 `dw_read` → prepend → 재기록으로 누적한다.
* **최초 1회 부트스트랩** (`/dw-setup` 4-1): 기존 프로젝트면 API 를 전수 스캔해 명세를 세우고,
  API 가 없으면 빈 명세를 만든다(첫 API 때 갱신 대상이 있도록). 이미 명세가 있으면 덮어쓰지 않고
  안내만 한다.
* **읽기 강제** (`guidance/api-spec-first`, `digest: full`): API 작업 착수 전 인덱스 필독 + 해당
  도메인 상세 열람. 전문이 SessionStart 다이제스트에 항상 주입된다. 읽기 범위를 3줄로 못 박아
  컨텍스트 폭주를 막는다 — `rule` 은 다이제스트에 제목 한 줄만 실려 지시가 세션에 도달하지 않으므로
  읽기 규율은 `guidance` 여야 한다.
* **갱신 강제** (`rule/api-spec-sync-required`, enforced-by `code-review`): API 표면을 바꾼 작업은
  도메인 노트·인덱스 카운트 갱신 + 변경 이력 항목 없이 완료 선언 금지.
* **절차 2종**: `api-spec-bootstrap`(전수 스캔) · `api-spec-update`(델타 → 도메인 → 인덱스 →
  이력 prepend). 스택 무관 서술.
* **do-er 배선**: 공급측(`senior-backend-engineer`)은 조사에서 읽고 마감에서 갱신. 소비측
  (`senior-front-engineer`·`senior-mobile-engineer`)은 **읽기 전용**(양쪽이 고치면 덮어쓰기 사고).
* **`/dw-api-spec` 커맨드**: 인자 없음 = 드리프트 점검(문서 미수정), `재추출` = 전체 재스캔,
  `<도메인>` = 부분 재스캔.
* **`contracts/` 와의 경계**: 계약 = 앞으로 만들 것(협상·완결 시 archive), 명세 = 이미 머지된 현재
  상태. 계약 sign-off·머지(⑨)가 명세 갱신 트리거이며, 별도 GATE 를 신설하지 않고 기존 API 계약
  GATE 의 완료 조건에 편입했다.

*엔진 코드 변경 없음 — 기존 MCP 도구(`dw_read`/`dw_write_reference`)와 컴파일 파이프라인만 사용한다.*

## 2.9.1 — 2026-07-25

### 수정 — 학습이 적은 신규 프로젝트에서 다이제스트가 자기모순으로 읽히던 문구

2.9.0 의 학습 섹션은 **memory 578건 기준**으로 맞춰져 있어, 제네릭 신규 프로젝트(학습 소수)에서
말이 안 됐다. 학습 3건인 vault 로 재현한 실제 출력:

```
## 누적 학습 (memory 3건 — 검색해서 찾는다)
> 제목 전량 나열은 걷었다. … 분포: engineering 3
최근 3건:
- [학습] … (3건 전부 나열)
```

"전량 나열은 걷었다"면서 전량을 나열하고, scope 1개짜리 분포 줄까지 붙는다. 플러그인 대상이
비개발직군이라(사용자 문구 원칙) 이 자기모순은 그대로 혼란이 된다.

- **접히는 꼬리가 없으면 압축한 척하지 않는다** — 학습이 `DIGEST_MEM_RECENT`(20) 이하면 헤더를
  `누적 학습 (memory N건 — 전문은 dw_read(name))` 로 두고 전량을 그냥 나열한다. 검색 안내·분포 줄 없음.
- **꼬리가 있을 때만** 압축 문구를 쓰고, 숫자를 명시한다 —
  `최근 20건만 제목 노출, 나머지 561건은 검색`.
- **분포는 scope 2개 이상일 때만** — 1개면 헤더의 총건수와 같은 말이다.

측정(제네릭 `_seed` 기준, 2.8.2 → 2.9.x): 다이제스트 **150줄/6,748자 → 83줄/4,014자**(−41%),
`dev-engineering-charter` **246 → 205줄**. seed 엔 procedure·memory 가 없어 이득은 전부
조건부 guidance 4건의 `digest: full` 해제에서 나온다 — 즉 2.9.0 의 개선은 balipick 전용이 아니라
**신규 프로젝트에도 그대로 적용된다**(이번에 실측 확인).

검증: `make dry-run`(strict) 에러 0·경고 0 · `make seed-check` 통과 · 학습 3건/581건 양쪽 출력 확인.

## 2.9.0 — 2026-07-25

### 변경 — 컨텍스트 rightsizing (Claude 5 세대 프롬프트 원칙 반영)

컴파일러는 "모델이 스스로 검색하지 않는다"를 전제로 **모든 것을 앞에 싣는** 설계였다. 지금은
`dw_search`·`dw_list`·`dw_read` + graphify 그래프가 있고 모델이 필요할 때 당겨 쓴다 → **항상
로드되는 표면은 압축하고, 전문은 필요할 때 펼치도록** 뒤집는다(progressive disclosure).
vault 노트·frontmatter·비준 상태는 **건드리지 않는다** — 산출 방식만 바뀐다.

- **SessionStart 다이제스트: 484줄/55,288자 → 190줄/16,176자** (실측, balipick scope union)
  - 학습(memory) 제목 **전량 250건 나열 → 분포(상위 8 scope) + 최근 20건**. 나머지는
    `dw_search`/graphify 로 찾는다. scope 는 자유 입력이라 1건짜리 꼬리가 길어(실측 89개)
    상위만 이름을 싣고 나머지는 개수로 접는다.
  - `dw-session-context.py` 의 `MAX_BYTES`(60,000자) 대비 **92% → 27%** — 무성 잘림 위험 해소.
    (직전 상태는 아직 잘리지 않았으나 여유가 약 45건뿐이었다.)
  - **조건부 guidance 4건의 `digest: full` 해제**(vault frontmatter, 사용자 승인) — 각각 조건이
    성립할 때만 필요하고 그 조건을 이미 다른 장치가 정확한 시점에 처리한다:
    `graphify-search`(본문이 "graphify 설치 시"로 시작 + `dw-graphify-gate` 훅이 `dw_search`·`Grep`
    직전에 동일 안내 주입) · `dispatch-discipline`(`dw-worktree-guard` 가 `Agent` 매처로 개입) ·
    `denver-workflow`(`/denver-workflow` 커맨드가 같은 내용 보유) · `dw-dependencies`(`dw-doctor`
    가 SessionStart 에서 미설치 항목 보고). 유지: `karpathy-guidelines`·`artifact-locations`·
    `dw-user-facing-copy`·`tdd-iron-law`(모든 작업에 실제로 걸린다).
  - 제목+요지로만 싣는 guidance 행에 **전문 경로를 명시**(`전문: 스킬 body|vault dw_read(name)`).
    `compiles-to: skill` 이 없는 노트(예: `dw-dependencies`)는 `dw_read` 가 유일 경로라 강등 시
    전문이 사라질 수 있었다.
- **스킬 body 합계: 1,988줄 → 857줄** (`dev-engineering-charter` 854 → 350줄)
  - `procedure` 는 특정 작업에서만 필요한 긴 단계 문서 → **`references/<노트>.md` 로 분리**하고
    body 엔 제목+요지+경로 인덱스만. "TDD 규율 보러 왔는데 iOS 제출 절차까지 읽는" 상태 제거.
    charter 는 절차 22건이 references 로 내려갔다.
  - `digest: full` guidance 는 다이제스트로 이미 항상 주입된다 → 스킬 body 엔 포인터만(중복 제거).
    `digest: full` 표기 자체는 그대로 존중한다(노트 저자의 의도적 선택).
  - vault 에서 사라진 절차의 `references/` 잔재 파일 정리 추가(`clean()` 은 스킬 디렉터리 단위라
    살아 있는 디렉터리 안쪽을 보지 않는다).
- **인덱스 요지(`_gist`) 수정 2건.** 인덱스는 모델이 "어느 파일을 펼칠지" 고르는 라우팅 표면이라
  텍스트 품질이 곧 라우팅 품질이다.
  - 어절/문장 경계에서 절단 + 말줄임(기존: 90자에서 단어 중간 절단).
  - 하이픈을 보존한다 — 마크다운 마커를 문자 단위로 전부 지워 `docs-only`→`docsonly`,
    `do-er`→`doer` 로 용어가 망가지고 있었다. 줄머리 마커만 걷는다.

총 산출 바이트는 260,760 → 275,205(+5.5%, 파일 7 → 55개) — 절차 전문이 references 로 **이동**
했을 뿐 스킬에서 삭제된 내용은 없다. 다이제스트에서 줄어든 분량(학습 제목 약 230행)은 vault 에
그대로 있고 `dw_search`/`dw_read` 로 도달한다.

검증: `make dry-run`(strict) 에러 0·경고 0(embed 평탄화 경고 2건은 변경 전후 동일) · `make seed-check` 통과.

⚠️ 기존 설치본은 `plugin-update` + 프로젝트별 재설치(`make install-project`)로 반영된다.

## 2.8.2 — 2026-07-15

### 수정 — 자동 비준(dw-ratify) 컴파일 검증 경로버그 (모든 버전 영향)
- `dw-ratify.py` 가 승격분 검증 시 존재하지 않는 `{vault}/_build/dw-compile.py` 를 실행 →
  항상 `Errno 2`/returncode≠0 → **모든 승격이 무조건 롤백**. 컴파일러는 플러그인 디렉터리에만
  있고 vault(지식 폴더)엔 없으므로, 2.0.0 이래 자동 비준이 실질적으로 한 번도 성공한 적이 없었고
  OBEY draft 가 "컴파일 strict 실패"로 거짓 hold 되어 누적돼 왔음.
- 검증기를 스크립트 자신과 같은 디렉터리의 `dw-compile.py` 로 지정(`Path(__file__)`).
- 부수: 승격 시 이전 run 의 stale `<!-- ratify-hold -->` 주석 제거(promotion path).
- ⚠️ 기존 설치본은 `plugin-update` 로 이 버전을 받아야 수정 반영됨.

## 2.8.1 — 2026-07-11

### 제거 — bkit 의존 폐기 (팀 결정: bkit 미사용)
- `/denver-workflow` 외부 플러그인 의존에서 bkit 설치 블록 제거 — ⑥ PR 리뷰는 dw 자체 검증자
  (`code-review`·`security-qa`) + `/dw-ci-review`(GH Actions Claude PR 리뷰어)가 담당.
- vault `senior-backend-engineer` 의 bkit 병행 옵션 문구, `backend-reply-via-real-channel` guidance 의
  bkit 각주, worktree TDD procedure 의 bkit 가드 유래 표기 정리. BOOTSTRAP 의 bkit 인용 제거.
- `project/specs/archive/` 의 과거 기록은 보존(역사 문서). 4개 추적 프로젝트 재설치 완료.

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
