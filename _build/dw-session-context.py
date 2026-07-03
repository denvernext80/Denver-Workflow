#!/usr/bin/env python3
"""SSOT 세션 컨텍스트 주입 — Claude Code SessionStart 훅.

CC 스킬 body 는 progressive disclosure 라 자동 로드되지 않는다(description 만 항상 로드).
그래서 컴파일된 규칙·가이던스·누적 지식 인덱스가 세션 컨텍스트에 자동으로 닿지 못했다
('worktree 가이던스 무시'의 근본 원인). SessionStart 의 additionalContext 는 body 와 달리
**항상 주입**되므로(검증됨), 컴파일러가 만든 다이제스트를 세션 시작 시 직접 컨텍스트에 넣는다.

다이제스트: `$CLAUDE_PROJECT_DIR/.claude/dw-session-digest.md` (make install 이 생성).
표준 라이브러리만 사용. 출력: SessionStart additionalContext JSON. 없으면 조용히 통과.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

MAX_BYTES = 60_000  # 과도한 주입 방지(다이제스트는 보통 수 KB)


def _plugin_version(project: Path) -> str:
    """활성 플러그인 버전 — CLAUDE_PLUGIN_ROOT(플러그인 설치본) 우선, 없으면 vault_root 의 plugin.json."""
    candidates = []
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root:
        candidates.append(Path(root) / ".claude-plugin" / "plugin.json")
    cfg = project / ".claude" / "dw-config.json"
    if cfg.exists():
        try:
            vr = json.loads(cfg.read_text(encoding="utf-8")).get("vault_root")
            if vr:
                candidates.append(Path(vr) / ".claude-plugin" / "plugin.json")
        except (OSError, json.JSONDecodeError):
            pass
    for c in candidates:
        try:
            return str(json.loads(c.read_text(encoding="utf-8")).get("version", "")).strip()
        except (OSError, json.JSONDecodeError):
            continue
    return ""


def _doctor_notice() -> str:
    """필수 의존이 빠졌으면 /dw-setup 안내 문단. 실패는 조용히 무시(주입 자체를 막지 않는다)."""
    try:
        import importlib.util
        p = Path(__file__).with_name("dw-doctor.py")
        spec = importlib.util.spec_from_file_location("dw_doctor", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        missing = mod.missing_required()
    except Exception:
        return ""
    if not missing:
        return ""
    return (
        f"⚠️ denver-workflow 초기 설정 미완료 — 빠진 것: {', '.join(missing)}.\n"
        f"사용자에게 `/dw-setup` 실행을 안내하라 (설정 도우미 — 필요한 프로그램 설치와 "
        f"vault(팀 지식 폴더) 준비를 대신해 준다)."
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}
    if payload.get("hook_event_name") not in (None, "SessionStart"):
        return 0

    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd())
    digest = project / ".claude" / "dw-session-digest.md"
    text = ""
    if digest.exists():
        try:
            text = digest.read_text(encoding="utf-8")[:MAX_BYTES].strip()
        except OSError:
            text = ""
    notice = _doctor_notice()
    if not text and not notice:
        return 0
    if notice:
        text = (notice + "\n\n" + text).strip()

    # 발화 가시화: additionalContext 는 모델 컨텍스트에만 주입(UI 비가시)이라,
    # systemMessage 로 사용자에게 '주입됨' 한 줄을 보여 발화 여부 + 활성 플러그인 버전을 확인하게 한다.
    g = text.count("\n- **")       # guidance/규칙 항목 수 근사
    idx = text.count("dw_read(")  # 지식 인덱스 항목 수
    ver = _plugin_version(project)
    vtag = f" v{ver}" if ver else ""
    setup_tag = " · ⚠️ /dw-setup 필요" if notice else ""
    sysmsg = f"🔒 Denver Workflow{vtag} — 규율·규칙 {g} · 지식 인덱스 {idx}건 (전문은 dw_read){setup_tag}"

    out = {
        "systemMessage": sysmsg,
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": text,
        }
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
