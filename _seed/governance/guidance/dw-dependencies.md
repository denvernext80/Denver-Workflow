---
type: guidance
scope: engineering
status: stable
title: 외부 의존 자가치유 — 미설치 발견 시 그 자리에서 설치
---

워크플로우 단계 진입 시 필요한 외부 스킬·플러그인(superpowers·impeccable·gstack·Obsidian)이
미설치로 확인되면, **작업을 중단하지 말고 그 자리에서 설치를 대행**한다:

- 감지: `python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw-doctor.py" --json`
- 설치 명령은 `/dw-setup` 의 1·3단계와 동일 (superpowers/impeccable = `claude plugin install`,
  gstack = git clone + setup, Obsidian = brew/winget).
- 사용자 PC 를 바꾸는 설치는 실행 전에 무엇을 왜 설치하는지 한 줄로 알린 뒤 진행한다.
- 설치 실패 시: 수동 설치 방법을 안내하고, 해당 단계가 필수 의존이면 진행을 멈춘다
  (권장 의존이면 그 단계만 건너뛰고 계속).
