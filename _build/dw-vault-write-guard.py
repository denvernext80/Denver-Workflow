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


def _cfg_dirs(project):
    """dw-config.json 을 찾을 후보 — project → 조상 → 본체 레포(git worktree 대응).

    do-er 서브에이전트는 git worktree 에서 돈다. 워크트리는 `.claude/` 가 gitignore 라 체크아웃되지
    않아 `<worktree>/.claude/dw-config.json` 이 **없다**. 종전엔 그때 `DW_VAULT_DIR` env 폴백에만
    기댔고, env 가 없는 환경(러너·다른 셸)에서는 vault 를 못 찾아 훅이 조용히 무력화됐다.
    """
    out = []
    cur = project.resolve()
    for _ in range(8):
        out.append(cur)
        if cur.parent == cur:
            break
        cur = cur.parent
    try:
        import subprocess
        r = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=str(project),
                           capture_output=True, text=True, timeout=3)
        if r.returncode == 0 and r.stdout.strip():
            cp = Path(r.stdout.strip())
            if not cp.is_absolute():
                cp = (project / cp).resolve()
            out.append(cp.parent)          # 본체 레포 루트
    except Exception:
        pass
    return out


def _vault_root(project: Path):
    for _d in _cfg_dirs(project):
        cfg = _d / ".claude" / "dw-config.json"
        if not cfg.exists():
            continue
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
