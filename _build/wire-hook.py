#!/usr/bin/env python3
"""대상 프로젝트 .claude/settings.json 에 SSOT 훅을 멱등 병합.

세 훅을 배선한다:
  - ssot-lint.py        (PostToolUse) : 편집한 프로젝트 코드 파일을 결정론적 검사
  - ssot-vault-guard.py (PostToolUse) : 편집한 vault(.md) 노트의 frontmatter 계약 + draft 게이트
  - ssot-worktree-guard.py (PreToolUse): Agent/Task spawn 시 worktree 격리 미확인이면 ask

worktree 가드만 PreToolUse(spawn 시점에 끼어들어야 강제 가능 — PostToolUse 는 grep 할 파일
자국이 없어 구조적으로 못 잡는다). 나머지는 PostToolUse 피드백 전용.

vault_root 가 주어지면 .claude/ssot-config.json 에 기록해 가드가 vault 위치를 알게 한다.
기존 설정(permissions, 다른 hooks)은 절대 덮어쓰지 않는다. 재실행 안전(멱등).

usage: wire-hook.py <project_dir> [vault_root]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# event -> (matcher, [(command, marker), ...]). matcher=None → 매처 없는 이벤트(SessionStart 등).
POST_MATCHER = "Edit|Write|MultiEdit"
PRE_MATCHER = "Agent|Task"
WIRING = {
    "PostToolUse": (POST_MATCHER, [
        ('python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/ssot-lint.py"', "ssot-lint.py"),
        ('python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/ssot-vault-guard.py"', "ssot-vault-guard.py"),
        ('python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/ssot-artifact-guard.py"', "ssot-artifact-guard.py"),
    ]),
    "PreToolUse": (PRE_MATCHER, [
        ('python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/ssot-worktree-guard.py"', "ssot-worktree-guard.py"),
    ]),
    "SessionStart": (None, [
        ('python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/ssot-session-context.py"', "ssot-session-context.py"),
    ]),
}


def wired_markers(settings: dict, event: str, hooks: list) -> set[str]:
    found = set()
    for group in settings.get("hooks", {}).get(event, []):
        for h in group.get("hooks", []):
            for _, marker in hooks:
                if marker in str(h.get("command", "")):
                    found.add(marker)
    return found


def remove_ssot_hooks(settings: dict) -> int:
    """settings.json 에서 SSOT 훅(ssot-*.py) 그룹을 제거. 반환: 제거 수.
    플러그인이 훅을 전역 제공하므로 프로젝트-로컬 wire 를 걷어내 중복(이중 발화)을 없앤다."""
    removed = 0
    for event in list(settings.get("hooks", {})):
        groups = settings["hooks"][event]
        kept = []
        for g in groups:
            ghooks = [h for h in g.get("hooks", []) if "ssot-" not in str(h.get("command", ""))]
            if not ghooks:
                removed += 1  # 그룹 전체가 SSOT 훅이었음
                continue
            g["hooks"] = ghooks
            kept.append(g)
        if kept:
            settings["hooks"][event] = kept
        else:
            del settings["hooks"][event]
    if "hooks" in settings and not settings["hooks"]:
        del settings["hooks"]
    return removed


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not 1 <= len(args) <= 2:
        sys.stderr.write("usage: wire-hook.py <project_dir> [vault_root] [--config-only|--remove]\n")
        return 2
    project = Path(args[0])
    vault_root = args[1] if len(args) == 2 else None
    config_only = "--config-only" in flags  # 플러그인 모드: 훅 안 걸고 config 만
    remove = "--remove" in flags             # 정리 모드: SSOT 훅 제거
    settings_path = project / ".claude" / "settings.json"

    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            sys.stderr.write(f"기존 settings.json 파싱 실패 — 안전을 위해 중단: {settings_path}\n")
            return 1

    added: list[str] = []
    if remove:
        n = remove_ssot_hooks(settings)
        print(f"  SSOT 훅 제거: {n}건 → {settings_path} (플러그인이 전역 제공)")
    elif not config_only:
        hooks = settings.setdefault("hooks", {})
        for event, (matcher, hook_list) in WIRING.items():
            have = wired_markers(settings, event, hook_list)
            bucket = hooks.setdefault(event, [])
            for cmd, marker in hook_list:
                if marker in have:
                    continue
                group: dict = {"hooks": [{"type": "command", "command": cmd, "timeout": 15}]}
                if matcher is not None:
                    group["matcher"] = matcher
                bucket.append(group)
                added.append(marker)

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if vault_root:
        cfg = project / ".claude" / "ssot-config.json"
        cfg.write_text(json.dumps({"vault_root": vault_root}, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")

    if config_only:
        print(f"  config-only: ssot-config.json 기록(훅은 플러그인 전역 제공) → {settings_path}")
    if added:
        print(f"  훅 병합: {', '.join(added)} → {settings_path}")
    else:
        print(f"  이미 설치됨(멱등): {settings_path}")
    if vault_root:
        print(f"  vault_root 기록: {vault_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
