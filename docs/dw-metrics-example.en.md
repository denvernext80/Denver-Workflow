> 🌐 English translation of [dw-metrics-example.md](dw-metrics-example.md). The Korean version is authoritative.

# `/dw-metrics` example output (sanitized)

Below is an **example** of what `/dw-metrics` produces. It is not real project data; it was generated against a **synthetic repository** (`demo-service`, 6 commits, no remote → Git-only mode) to demonstrate the deterministic behavior. The Denver-Workflow repository contains only this document (the example) and no per-project raw dumps (the generated output stays under the target repository's `.claude/dw-metrics/`, which is gitignored).

## Running it

```bash
# 현재 저장소를 자동 감지해 측정 (gh 있으면 GitHub-enhanced, 없으면 Git-only)
/dw-metrics

# 페이즈 비교 경계와 함께, gh 무시(Git-only) 예시
/dw-metrics --phases 2026-02-01,2026-03-01 --no-github
```

Internally this delegates to `python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw.py" metrics …`, and **after** the deterministic computation finishes, the command layer reads the output and interprets it as FACT / INFERENCE / UNKNOWN.

## Output layout (`<repo>/.claude/dw-metrics/`)

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

Every number can be independently recomputed straight from `raw/` (reproducibility is the whole point of this tool).

## Example `REPORT.md`

(the tool currently emits its `REPORT.md` in Korean, so the sample below is shown verbatim)

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

## Example `metrics.json` (excerpt)

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

In GitHub-enhanced mode (i.e. `gh` is authenticated), this is augmented with `prs` (opened/merged/closed), `velocity` (throughput), and `runs` (deploy/ci runs and failure rate).

## Evidence levels (FACT / INFERENCE / UNKNOWN)

- **FACT** — values that can be recomputed from `metrics.json` / `raw/`.
- **INFERENCE** — rule-based estimates such as classification and phases (not causation).
- **UNKNOWN** — production incidents, user impact, and whether an actual outage occurred cannot be determined from git/GitHub history alone.

CI/deploy failures are **not** asserted to be production defects or incidents, and reverts are **not** asserted to be outages. Run counts are live values that grow depending on when they are measured.
