---
description: SSOT draft OBEY(rule/guidance/procedure) 자동 비준 → 검증 통과분 stable·compile·install (사람 불요)
---
Denver SSOT 자동 비준을 실행한다.

```bash
make -C "${CLAUDE_PLUGIN_ROOT}" ratify
```

실행 후: 승격된 항목, hold(판단 필요)된 항목, 컴파일·설치 결과를 사용자에게 간결히 보고하라.
hold 가 있으면 그 사유(본문 `<!-- ratify-hold: ... -->`)를 요약하라.
