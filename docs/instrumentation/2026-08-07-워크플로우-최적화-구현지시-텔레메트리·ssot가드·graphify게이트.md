# 구현 지시: denver-workflow 워크플로우 최적화 (텔레메트리 + SSOT 가드 + graphify 게이트)

> 이 문서를 로컬 Claude Code(denver-workflow 플러그인 레포)에서 실행하라. 클라우드 세션은 git
> lock 파일 unlink 권한이 없어 커밋이 불가해, 배선·검증·커밋을 로컬로 넘긴다.

## 배경 (왜)
워크플로우 진단에서 세 병목이 실측·관찰됐다: (1) 절차·memory 가 완료 수명주기 없이 축적되고
재사용이 미검증(절차 95%·규칙 89% orphan), (2) 에이전트가 dw_write 실패 시 **파일을 직접 편집해
SSOT 를 우회**함, (3) graphify 가 설치·발화되는데도 무시되고 vault(dw_search)만 자주 쓰임.
근본 공통점: **조언(additionalContext)형 훅은 라우팅당한다 — 강제하려면 PreToolUse 게이트가 필요.**

이 작업은 3가지를 구현한다:
- ① **워크플로우 텔레메트리**(비파괴 PostToolUse): 3대 규율 준수율 + 절차/memory 재사용 실측.
- ② **SSOT 쓰기 가드**(PreToolUse): OBEY(rule/guidance/procedure) 직접편집 차단, LIVE 통과.
- ③ **graphify 하드 게이트**(PreToolUse): 세션에 graphify 미사용 시 dw_search/심볼-grep 차단,
  한 번 쓰면 조언 모드로 self-release(텔레메트리 세션로그 연동 → ③은 ①에 의존).

### automode 인지 (중요)
②③ 게이트는 payload 의 `permission_mode` 를 읽어 결정을 **자동 상향**한다:
- **사람 있는 모드**(default/plan) → `ask`(사람 override 가능).
- **automode**(auto/dontAsk/bypassPermissions, +쓰기가드는 acceptEdits 도) → `deny`(무조건 차단).
  이유: automode 에선 `ask` 가 auto-approve 로 폴백돼 무력화되지만, **훅의 `deny` 는 bypassPermissions
  에서도 항상 차단**된다(훅이 권한모드보다 상위). 러너/무인 흐름에서도 규율이 안 샌다.
- `DW_GATE_HARD=1|0` env 로 명시 강제(1=deny, 0=ask). 러너 런처에서 `export DW_GATE_HARD=1` 권장.

## 반드시 지킬 규율 (이 레포의 CLAUDE.md·거버넌스)
- **worktree 격리 + 작업 브랜치**에서만 작업. main 직접 커밋 금지.
- 완료 게이트: 아래 "검증" 전부 green 이어야 완료. 증거(스모크 테스트 출력) 제시.
- 마감에 비자명 학습을 `dw_write_memory`, 재사용 절차를 `dw_write_procedure` 로 draft 기록.

## 0단계 — 이전 세션 잔재 정리 + worktree 생성
```bash
cd ~/Repository/denver-workflow
git worktree remove -f -f .wt-dwtel 2>/dev/null; rm -rf .wt-dwtel .git/worktrees/-wt-dwtel
git branch -D dw/telemetry-guard 2>/dev/null; rm -f .git/index.lock
git worktree add -b dw/workflow-opt .worktrees/workflow-opt main
cd .worktrees/workflow-opt
```

## 1단계 — 새 훅 파일 3개 배치 (`_build/`)
아래 소스를 **그대로** 생성한다. (분석기 `dw-workflow-report.py` 와 선택 로거 `dw_access_log.py`
는 이 세션에 이미 전달된 파일을 `_build/` 에 함께 두라 — 소스 동일.)

### `_build/dw-telemetry.py`
```python
#!/usr/bin/env python3
"""dw 워크플로우 텔레메트리 — 비파괴 PostToolUse 훅.

의도한 규율 대비 '실제 도구 사용 분포'를 관측한다. 서버를 건드리지 않고 훅 레이어에서
모든 관련 도구 호출을 <vault>/.dw-state/access.jsonl 에 한 줄(JSON)씩 남긴다.

측정 목표(진단에서 나온 두 가설):
  1) graphify-우선 규율이 실제로 지켜지나 — graphify vs dw_search vs Grep 분포.
  2) 쓰기가 dw_write 로만 되나 — dw_write_* vs vault 파일 직접 Edit/Write(bypass).
  3) 읽기가 dw_read 로 되나 — dw_read vs vault 파일 직접 Read(bypass).
  + 절차·memory 재사용(read 0회 = archive 후보) 실측.

설계 원칙: 계측은 결코 도구 호출을 막지 않는다(항상 exit 0, 모든 예외 삼킴).
vault CONTENT_DIRS 밖(.dw-state/)에만 기록. 표준 라이브러리만.

Claude Code PostToolUse 훅으로 배선(matcher 는 아래 도구들을 포함하도록). stdin=훅 payload JSON.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
from pathlib import Path


def _vault_root(project: Path):
    cfg = project / ".claude" / "dw-config.json"
    if cfg.exists():
        try:
            v = json.loads(cfg.read_text(encoding="utf-8")).get("vault_root")
            if v and Path(v).is_dir():
                return Path(v)
        except Exception:
            pass
    env = os.environ.get("DW_VAULT_DIR")
    if env:
        env = os.path.expandvars(os.path.expanduser(env))
        if Path(env).is_dir():
            return Path(env)
    conv = Path.home() / "denver-workflow-vault"
    if conv.is_dir():
        return conv
    if (project / "_build" / "dw-compile.py").exists():
        return project
    return None


def _classify(tool: str, ti: dict):
    """(kind, sub, target) 반환. kind: vault|graphify|grep|file|other."""
    low = tool.lower()
    if "dw-vault__" in tool or (tool.startswith("dw_")):
        sub = tool.split("dw-vault__")[-1] if "dw-vault__" in tool else tool
        target = ti.get("name") or ti.get("query") or ti.get("title") or ti.get("note_type") or ""
        return "vault", sub, target
    if "graphify" in low:
        sub = tool.split("__")[-1]
        target = ti.get("query") or ti.get("node") or ti.get("symbol") or ti.get("start") or ""
        return "graphify", sub, str(target)[:120]
    if tool == "Grep":
        return "grep", "Grep", ti.get("pattern", "")
    if tool in ("Read", "Edit", "Write", "MultiEdit"):
        return "file", tool, ti.get("file_path", "")
    return "other", tool, ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        tool = payload.get("tool_name") or ""
        ti = payload.get("tool_input") or {}
        kind, sub, target = _classify(tool, ti)
        if kind == "other":
            return 0

        project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())
        vault = _vault_root(project)
        if vault is None:
            return 0
        vroot = vault.resolve()

        inside_vault = None
        resolved = None
        if kind == "file" and target:
            try:
                rel = Path(target).resolve().relative_to(vroot)
                inside_vault = True
                resolved = str(rel)
            except Exception:
                inside_vault = False
            # vault 밖 코드 파일 Read/Edit 는 노이즈 → 기록하지 않는다(Grep 은 코드탐색이라 유지).
            if not inside_vault:
                return 0

        rec = {
            "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "session": payload.get("session_id") or "",
            "kind": kind,
            "tool": sub,
            "target": str(target)[:200],
        }
        if resolved is not None:
            rec["resolved"] = resolved
        d = vroot / ".dw-state"
        d.mkdir(exist_ok=True)
        with open(d / "access.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### `_build/dw-vault-write-guard.py`
```python
#!/usr/bin/env python3
"""dw-vault-write-guard — PreToolUse 훅: OBEY 노트(rule/guidance/procedure) 직접편집 차단(ask).

문제: 에이전트가 dw_write_* 를 잘못 써 실패하면 파일을 직접 열어 Edit/Write 로 고치며 SSOT 를
우회한다. dw-vault-guard(PostToolUse)는 구조적으로 차단 불가(조언만) — 그래서 **PreToolUse** 에서
차단한다(worktree-guard 와 동일 패턴).

정책(사용자 비준 모델과 일치):
  - OBEY = rule/guidance/procedure  → 컴파일/사람비준 대상. 직접편집 **ask 로 차단**,
    올바른 경로(dw_propose_rule / dw_write_procedure / vault 에서 사람 편집)로 유도.
  - LIVE = memory/contract/spec/decision/backlog/reference → 직접 쓰기 허용(통과).
  - vault 밖 코드 파일 → 통과.
OBEY 판정: 파일 존재 시 frontmatter `type`, 없으면(신규) 경로 프리픽스(governance/rules|guidance|procedures).

출력: PreToolUse permissionDecision(ask/allow) JSON. 결코 예외로 터지지 않는다(실패 시 allow).
표준 라이브러리만.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

FM_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
OBEY = {"rule", "guidance", "procedure"}
OBEY_DIRS = ("governance/rules", "governance/guidance", "governance/procedures")
TOOL_HINT = {
    "rule": "dw_propose_rule 로 draft 규칙을 제안하라(stable 승격은 사람).",
    "procedure": "dw_write_procedure 로 draft 절차를 기록하라(비준되면 스킬로 로드).",
    "guidance": "guidance 는 사람이 vault 에서 저작한다 — 에이전트 직접편집 금지.",
}


def _vault_root(project: Path):
    cfg = project / ".claude" / "dw-config.json"
    if cfg.exists():
        try:
            v = json.loads(cfg.read_text(encoding="utf-8")).get("vault_root")
            if v and Path(v).is_dir():
                return Path(v)
        except Exception:
            pass
    env = os.environ.get("DW_VAULT_DIR")
    if env:
        env = os.path.expandvars(os.path.expanduser(env))
        if Path(env).is_dir():
            return Path(env)
    conv = Path.home() / "denver-workflow-vault"
    if conv.is_dir():
        return conv
    if (project / "_build" / "dw-compile.py").exists():
        return project
    return None


def _fm_type(path: Path):
    try:
        m = FM_RE.match(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not m:
        return None
    for line in m.group(1).splitlines():
        if line.startswith("type:"):
            return line.split(":", 1)[1].strip().strip("'\"")
    return None


# automode(무인 실행)에서는 ask 가 auto-approve 로 폴백돼 무력화된다 → deny 로 상향.
# 훅의 deny 는 bypassPermissions 에서도 항상 차단(훅이 권한모드보다 상위). Edit/Write 를 가드하므로
# 그것을 자동승인하는 acceptEdits 도 hard 로 취급. DW_GATE_HARD env 로 명시 오버라이드 가능.
_HARD_MODES = {"auto", "dontAsk", "bypassPermissions", "acceptEdits"}


def _hard(payload) -> bool:
    env = os.environ.get("DW_GATE_HARD", "").lower()
    if env in ("1", "deny", "hard", "true"):
        return True
    if env in ("0", "ask", "soft", "false"):
        return False
    return str(payload.get("permission_mode") or "") in _HARD_MODES


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # 파싱 실패 = 침묵(차단 안 함)
    try:
        if payload.get("hook_event_name") not in (None, "PreToolUse"):
            return 0
        ti = payload.get("tool_input") or {}
        fp = ti.get("file_path")
        if not fp or not str(fp).endswith(".md"):
            return 0
        project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())
        vault = _vault_root(project)
        if vault is None:
            return 0
        try:
            rel = Path(fp).resolve().relative_to(vault.resolve())
        except Exception:
            return 0  # vault 밖 = 통과
        rels = str(rel).replace("\\", "/")

        # OBEY 판정: type(있으면) 우선, 없으면 경로 프리픽스.
        p = Path(fp)
        ty = _fm_type(p) if p.exists() else None
        is_obey = (ty in OBEY) if ty else any(rels.startswith(d + "/") for d in OBEY_DIRS)
        if not is_obey:
            return 0  # LIVE·기타 = 통과(직접 쓰기 허용)

        kind = ty or next((d.split("/")[-1].rstrip("s") for d in OBEY_DIRS if rels.startswith(d + "/")), "rule")
        kind = {"rule": "rule", "guidance": "guidance", "procedure": "procedure",
                "guidanc": "guidance", "procedure ": "procedure"}.get(kind, kind)
        hint = TOOL_HINT.get(kind, "dw 쓰기 도구를 사용하라.")
        hard = _hard(payload)
        tail = "automode → 차단. 올바른 경로로 재시도하라." if hard else "정말 직접 편집이 필요하면 override."
        reason = (f"🔒 SSOT 가드: '{rels}' 는 OBEY 노트({kind})다 — 직접편집은 컴파일·비준을 우회한다. "
                  f"{hint} ({tail})")
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny" if hard else "ask",
            "permissionDecisionReason": reason,
        }}, ensure_ascii=False))
    except Exception:
        return 0  # 어떤 실패도 차단으로 이어지지 않는다
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### `_build/dw-graphify-gate.py`  (기존 v1 을 이 v2 로 교체)
```python
#!/usr/bin/env python3
"""dw-graphify-gate v2 — PreToolUse 훅: graphify 우선을 '조언'에서 '게이트(ask)'로 강화.

배경: v1 은 additionalContext 넛지만 줬고, graphify 가 발화돼도 에이전트가 무시하고 dw_search/
grep 로 직행했다(직접편집 bypass 와 같은 실패 모드 — 조언은 라우팅당한다). v2 는 **이번 세션에
graphify 를 아직 한 번도 안 썼으면 dw_search/심볼-Grep 직전에 ask 로 차단**한다. graphify 를 한 번
쓰면(텔레메트리 로그로 판별) 그 세션에선 다시 조언 모드로 내려간다 — self-releasing.

의존: dw-telemetry.py 가 <vault>/.dw-state/access.jsonl 에 session 별 graphify 이벤트를 남긴다.
로그가 없거나 graphify 미등록이면 v1 과 동일하게 (조언 또는 침묵) 동작 — 안전 폴백.

정책:
  - graphify 미등록(project .mcp.json) → 침묵 통과(옵셔널 불변식).
  - 이번 세션 graphify 사용 기록 있음 → v1 넛지(additionalContext)만.
  - 사용 기록 없음 → permissionDecision "ask" (override 가능). dw_read 는 매처에서 제외.
표준 라이브러리만. 결코 예외로 안 터진다(실패 시 통과).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_SYMBOLISH = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")

_NUDGE = (
    "🕸 graphify 활성 — 이 substring `dw_search` 전에 graphify 그래프로 먼저 발견했는가? "
    "지식/문서는 `query_graph`·`get_neighbors`·`shortest_path`(기본 그래프), 특정 레포 코드는 "
    "`project_path=<repo 절대경로>`. (원문 확정·인용은 이후 `dw_read`.)"
)
_GREP_NUDGE = (
    "🕸 graphify 활성 — 코드 **구조**(정의·호출자·의존) grep 으로 보인다. raw grep 대신 "
    "**세션 graphify MCP**: `query_graph`·`get_neighbors`(`project_path=<repo 절대경로>`). "
    "grep 은 리터럴(에러메시지·설정키·주석)에만."
)
_ASK = (
    "🕸 graphify 게이트: 이번 세션에 graphify 그래프를 **아직 한 번도** 쓰지 않았다. 규율은 "
    "graphify 우선(코드·지식 탐색) — `query_graph`/`get_neighbors`/`shortest_path` 로 먼저 발견한 뒤 "
    "`dw_search`/grep 은 폴백으로만 쓴다. graphify 로 먼저 탐색하라."
)


def _vault_root(project: Path):
    cfg = project / ".claude" / "dw-config.json"
    if cfg.exists():
        try:
            v = json.loads(cfg.read_text(encoding="utf-8")).get("vault_root")
            if v and Path(v).is_dir():
                return Path(v)
        except Exception:
            pass
    env = os.environ.get("DW_VAULT_DIR")
    if env:
        env = os.path.expandvars(os.path.expanduser(env))
        if Path(env).is_dir():
            return Path(env)
    conv = Path.home() / "denver-workflow-vault"
    if conv.is_dir():
        return conv
    if (project / "_build" / "dw-compile.py").exists():
        return project
    return None


# automode(auto/dontAsk/bypassPermissions)에선 ask 가 무력화 → deny 로 상향(훅 deny 는 항상 차단).
# dw_search/Grep 은 edit 이 아니므로 acceptEdits 는 hard 에 넣지 않는다. DW_GATE_HARD 로 오버라이드.
def _hard(payload) -> bool:
    env = os.environ.get("DW_GATE_HARD", "").lower()
    if env in ("1", "deny", "hard", "true"):
        return True
    if env in ("0", "ask", "soft", "false"):
        return False
    return str(payload.get("permission_mode") or "") in {"auto", "dontAsk", "bypassPermissions"}


def _graphify_registered(project: Path) -> bool:
    try:
        p = project / ".mcp.json"
        if not p.exists():
            return False
        servers = json.loads(p.read_text(encoding="utf-8")).get("mcpServers", {})
        return isinstance(servers, dict) and "graphify" in servers
    except Exception:
        return False


def _graphify_used_this_session(vault: Path, session: str) -> bool:
    """텔레메트리 로그 tail 에서 이번 세션의 graphify 이벤트 유무. 로그 없으면 False(→ ask)."""
    if not session:
        return False
    log = vault / ".dw-state" / "access.jsonl"
    if not log.is_file():
        return False
    try:
        lines = log.read_text(encoding="utf-8").splitlines()[-4000:]  # tail 만
    except Exception:
        return False
    for line in reversed(lines):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("session") == session and r.get("kind") == "graphify":
            return True
    return False


def _emit_ctx(text: str):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "additionalContext": text}}, ensure_ascii=False))


def _emit_gate(text: str, hard: bool):
    tail = " (automode → 차단.)" if hard else " (그래도 이 검색이 필요하면 override.)"
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny" if hard else "ask",
        "permissionDecisionReason": text + tail}}, ensure_ascii=False))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        if payload.get("hook_event_name") not in (None, "PreToolUse"):
            return 0
        project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())
        if not _graphify_registered(project):
            return 0

        tool = str(payload.get("tool_name") or "")
        ti = payload.get("tool_input") or {}
        is_grep = tool == "Grep"
        if is_grep and not _SYMBOLISH.match(str(ti.get("pattern") or "")):
            return 0  # 리터럴 grep 은 그래프가 답 못 함 → 침묵

        vault = _vault_root(project)
        session = payload.get("session_id") or ""
        used = _graphify_used_this_session(vault, session) if vault else False
        if used:
            _emit_ctx(_GREP_NUDGE if is_grep else _NUDGE)  # 이미 썼으면 부드럽게
        else:
            _emit_gate(_ASK, _hard(payload))  # 아직 안 썼으면 게이트(automode=deny, else ask)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## 2단계 — `hooks/hooks.json` 배선 (기존 항목 유지, 아래를 병합)
- **PostToolUse** 배열에 텔레메트리 블록 **추가**:
```json
{ "matcher": "mcp__.*graphify.*|mcp__.*dw-vault__dw_.*|Grep|Read|Edit|Write|MultiEdit",
  "hooks": [ { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/_build/dw-telemetry.py\"", "timeout": 10 } ] }
```
- **PreToolUse** 배열에 SSOT 쓰기 가드 블록 **추가**:
```json
{ "matcher": "Edit|Write|MultiEdit",
  "hooks": [ { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/_build/dw-vault-write-guard.py\"", "timeout": 10 } ] }
```
- **PreToolUse** 의 기존 dw-graphify-gate 항목은 그대로 두고 파일만 v2 로 교체(matcher 유지).
- `wire-hook.py` 의 배선 목록에도 위 두 훅 커맨드를 멱등 추가(대상 프로젝트 settings.json 반영).

## 3단계 — Makefile 타깃 + vault .gitignore
`Makefile`:
```make
workflow-report: $(VENV)/.stamp   ## dw 워크플로우 리포트. 사용: make workflow-report V=/abs/vault [DAYS=30]
	$(VENV)/bin/python _build/dw-workflow-report.py --vault $(V) --days $(or $(DAYS),30)
```
vault 레포 `.gitignore` 에 `.dw-state/` 추가.

## 4단계 — 검증 (전부 green)
```bash
python3 -c "import ast;[ast.parse(open(f).read()) for f in ['_build/dw-telemetry.py','_build/dw-vault-write-guard.py','_build/dw-graphify-gate.py','_build/dw-workflow-report.py']];print('syntax OK')"
python3 -c "import json;json.load(open('hooks/hooks.json'));print('hooks.json OK')"
make dry-run && make doctor
```
스모크(모드별 기대 결정 — 이 세션에서 검증된 계약):
- ② Edit rule: default→`ask`, bypassPermissions/acceptEdits→`deny`, `DW_GATE_HARD=1`→`deny`. memory(LIVE)/코드→무출력.
- ③ dw_search(graphify 미사용 세션): default→`ask`, auto/bypassPermissions→`deny`. graphify 사용 후→`additionalContext`. 리터럴 grep→침묵.

## 5단계 — 커밋 & PR
```bash
git add -A && git commit -m "feat(dw): 워크플로우 텔레메트리 + SSOT 쓰기 가드 + graphify 하드 게이트(automode deny)"
gh pr create --fill
```
머지 후 `/dw-install`. **러너 런처에 `export DW_GATE_HARD=1` 추가**(automode 하드 강제).

## 롤아웃 노트
- 텔레메트리는 설치 이후만 관측 → **2~4주** 후 `make workflow-report V=~/Documents/denver-workflow-vault`.
- 게이트는 default 세션=ask(override), automode=deny. 인터랙티브에서도 우회가 계속되면 rule/guidance
  는 default 도 deny 로 상향 고려(_HARD 로직/DW_GATE_HARD 로 조절).
- ③ 게이트는 세션당 graphify 첫 사용 후 조언 모드로 self-release.

## 마감 기록
- `dw_write_memory`: "advisory 훅은 라우팅당함 → PreToolUse 게이트, automode 는 ask 무력화라 permission_mode 로 deny 상향".
- `dw_write_procedure`: "런타임 훅 추가 절차: hooks.json+wire-hook 배선 → dry-run/doctor → 모드별 스모크 payload 검증".
