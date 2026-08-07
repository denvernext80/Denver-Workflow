#!/usr/bin/env python3
"""대상 프로젝트 .claude/settings.json 에 SSOT 훅을 멱등 병합.

배선하는 훅:
  - dw-lint.py             (PostToolUse) : 편집한 프로젝트 코드 파일을 결정론적 검사
  - dw-vault-guard.py      (PostToolUse) : 편집한 vault(.md) 노트의 frontmatter 계약 + draft 게이트
  - dw-artifact-guard.py   (PostToolUse) : 컴파일 산출물 직접편집 감지
  - dw-telemetry.py        (PostToolUse) : 도구 사용 분포 관측(비파괴 — 결코 차단하지 않는다)
  - dw-worktree-guard.py   (PreToolUse)  : Agent/Task spawn 시 worktree 격리 미확인이면 ask
  - dw-vault-write-guard.py(PreToolUse)  : OBEY 노트 직접편집 차단(ask/deny)

**강제가 필요한 것은 PreToolUse 여야 한다.** PostToolUse 는 이미 일어난 뒤라 조언(additionalContext)
밖에 못 하고, 조언은 라우팅당한다 — worktree 가드(spawn 시점에 끼어들어야 함)와 SSOT 쓰기 가드
(편집 전에 막아야 함)가 그래서 PreToolUse 다. 나머지는 PostToolUse 피드백·관측 전용.

⚠️ 이벤트당 매처가 여럿일 수 있다 — 같은 PreToolUse 라도 worktree 가드는 `Agent|Task`, 쓰기
가드는 `Edit|Write|MultiEdit` 를 본다. WIRING 값이 **(matcher, hooks) 리스트**인 이유다.

vault_root 가 주어지면 .claude/dw-config.json 에 기록해 가드가 vault 위치를 알게 한다.
기존 설정(permissions, 다른 hooks)은 절대 덮어쓰지 않는다. 재실행 안전(멱등).

usage: wire-hook.py <project_dir> [vault_root]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# event -> [(matcher, [(command, marker), ...]), ...]. matcher=None → 매처 없는 이벤트(SessionStart 등).
# 이벤트당 그룹이 여럿인 이유는 모듈 docstring 참조(같은 이벤트라도 훅마다 보는 도구가 다르다).
EDIT_MATCHER = "Edit|Write|MultiEdit"
PRE_MATCHER = "Agent|Task"
# 텔레메트리는 '무엇을 썼나' 분포를 보는 것이라 관련 도구를 넓게 받는다(비파괴 — 항상 통과시킨다).
TELEMETRY_MATCHER = "mcp__.*graphify.*|mcp__.*dw-vault__dw_.*|Grep|Read|Edit|Write|MultiEdit"


def _cmd(name: str) -> tuple[str, str]:
    return (f'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/{name}"', name)


WIRING = {
    "PostToolUse": [
        (EDIT_MATCHER, [
            _cmd("dw-lint.py"),
            _cmd("dw-vault-guard.py"),
            _cmd("dw-artifact-guard.py"),
        ]),
        (TELEMETRY_MATCHER, [_cmd("dw-telemetry.py")]),
    ],
    "PreToolUse": [
        (PRE_MATCHER, [_cmd("dw-worktree-guard.py")]),
        (EDIT_MATCHER, [_cmd("dw-vault-write-guard.py")]),
    ],
    "SessionStart": [
        (None, [_cmd("dw-session-context.py")]),
    ],
}


def wired_markers(settings: dict, event: str, hooks: list) -> set[str]:
    found = set()
    for group in settings.get("hooks", {}).get(event, []):
        for h in group.get("hooks", []):
            for _, marker in hooks:
                if marker in str(h.get("command", "")):
                    found.add(marker)
    return found


def remove_dw_hooks(settings: dict) -> int:
    """settings.json 에서 SSOT 훅(dw-*.py) 그룹을 제거. 반환: 제거 수.
    플러그인이 훅을 전역 제공하므로 프로젝트-로컬 wire 를 걷어내 중복(이중 발화)을 없앤다."""
    removed = 0
    for event in list(settings.get("hooks", {})):
        groups = settings["hooks"][event]
        kept = []
        for g in groups:
            ghooks = [h for h in g.get("hooks", []) if "dw-" not in str(h.get("command", ""))]
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
        n = remove_dw_hooks(settings)
        print(f"  SSOT 훅 제거: {n}건 → {settings_path} (플러그인이 전역 제공)")
    elif not config_only:
        hooks = settings.setdefault("hooks", {})
        for event, groups in WIRING.items():
            bucket = hooks.setdefault(event, [])
            for matcher, hook_list in groups:
                # 멱등: 마커가 그 이벤트의 **어느 그룹에든** 이미 있으면 건너뛴다.
                have = wired_markers(settings, event, hook_list)
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
        cfg = project / ".claude" / "dw-config.json"
        cfg.write_text(json.dumps({"vault_root": vault_root}, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")

    if config_only:
        print(f"  config-only: dw-config.json 기록(훅은 플러그인 전역 제공) → {settings_path}")
    if added:
        print(f"  훅 병합: {', '.join(added)} → {settings_path}")
    else:
        print(f"  이미 설치됨(멱등): {settings_path}")
    if vault_root:
        print(f"  vault_root 기록: {vault_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
