# Windows 스모크 체크리스트 (5 분 판정)

**목적**: Windows 실기가 확보됐을 때, denver-workflow 플러그인이 실제로 사는지 **5 분 안에**
판정한다. 2.14.0 은 MCP 런처의 POSIX 셸 의존을 구조적으로 제거했을 뿐, **실기 검증은 없다**
(작성 시점 2026-08-08). 이 문서가 그 공백을 메우는 절차다.

판정 원칙: **"아마 됐을 것" 은 근거가 아니다.** 각 단계는 눈으로 확인할 산출물이 있다.

---

## 0. 사전 전제 확인 (30 초)

```powershell
python3 --version      # ← 이게 실패하면 1~4 단계는 전부 실패한다. 아래 「전제 A」로.
git --version
make --version         # 없어도 MCP·훅은 산다. 커맨드 7 개만 죽는다(「전제 B」).
claude --version
```

* `python3` 이 해석되지 않으면 **여기서 멈추고** 「전제 A」를 먼저 해결한다. `plugin.json` 의
  `mcpServers.command` 가 `"python3"` 이라, 이름이 안 잡히면 MCP 는 절대 뜨지 않는다.

## 1. 플러그인 설치 (1 분)

```powershell
claude plugin marketplace add denvernext80/Denver-Workflow
claude plugin install denver-workflow@denver-workflow
```

**확인**: 설치 경로에 `_build\dw-mcp-launch.py` 가 있고 `_build\dw-mcp-launch.sh` 는 **없다**
(있으면 2.14.0 이전 버전을 받은 것 — `claude plugin update denver-workflow@denver-workflow`).

## 2. 새 세션 시작 (1 분)

새 터미널에서 `claude` 를 띄운다. 첫 실행은 venv 부트스트랩(`.venv` 생성 + `pyyaml`·`mcp<2`
설치)이 돌아 **10~60 초 걸릴 수 있다** — MCP 기동이 느려도 즉시 실패로 판단하지 않는다.

**확인**: 플러그인 루트에 `.venv\Scripts\python.exe` 가 생겼다.

## 3. dw-vault 도구 노출 확인 (1 분) — **핵심 게이트**

세션에서 `/mcp` 를 실행한다.

**확인**: `dw-vault` 가 **connected** 이고 도구가 **11 개** 노출된다.

```
dw_search  dw_read  dw_list  dw_resolve  dw_propose_rule
dw_write_memory  dw_write_backlog  dw_write_reference
dw_write_contract  dw_write_spec  dw_write_procedure
```

> 도구 수는 `_build/dw-mcp-server.py` 의 `@mcp.tool()` 개수와 같아야 한다(`make test` 의
> `test_launcher_serves_all_tools_over_stdio` 가 macOS 에서 같은 것을 검사한다).
> 이 단계가 실패하면 **다른 무엇이 되든 플러그인은 죽은 것**이다.

## 4. 실제 호출 1 회 (30 초)

세션에서 vault 를 읽는 질문을 던져 `dw_search` 가 실제로 돌게 한다. 예:

> vault 에서 tdd-iron-law 를 찾아 요약해줘

**확인**: 결과에 노트 경로가 실제로 나온다(빈 결과 = vault 해석 실패 의심 → 「전제 C」).

## 5. 훅 동작 확인 (1 분)

훅은 문자열 형태라 **셸을 경유한다** — Windows 는 Git Bash, 미설치 시 PowerShell.
두 경로 모두 확인 대상이다.

1. **SessionStart**: 2 단계에서 세션 시작 시 vault 다이제스트 문맥이 주입됐는지(세션 초반에
   프로젝트 규칙이 언급되는지). 조용하면 정상일 수도 있다(비준 대상 0 이면 무작업 설계).
2. **PostToolUse**: 아무 프로젝트 파일을 한 줄 편집한다 → 린터 훅이 돌아야 한다.
3. **PreToolUse**: 서브에이전트를 하나 띄운다 → worktree 가드가 개입하는지.

**확인**: 훅 실행 로그는 세션에서 `/hooks`, 상세 진단은 `claude --debug` 로 본다.

## 6. (선택) make 경유 커맨드 (30 초)

`make` 를 설치했다면 `/dw-install` 을 실행한다. `make` 가 없으면 이 단계는 **실패가 정상**이며,
그 사실 자체가 2.14.0 의 알려진 잔여 범위다(「전제 B」).

---

## 실패 시 어디를 보는가

| 증상 | 1 순위 원인 | 확인 지점 |
| --- | --- | --- |
| `/mcp` 에 `dw-vault` 가 아예 없다 | 플러그인 미활성 / 설치 실패 | `claude plugin list`, `/dw-scope` |
| `dw-vault` 가 **failed** | `python3` 이름 미해석(**가장 흔함**) | `claude --debug` 의 MCP stderr — spawn 자체가 실패하면 파일 없음/ENOENT 계열 |
| `dw-vault` failed + stderr 에 `vault 없음` | vault 폴더 미존재 | 「전제 C」 |
| `dw-vault` failed + stderr 에 `venv 생성 실패` | 파이썬 `venv` 모듈 문제 | 런처가 명령·종료코드·자식 출력을 전부 찍는다 — 그 전문을 본다 |
| 도구가 11 개보다 적다 | 낡은 플러그인 버전 | `plugin.json` 의 `version` 이 2.14.0 이상인지 |
| 도구는 뜨는데 검색이 항상 빈 결과 | vault 경로가 딴 곳 | 「전제 C」 |
| 훅이 전혀 안 돈다 | 셸 부재/`python3` 미해석 | `claude --debug`, Git Bash 설치 여부 |

### 전제 A — `python3` 이름 해석

`plugin.json` 은 `"command": "python3"` 이다. 플랫폼별 분기 키가 없어 **macOS/Linux 와 Windows
양쪽에서 동시에 안전한 인터프리터 이름은 존재하지 않는다** — 이 플러그인의 훅 10 건이 이미 전부
`python3` 을 쓰고 있어 거기에 맞췄다.

* Microsoft Store 판 Python: `python3.exe` 를 제공한다 → 그대로 동작할 가능성이 높다.
* python.org 판 Python: `python.exe`·`py.exe` 만 제공한다 → **`python3` 이 해석되지 않는다.**
  Store 판으로 바꾸거나, PATH 상의 디렉터리에 `python3` 이름을 만들어 준다.

확인: `where python3` 이 실제 실행 파일을 가리키는지(Store 앱 별칭 스텁만 잡히면 실행이 실패할 수 있다).

### 전제 B — `make`

슬래시 커맨드 10 개 중 **7 개**(`/denver-workflow`, `/dw-build`, `/dw-install`, `/dw-ratify`,
`/dw-review`, `/dw-scope`, `/dw-setup`)가 `make` 타깃을 호출한다. 2.14.0 은 이 범위를 **손대지
않았다** — Windows 에서 그 커맨드들엔 여전히 `make` 가 필요하다. MCP·훅은 `make` 없이 동작한다.

### 전제 C — vault 위치

해석 순서는 `DW_VAULT_DIR`(env) → `%USERPROFILE%\denver-workflow-vault`(규약) → **에러**.
폴백은 없다(vault 없이 뜬 서버는 조용히 빈 지식으로 답하므로 기동을 거부한다).
`DW_VAULT_DIR` 값에는 리터럴 `~/`·`$HOME/` 접두를 쓸 수 있다(그 접두만 확장된다).

---

## 이 체크리스트로 판정할 수 없는 것

* **성능·장기 안정성** — 5 분 스모크의 범위가 아니다.
* **Git Bash 경로와 PowerShell 경로의 차이** — 5 단계가 둘 중 실제로 쓰인 쪽만 검증한다.
  둘 다 보려면 Git Bash 를 지운 환경에서 5 단계를 한 번 더 돌린다.
* **`os.execv` 관련 회귀** — Windows 분기는 `subprocess` 로 자식을 띄우므로 애초에 `execv` 를
  타지 않는다(근거는 `_build/dw-mcp-launch.py` 의 `launch()` 주석).

판정 결과는 CHANGELOG 의 2.14.0 「미검증」 목록을 갱신하는 근거로 쓴다 — **실기로 확인한 뒤에만**
그 항목을 「검증됨」 으로 옮긴다.
