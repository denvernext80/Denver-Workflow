---
description: repository 이력(history)을 재현 가능한 Engineering Evidence(엔지니어링 증거 — 숫자로 확인 가능한 근거)로 변환해 관찰한다
argument-hint: "[--phases d1,d2] [--json] [--no-github] [-p 경로]"
---
현재 repository(작업 중인 저장소)가 실제로 어떻게 **만들어지고·검증되고·전달되고** 있는지를
git/GitHub 이력에서 **결정론적(deterministic — 매번 같은 입력이면 같은 결과)**으로 측정한다.

핵심 원칙 — **Evidence first, interpretation second(증거 먼저, 해석은 그 다음).**
숫자는 도구가 만든다. 너는 그 숫자를 **기억이나 추측으로 만들지 말고**, 아래 산출물을 읽은 뒤에만
해석한다.

## 1) 측정 실행 (결정론 — 도구가 raw 증거 + 집계를 만든다)

현재 디렉토리를 대상 repo 로 자동 감지한다(GitHub remote 가 있으면 owner/repo 자동 감지, `gh` 가
없거나 인증 안 됐으면 **Git-only mode** 로 graceful 하게 동작). `$ARGUMENTS` 가 있으면 그대로 이어
붙여 실행하라(예: `--phases 2026-07-05,2026-08-11` · `--no-github` · `-p <다른 repo 경로>`):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw.py" metrics $ARGUMENTS
```

산출물(대상 repo 의 `.claude/dw-metrics/` — gitignore 대상이라 저장소를 오염시키지 않는다):
- `raw/` — 원시 증거(numstat·commits·trailers·reverts·evolution·growth·gh dump). 모든 숫자의 출처.
- `metrics.json` — 결정론 집계(머신 판독).
- `REPORT.md` — 사람 판독 요약(관찰만, 인과 표현 없음).

감지 실패 시(저장소 아님): 사용자에게 `-p <repo 경로>` 를 요청하라.

## 2) 산출물 읽기 (해석의 유일한 근거)

`.claude/dw-metrics/REPORT.md` 와 `.claude/dw-metrics/metrics.json` 을 읽어라. **여기에 있는 숫자만**
쓴다. 없는 값을 만들어내지 말 것.

## 3) 해석 보고 (FACT / INFERENCE / UNKNOWN 을 구분)

읽은 증거를 근거로 다음을 간결히 요약하되, 각 항목에 근거 수준을 태그하라:

- **현재 개발 패턴** (변경 성격·크기·처리량)
- **눈에 띄는 변화** (월별·페이즈 추이 — 경계가 주어진 경우)
- **전달(delivery) 패턴** (배포·CI 활동 — GitHub-enhanced mode 일 때)
- **품질/안전 신호** (revert·hotfix·테스트 활동)
- **비정상 추세**(unusual trend) 또는 **추가 확인이 필요한 부분**

근거 수준 규칙:
- **FACT** — `metrics.json`/`raw/` 에서 재계산 가능한 값만.
- **INFERENCE** — 규칙 기반 추정(분류·페이즈 해석 등). 인과가 아님을 명시.
- **UNKNOWN** — git/GitHub 이력만으로 확인 불가한 것. **추정하지 말고 UNKNOWN 으로 남겨라.**

**금지(반드시 지켜라):**
- 상관(correlation)을 인과(causation)로 표현하지 말 것. "X 덕분에 Y" 금지 — "X 이후 Y 가 관측됨"까지만.
- CI 실패·deploy 워크플로 실패를 **production defect/incident 로 해석하지 말 것**(게이트가 프로덕션
  도달 전에 막은 것일 수 있다).
- revert 를 곧바로 **production outage 로 단정하지 말 것**. hotfix 는 발견된 버그를 해소하는
  corrective change(교정 변경)로만 분류한다.
- production incident·사용자 영향·실제 장애 여부 등 이력이 뒷받침하지 않는 주장을 만들지 말 것.

마지막에 산출물 경로(`.claude/dw-metrics/`)를 알려, 사용자가 raw 증거로 직접 재검산할 수 있게 하라.
