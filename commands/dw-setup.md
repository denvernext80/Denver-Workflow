---
description: 초기 설정 도우미 — 필요한 프로그램 설치, vault(팀 지식 폴더) 준비, 이 프로젝트에 워크플로우 설치까지 한 번에
---
denver-workflow 초기 설정 위저드다. 아래 단계를 **순서대로** 진행하라. 각 단계에서 사용자에게
무엇을 왜 하는지 **한 줄씩 쉬운 말로 설명**하고(전문용어에는 짧은 풀이를 붙인다), 설치처럼
사용자 PC 를 바꾸는 행동은 실행 전에 알려라.

## 0단계 — 상태 진단

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw-doctor.py" --json
```
결과의 `missing` 항목만 아래에서 설치한다. 전부 설치돼 있으면 4단계(프로젝트 설치)로 건너뛴다.
OS 는 `uname -s`(Darwin=macOS) 로 판별한다. Linux 면: "Linux 는 지원 예정입니다 — Obsidian 만
수동 설치(https://obsidian.md/download) 후 다시 실행해 주세요" 안내.

## 1단계 — Obsidian 설치 (필수 — 가장 먼저)

Obsidian(팀 지식 vault 를 여는 노트 앱)이 없으면 vault 를 만들어도 사람이 볼 수 없다.
**설치 확인 전에는 2단계로 넘어가지 않는다.**

- macOS: `brew install --cask obsidian` — brew(맥용 프로그램 설치 도구)가 없으면
  https://obsidian.md/download 를 안내하고 사용자가 설치를 마칠 때까지 대기 후 doctor 재실행.
- Windows: `winget install --id Obsidian.Obsidian -e --accept-source-agreements --accept-package-agreements`
- 설치 후 재확인: `python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw-doctor.py" --json` 에서 Obsidian 이 ok 로.

## 2단계 — vault(팀 지식 폴더) 준비 + seed(기본 구조) 주입

vault 는 규칙·계약·스펙·학습이 쌓이는 **단일 진실 원천(SSOT — 한 곳만 믿는 원본)** 폴더다.

1. 경로 결정: 기본은 `~/denver-workflow-vault`. 사용자가 다른 위치를 원하면 그 절대경로 사용.
2. scaffold(기본 폴더 구조 자동 생성):
   ```bash
   make -C "${CLAUDE_PLUGIN_ROOT}" scaffold-vault
   ```
   (커스텀 경로면 `DW_VAULT_DIR=<경로> make -C "${CLAUDE_PLUGIN_ROOT}" scaffold-vault`.
   make 가 없는 환경이면 동일 동작을 직접: `mkdir -p "$VAULT" && cp -Rn "${CLAUDE_PLUGIN_ROOT}/_seed/." "$VAULT/"`)
3. 경로를 환경설정에 기록 — `~/.claude/settings.json` 의 `env.DW_VAULT_DIR` 에 저장한다
   (사용자 홈 기준 값, 예: `"$HOME/denver-workflow-vault"`. 이미 같은 값이면 건너뜀):
   ```bash
   python3 - <<'EOF'
   import json, os
   from pathlib import Path
   p = Path.home() / ".claude" / "settings.json"
   s = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
   s.setdefault("env", {})["DW_VAULT_DIR"] = os.environ.get("DW_VAULT_DIR", "$HOME/denver-workflow-vault")
   p.parent.mkdir(parents=True, exist_ok=True)
   p.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
   print("recorded:", s["env"]["DW_VAULT_DIR"])
   EOF
   ```
4. Obsidian 으로 열기 안내: "Obsidian 을 열고 **Open folder as vault** 로 방금 만든 폴더를
   여세요" — macOS 는 `open "obsidian://open?path=$VAULT"` 로 자동 열기를 시도한다.

## 3단계 — 동료 플러그인·스킬 설치

각각 설치 전에 용도를 한 줄로 설명하고 진행한다:

```bash
# superpowers — 기획·구현 순서를 잡아 주는 플러그인 (요구사항 분석·계획·TDD 단계에 사용)
claude plugin marketplace add anthropics/claude-plugins-official
claude plugin install superpowers@claude-plugins-official

# impeccable — 화면(UI) 디자인 검수 플러그인 (UI 작업 시 필수)
claude plugin marketplace add pbakaus/impeccable
claude plugin install impeccable@impeccable

# gstack — 디자인·QA 스킬 모음 (플러그인이 아니라 git 으로 받는 스킬)
git clone --single-branch --depth 1 https://github.com/garrytan/gstack.git ~/.claude/skills/gstack \
  && cd ~/.claude/skills/gstack && ./setup
```
Windows 에서 gstack `./setup` 실패 시: "gstack 은 수동 설치가 필요합니다" + 저장소 README 안내
(차단 아님 — 권장 의존).

## 4단계 — 이 프로젝트에 워크플로우 설치 (케이스 자동 판별)

먼저 케이스를 판별해 사용자에게 확인받는다:

- **멀티레포**(여러 코드 저장소를 한 세션에서 오가며 작업): 사용자에게 "여러 저장소를 함께
  쓰시나요?" 확인. 그렇다면 → `/denver-workflow` 의 0단계 repo-map(저장소 지도) 부트스트랩으로
  저장소들을 등록한 뒤, repo-map 의 각 저장소 경로에 대해
  `make -C "${CLAUDE_PLUGIN_ROOT}" install-project P=<저장소 절대경로>` 를 순회 실행.
- **신규 프로젝트**(빈 폴더/커밋이 거의 없는 저장소): 바로
  `make -C "${CLAUDE_PLUGIN_ROOT}" install-project P="$(pwd)"`.
- **기존 프로젝트**(코드·CLAUDE.md 가 이미 있음): 동일 설치 — 단 **additive**(기존 파일을
  덮어쓰지 않는다). 기존 CLAUDE.md·settings 는 건드리지 않고 `.claude/` 산출물만 추가한다.
  설치 전 아래 "레거시 정리"를 먼저 수행.

## 레거시 정리 (구버전 산출물 마이그레이션)

<!-- 주의: 아래 구(舊) 이름 리터럴은 감지 대상 표기다 — 이 파일에만 허용. -->
대상 프로젝트 `.claude/` 에 구버전(1.x) 산출물이 있으면 삭제 후 재설치한다:
`ssot-checks.json`, `ssot-session-digest.md`, `ssot-config.json`, `agents/ssot-governed.md`,
`agents/ssot-orchestrator.md`, `agents/ssot-ratifier.md`, `skills/*/.ssot-manifest.json`,
`agents/.ssot-agents.json`. `settings.local.json` 에 `"agent": "ssot-governed"` 또는
`"agent": "ssot-orchestrator"` 가 있으면 `dw-governed`/`dw-orchestrator` 로 치환한다.
구 vault 폴더 `~/denver-agent-vault` 가 있으면 사용자에게 두 가지를 제안:
(1) `mv ~/denver-agent-vault ~/denver-workflow-vault` (권장) (2) `env.DW_VAULT_DIR` 로 기존 경로 유지.

## 마무리 보고

설치·설정된 항목을 표로 요약하고, 다음 행동을 안내한다:
"이제 `/denver-workflow` 를 실행하면 기능 개발 전체 과정(요구사항 → 배포)을 안내해 드립니다."
