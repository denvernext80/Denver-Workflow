# `/dw-metrics` 예시 출력 (sanitized)

아래는 `/dw-metrics` 가 만드는 산출물의 **예시**다. 실제 프로젝트 데이터가 아니라, 결정론 동작을
보여주기 위한 **합성(synthetic) 저장소**(`demo-service`, 커밋 6개, remote 없음 → Git-only mode)로
생성했다. Denver-Workflow 저장소에는 이 문서(예시)만 포함하고, 프로젝트별 raw dump 는 포함하지 않는다
(생성물은 대상 저장소의 `.claude/dw-metrics/` 아래 gitignore 대상으로 남는다).

## 실행

```bash
# 현재 저장소를 자동 감지해 측정 (gh 있으면 GitHub-enhanced, 없으면 Git-only)
/dw-metrics

# 페이즈 비교 경계와 함께, gh 무시(Git-only) 예시
/dw-metrics --phases 2026-02-01,2026-03-01 --no-github
```

내부적으로는 `python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw.py" metrics …` 로 위임되고, 결정론 계산이
끝난 **뒤에** 커맨드 층이 산출물을 읽어 FACT/INFERENCE/UNKNOWN 으로 해석한다.

## 출력 구조 (`<repo>/.claude/dw-metrics/`)

```
metrics.json          결정론 집계(머신 판독)
REPORT.md             사람 판독 요약(관찰만 — 인과 표현 없음)
raw/
├── _meta.txt                 분석 ref(SHA)·시각·커밋 카운트
├── firstparent_numstat.txt   PR 단위(스쿼시=1) 제목 + numstat  ← 크기/분류/속도의 정본
├── allcommits.txt            전체 커밋 sha|date
├── trailers.txt              Claude 공동저작/세션 트레일러 카운트
├── governance-adds.txt       거버넌스/워크플로 파일 최초 추가일
├── reverts.txt               revert/reapply/hotfix 목록
├── evolution.txt             개념 발생 키워드 검색
├── codebase-growth.tsv       월별 스냅샷 추적파일·라인
├── prs.json                  gh pr list 전량(GitHub-enhanced 일 때만 내용)
├── deploy_runs.tsv           deploy.yml run(GitHub-enhanced 일 때만)
└── run-counts.json           워크플로별 total/success/failure(GitHub-enhanced 일 때만)
```

모든 숫자는 `raw/` 로 직접 재검산할 수 있다(재현 가능성이 이 도구의 핵심).

## 예시 `REPORT.md`

```markdown
# Engineering Evidence — (no remote)

> 분석 ref `0cbc56cd549c` (HEAD) · 생성 2026-… · mode **Git-only**
>
> 관찰(observation) 리포트. 아래는 git/GitHub 이력에서 결정론적으로 계산한 수치다.
> 성과·품질을 단정하지 않으며, 상관을 인과로 표현하지 않는다.

## 기간·규모 (period & scale)
- 기간: **2026-01-05 → 2026-03-09** (64일 ≈ 9.1주)
- 커밋: all **6** · first-parent(머지 단위) **6**

## 변경 성격 (change classification)
| 분류 | 건수 | 비율 |
|---|---:|---:|
| feature | 1 | 16.7% |
| bugfix | 1 | 16.7% |
| docs | 1 | 16.7% |
| refactor | 1 | 16.7% |
| test | 1 | 16.7% |
| 기타(non-conforming) | 1 | 16.7% |

## 변경 크기 (change size)
- 파일/PR: 평균 **1.0** · 중앙값 **1**
- 라인: **+6 / -0** (net +6)
- 분포: 소형(≤5파일) **100%** · 대형(>20파일) **0%**

## 전달·CI 활동
- (Git-only mode — GitHub Actions 지표 없음. `gh` 인증 시 배포·CI 지표가 추가된다.)

## 안정성 신호 (stability signals)
- revert: **1** (16.7% of first-parent)
- hotfix: **0** — 발견된 버그를 해소하는 corrective change 로 분류
> ⚠️ revert·hotfix 를 production outage 로 단정하지 않는다. git 이력만으로는 사용자 영향·실제
> 장애 여부를 확인할 수 없다(UNKNOWN).

## AI-assisted 개발 흔적 (traces)
- Claude 공동저작 트레일러 포함 커밋: **1/6 (17%)**

## 페이즈 비교 (경계 ['2026-02-01', '2026-03-01'])
> 페이즈 차이는 관측된 변화일 뿐 — 교란요인이 있어 특정 규칙 '덕분'이라 단정하지 않는다.

| phase | PR | via(#N) | median files | test% | bugfix% | revert% |
|---|---:|---:|---:|---:|---:|---:|
| P1 (<2026-02-01) | 2 | 100% | 1 | 0% | 50% | 0.0% |
| P2 (<2026-03-01) | 2 | 100% | 1 | 0% | 0% | 0.0% |
| P3 (>=2026-03-01) | 2 | 100% | 1 | 50% | 0% | 50.0% |
```

## 예시 `metrics.json` (발췌)

```json
{
  "period": {"first": "2026-01-05", "last": "2026-03-09", "days": 64,
             "commits_all": "6", "first_parent": 6},
  "classification": {"feature": 1, "bugfix": 1, "docs": 1, "refactor": 1,
                     "test": 1, "기타(non-conforming)": 1},
  "size": {"mean_files": 1.0, "median_files": 1, "add": 6, "del": 0,
           "small_pct": 100, "large_pct": 0},
  "stability": {"reverts": 1, "revert_pct": 16.7, "hotfix": 0,
                "reverts_by_month": {"2026-03": 1}},
  "ai_native": {"commits_all": "6", "commits_with_claude_coauthor": "1",
                "commits_with_claude_session": "0"}
}
```

GitHub-enhanced mode(=`gh` 인증됨)에서는 여기에 `prs`(생성/병합/종료)·`velocity`(처리량)·
`runs`(deploy/ci 실행·실패율) 가 더해진다.

## 근거 수준 (FACT / INFERENCE / UNKNOWN)

- **FACT** — `metrics.json`/`raw/` 에서 재계산 가능한 값.
- **INFERENCE** — 분류·페이즈 등 규칙 기반 추정(인과 아님).
- **UNKNOWN** — production incident·사용자 영향·실제 장애 여부는 git/GitHub 이력만으로 확인 불가.

CI/배포 실패는 production defect·incident 로, revert 는 outage 로 **단정하지 않는다**. run count 는
실행 시점에 따라 증가하는 live 값이다.
