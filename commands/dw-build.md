---
description: vault 를 컴파일(.claude/skills) — dry-run strict 검증 후 빌드
---
Denver SSOT vault 를 컴파일한다. **먼저 검증(dry-run), 에러 0 일 때만 빌드** — 두 단계를
순서대로 실행하라(셸 `&&` 대신 순차 실행: PowerShell 5.1 등에 `&&` 가 없다).

1. 검증(쓰기 없음, 경고도 에러):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw.py" dry-run
   ```
2. **1번이 에러 0 으로 끝났을 때만** 빌드:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw.py" build
   ```

검증(에러·경고)과 생성된 skill 목록을 사용자에게 보고하라. 에러가 있으면 빌드하지 말고 원인을 짚어라.
