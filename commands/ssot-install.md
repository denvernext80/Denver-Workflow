---
description: 현재 vault 상태(스킬·결정론 검사·훅·서브에이전트·SessionStart 다이제스트)를 대상 프로젝트에 설치/갱신
---
Denver SSOT 를 대상 프로젝트에 설치·갱신한다. vault 의 최신 상태(규칙·가이던스·학습 인덱스 등)를
컴파일해 각 프로젝트의 `.claude/`(skills·ssot-checks.json·hooks·agents·**ssot-session-digest.md**)로
반영한다 — 이것이 디제스트(학습 항상 노출 포함)를 프로젝트 세션에 닿게 하는 경로다.

```bash
make -C "${CLAUDE_PLUGIN_ROOT}" install
```

(특정 프로젝트만: `make -C "${CLAUDE_PLUGIN_ROOT}" install-travel-one` 또는 `install-balipick`.
대상 경로·scope 는 `${CLAUDE_PLUGIN_ROOT}/Makefile` 상단 `TRAVEL_ONE`/`BALIPICK`·`*_SCOPES` 에서 정의.)

실행 후: 각 프로젝트에 생성된 스킬 수·검사 수·서브에이전트·다이제스트 크기(학습 N건)를 보고하라.
설치된 산출물은 직접 편집 금지 — vault 를 고친 뒤 이 커맨드를 재실행한다.
