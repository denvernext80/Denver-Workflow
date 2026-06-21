#!/usr/bin/env python3
"""SSOT 결정론적 린터 — Claude Code PostToolUse 훅.

편집/생성된 파일을 vault 에서 컴파일된 검사 매니페스트(.claude/ssot-checks.json)에 비추어
검사한다. 위반이 있으면 PostToolUse 의 additionalContext 로 모델에 피드백한다(차단하지 않음 —
PostToolUse 는 이미 실행된 뒤이고, BOOTSTRAP 불변식상 검증자는 단독 게이트가 아니다).

stdin: Claude Code 훅 JSON. 사용 필드: tool_input.file_path, hook_event_name.
출력: 위반 시 {"hookSpecificOutput": {"hookEventName": "PostToolUse",
       "additionalContext": "..."}} 를 stdout 에 쓰고 exit 0. 위반 없으면 조용히 exit 0.

이 파일은 vault 의 빌드 산출물로 각 프로젝트 .claude/hooks/ 에 설치된다. 직접 편집 금지.
표준 라이브러리만 사용(pyyaml 불필요).
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from pathlib import Path

CHECKS_REL = ".claude/ssot-checks.json"
MAX_BYTES = 2_000_000  # 대용량/바이너리 파일 회피


def _project_dir(payload: dict) -> Path:
    return Path(
        os.environ.get("CLAUDE_PROJECT_DIR")
        or payload.get("cwd")
        or os.getcwd()
    )


def _rel_posix(file_path: Path, project: Path) -> str:
    try:
        return file_path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError:
        return file_path.name  # 프로젝트 밖이면 basename 으로만 매칭


def _matches(rel: str, patterns: list[str]) -> bool:
    base = rel.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(base, p) for p in patterns)


def _line_no(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # 훅 입력이 없거나 깨졌으면 조용히 통과

    if payload.get("hook_event_name") not in (None, "PostToolUse"):
        return 0

    tool_input = payload.get("tool_input") or {}
    fp = tool_input.get("file_path")
    if not fp:
        return 0
    file_path = Path(fp)

    project = _project_dir(payload)
    checks_file = project / CHECKS_REL
    if not checks_file.exists():
        return 0
    try:
        checks = json.loads(checks_file.read_text(encoding="utf-8")).get("checks", [])
    except (json.JSONDecodeError, OSError):
        return 0

    if not file_path.exists() or file_path.is_dir():
        return 0
    try:
        if file_path.stat().st_size > MAX_BYTES:
            return 0
        text = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0  # 바이너리/비텍스트는 건너뜀

    rel = _rel_posix(file_path, project)
    violations: list[str] = []

    for chk in checks:
        glob = chk.get("glob") or []
        if not glob or not _matches(rel, glob):
            continue
        if _matches(rel, chk.get("exclude") or []):
            continue

        title = chk.get("title", chk.get("rule", "?"))
        enforcer = chk.get("enforced_by", "?")
        hint = chk.get("hint", "")

        # deny: 있으면 위반
        for pat in chk.get("deny", []):
            for m in re.finditer(pat, text):
                ln = _line_no(text, m.start())
                violations.append(
                    f"[{title}] (enforced-by: {enforcer}) {rel}:{ln} "
                    f"금지 패턴 '{pat}' 발견" + (f" — {hint}" if hint else "")
                )
                break  # 규칙당 첫 매치만 보고(노이즈 억제)

        # require: 없으면 위반
        for pat in chk.get("require", []):
            if not re.search(pat, text):
                violations.append(
                    f"[{title}] (enforced-by: {enforcer}) {rel} "
                    f"필수 패턴 '{pat}' 누락" + (f" — {hint}" if hint else "")
                )

    if not violations:
        return 0

    body = "SSOT 규칙 위반이 감지되었습니다(편집한 파일). 수정 후 다시 적용하세요:\n  - " \
        + "\n  - ".join(violations)
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": body,
        }
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
