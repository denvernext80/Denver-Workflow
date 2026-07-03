---
description: vault 최신 상태(규칙·검사·에이전트·세션 다이제스트)를 프로젝트에 설치/갱신
---
denver-workflow 를 대상 프로젝트에 설치·갱신한다. vault(팀 지식 폴더)의 최신 상태를 컴파일해
프로젝트의 `.claude/`(skills·dw-checks.json·agents·dw-session-digest.md)로 반영한다 —
다음 세션부터 규칙·학습이 자동 주입된다.

## 대상 결정

1. **단일 프로젝트**(기본): 현재 디렉토리.
   ```bash
   make -C "${CLAUDE_PLUGIN_ROOT}" install-project P="$(pwd)"
   ```
2. **멀티레포**: 세션 digest 의 "## 레포 맵" (없으면 vault `project/repo-map.md` 를 읽음)에
   등록된 각 저장소 절대경로에 대해 순회:
   ```bash
   make -C "${CLAUDE_PLUGIN_ROOT}" install-project P=<저장소 절대경로>
   ```
   repo-map 에 scope 열이 있으면 `SCOPES=<값>` 을 함께 넘긴다(생략 = 전체 union).

## 사전 점검

- vault 가 없으면 중단하고 `/dw-setup` 안내 (설정 도우미가 vault 를 만들어 준다).
- 대상 `.claude/` 에 구버전(1.x, `ssot-` 접두) 산출물이 보이면 `/dw-setup` 의
  "레거시 정리" 절차를 먼저 수행한 뒤 설치한다.

## 보고

설치된 산출물 목록(스킬 수·검사 수·에이전트 수)과 "새 세션부터 반영됩니다"를 사용자에게
보고하라. 컴파일 에러가 나면 설치하지 말고 원인을 짚어라.
