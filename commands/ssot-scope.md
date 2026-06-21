---
description: Denver 플러그인 활성 범위 선택 — 사용자 전역 vs 이 프로젝트만 (확인 후 설정)
argument-hint: "[user | project | off]"
---
Denver 플러그인의 활성 범위를 설정한다. CC 는 플러그인을 계정 전역에 설치하므로, 활성 범위는
`enabledPlugins`(settings.json) 위치로 정한다.

인자($ARGUMENTS)가 없으면 **사용자에게 확인**하라: "Denver 를 (1) 사용자 전역 — 모든 프로젝트,
(2) 이 프로젝트만, (3) 끄기 중 어디에 적용할까요?" 그 답에 따라 실행:

- **user(전역)**:    `make -C "${CLAUDE_PLUGIN_ROOT}" plugin-scope-user`
- **project(여기만)**: `make -C "${CLAUDE_PLUGIN_ROOT}" plugin-scope-project P="$(pwd)"`
- **off**:           `make -C "${CLAUDE_PLUGIN_ROOT}" plugin-scope-off P="$(pwd)"`

실행 후: 어디(계정/프로젝트 settings.json)에 무엇이 바뀌었는지 보고하고, **새 세션부터 반영**됨을
알려라. project 범위가 실제로 존중되는지는 새 세션에서 🔒 노출 여부로 확인하라(안 되면 user 로 폴백).
