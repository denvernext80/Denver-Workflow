---
description: vault 를 컴파일(.claude/skills) — dry-run strict 검증 후 빌드
---
Denver SSOT vault 를 컴파일한다.

```bash
make -C "${CLAUDE_PLUGIN_ROOT}" dry-run && make -C "${CLAUDE_PLUGIN_ROOT}" build
```

검증(에러·경고)과 생성된 skill 목록을 사용자에게 보고하라. 에러가 있으면 빌드하지 말고 원인을 짚어라.
