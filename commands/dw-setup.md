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

<!-- 주의: 아래 구(舊) 이름 리터럴은 감지 대상 표기다 — 이 파일(과 dw-migrate-vault.py)에만 허용. -->

**(a) 프로젝트 `.claude/` 산출물** — 있으면 삭제 후 재설치한다:
`ssot-checks.json`, `ssot-session-digest.md`, `ssot-config.json`, `agents/ssot-governed.md`,
`agents/ssot-orchestrator.md`, `agents/ssot-ratifier.md`, `skills/*/.ssot-manifest.json`,
`agents/.ssot-agents.json`, 그리고 1.x 가 프로젝트에 복사해 둔 로컬 훅 4종
`hooks/ssot-lint.py`·`hooks/ssot-session-context.py`·`hooks/ssot-vault-guard.py`·
`hooks/ssot-worktree-guard.py` (지운 뒤 `hooks/` 가 비면 폴더도 제거 — 2.0 은 훅을 플러그인이
전역 제공하므로 프로젝트 사본이 필요 없다). 다른 이름의 훅·에이전트 파일은 사용자 것 — 삭제하지
않는다. **단, 파일명은 멀쩡하나 내용에 구 식별자(`ssot_`·`denver-agent`)를 품은 에이전트(예: 1.x 가
설치한 `senior-backend-engineer.md`)는 삭제 대상이 아니라 (e) 내용 치환 대상**이다 — 지우면 오케스트
레이터가 디스패치할 do-er 가 사라진다(기록 실패가 디스패치 실패로 악화). 아래로 감지한다:
```bash
grep -rlE 'ssot_|denver-agent|mcp__plugin_denver-agent' "<프로젝트>/.claude/agents" 2>/dev/null
```

**(b) settings 배선** — `settings.json`/`settings.local.json` 에서 (다른 설정은 유지):
- `hooks` 항목 중 command 가 `/hooks/ssot-` 를 참조하는 배선만 제거.
- `enabledMcpjsonServers` 배열의 `"ssot-vault"` 항목 제거.
- `env.DENVER_VAULT_DIR` 는 삭제하고 `env.DW_VAULT_DIR` 로 대체(값은 아래 (c)의 경로 결정 결과).
- `"agent": "ssot-governed"` / `"agent": "ssot-orchestrator"` → `dw-governed`/`dw-orchestrator`.

**(c) 구 vault 감지·이전** — 구 vault 는 규약 경로 밖(커스텀 경로)에 있을 수 있다. 다음 순서로 찾는다:
① `~/denver-agent-vault`(구 규약 경로) ② 전역·프로젝트 `settings.json` 의 `env.DENVER_VAULT_DIR`
③ 프로젝트 `.claude/ssot-config.json` 의 `vault_root`. 찾으면 사용자에게 두 가지를 제안:
(1) **새 이름으로 변경(권장)** — 같은 부모 폴더 안에서 `denver-workflow-vault` 로 이름만 바꾸고
`env.DW_VAULT_DIR` 에 기록, Obsidian 재등록(`open "obsidian://open?path=<새 경로>"`).
(2) **경로 그대로 유지** — `env.DW_VAULT_DIR` 에 기존 경로를 기록.

**(d) vault 내용 치환** — 1.x vault 에 콘텐츠가 쌓여 있으면 노트 속 구 식별자(도구·에이전트·산출물
이름)를 이전 스크립트로 새 체계로 바꾼다. 개념어 "SSOT" 와 기록 제목 속 일반 표현은 보존하고,
파일명·위키링크 정합을 함께 유지한다. dry-run(미리보기)으로 변경 대상을 사용자에게 보여준 뒤 적용한다:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw-migrate-vault.py" --vault <vault 경로>          # 미리보기(쓰기 없음)
python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw-migrate-vault.py" --vault <vault 경로> --apply  # 적용(백업 tar.gz 자동)
```
적용 후 검증: `make -C "${CLAUDE_PLUGIN_ROOT}" dry-run` 이 에러 0 으로 통과해야 한다.

**(e) 프로젝트 설치 아티팩트 내용 치환** — (a) 에서 감지한, 파일명은 멀쩡하나 내용이 stale 한
에이전트(`senior-*.md` 등)를 **삭제 대신 제자리 치환**한다. `dw-migrate-vault.py` 는 vault 뿐 아니라
`--project` 로 대상 레포의 `.claude/agents/*.md` 도 같은 규칙으로 치환한다(skills 는 재설치가 재생성,
agent-memory 는 사용자 데이터라 제외) — `ssot_write_memory` 류 죽은 도구 이름이 `dw_write_*` 로
바뀌어 기록 도구가 되살아난다. 여러 레포는 `--project` 를 반복한다:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw-migrate-vault.py" --project <레포1> --project <레포2>          # 미리보기
python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw-migrate-vault.py" --project <레포1> --project <레포2> --apply  # 적용(백업 자동)
```
치환 후 `grep -rlE 'ssot_|denver-agent' <레포>/.claude/agents` 가 **빈 결과**여야 한다.

> **후속(사용자 판단):** 위 do-er(`senior-*.md` 등)가 **현재 vault `governance/agents/` 소스에
> 정의돼 있지 않으면**, 지금 치환으로 되살아나더라도 다음 클린 설치 때 다시 고아가 될 수 있다.
> vault 의 규칙·레포맵이 그 do-er 를 디스패치 대상으로 참조한다면, **정본을 vault 소스로 추가**해
> 컴파일·재설치 흐름에 편입시켜야 근본 해소된다.

## (선택) graphify 시멘틱 그래프 MCP 등록

`graphify`(코드/지식을 그래프로 인덱싱하는 외부 도구)가 설치돼 있고 대상 프로젝트에 그래프가
빌드돼 있으면(`graphify-out/graph.json`), 프로젝트 `.mcp.json` 에 graphify MCP 서버를 등록해
`query_graph`·`shortest_path`·`get_neighbors` 등 **네이티브 그래프 도구**를 세션에 노출할 수 있다.
graphify 는 optional — 감지될 때만 사용자에게 등록을 제안한다(전역 plugin.json 미포함).

1. 감지·미리보기(쓰기 없음):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw-graphify-register.py" --project "$(pwd)"
   ```
   "등록 스킵"이면 graphify/graph.json 이 없는 것 — 이 단계 건너뛴다.
2. 경로가 출력되면 사용자에게 **등록할지 확인**한 뒤 적용(mcp SDK 없으면 `pipx inject` 자동):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw-graphify-register.py" --project "$(pwd)" --apply
   ```
   (그래프가 vault 등 다른 위치면 `--graph <graph.json 절대경로>` 를 붙인다.)
3. 새 세션에서 확인: `claude mcp list | grep graphify` (→ graphify … Connected).

- 등록(`--apply`)은 대상 레포 `.gitignore` 에 `graphify-out/`(그래프 산출물, 수십 MB)를 자동 추가한다.
  Flutter/node 등 네이티브 혼재 레포면 god-node 오염 방지용 `.graphifyignore` 스캐폴드를 제안하며,
  기록하려면 `--graphifyignore` 로 재실행한다(자동 기록 안 함 — 제외 경로는 레포마다 다름).
- 조회 라우팅: **지식**은 기본 그래프(vault ingest), **특정 레포 코드**는 `project_path=<repo 절대경로>` 인자.
- 참고: `graphify install --platform claude` 가 `.claude/CLAUDE.md` 에 넣는 graphify 블록은 graphify
  자체 산출물이다 — 워크스페이스 루트엔 그래프가 없어 문구가 거짓일 수 있다. 그래프 라우팅 정본은
  digest guidance(지식=기본 그래프 / 코드=`project_path`)이며 CLAUDE.md 블록에 의존하지 않는다.

## (선택) GitHub Actions Claude PR 리뷰어 설치

11단계 ⑥(PR + 리뷰 + CI)를 GitHub 에서 자동화하는 **Claude 기반 PR 리뷰어**를 설치할 수 있다.
PR 이 열리면 Claude 가 코드를 읽어 리뷰하고 합격/불합격을 판정한다. **선택 기능** — 대상 저장소가
GitHub 저장소이고 사용자가 원할 때만 제안한다(비용·시크릿이 걸린 바깥 설정이라 강제하지 않는다).

1. 대상이 GitHub 저장소인지 확인(`.git` 존재 + GitHub 리모트). 아니면 이 단계 건너뛴다.
2. 사용자에게 "PR 이 열리면 Claude 가 자동으로 코드 리뷰하고 합격/불합격을 매기는 기능을 켤까요?
   (Claude Pro/Max 구독 토큰이 필요합니다)" 확인. 원하면:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw-ci-review.py" --project "$(pwd)"          # 미리보기
   python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw-ci-review.py" --project "$(pwd)" --apply  # 설치(no-clobber)
   ```
3. 설치 후 사람 작업(토큰 등록·커밋·머지 게이트)은 **`/dw-ci-review` 커맨드가 안내하는 절차**와 동일
   하다 — 그 안내(① `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN` 시크릿, ② 커밋·푸시, ③ 선택:
   브랜치 보호 required check 에 `review` 추가)를 따르게 한다.

나중에 다른 저장소에 켜거나 다시 설정하려면 **`/dw-ci-review`** 를 쓰면 된다.

## 마무리 보고

설치·설정된 항목을 표로 요약하고, 다음 행동을 안내한다:
"이제 `/denver-workflow` 를 실행하면 기능 개발 전체 과정(요구사항 → 배포)을 안내해 드립니다."
필요하면 `/dw-ci-review` 로 GitHub PR 자동 리뷰어를 저장소별로 켤 수 있음을 함께 알린다.
