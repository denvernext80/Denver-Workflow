#!/usr/bin/env python3
"""대상 프로젝트 .claude/settings.local.json 에 vault 접근 권한을 멱등 병합.

에이전트가 (Travel-One/Balipick 세션에서) SSOT vault 를 직접 읽고, 콘텐츠 폴더에
쓰도록 권한을 사전 승인한다 — 권한 프롬프트로 살아있는 루프가 막히지 않게.
"전부 draft 경유로 쓰기 가능" 설계에 맞춰 콘텐츠 폴더(memory/contracts/rules/guidance/
decisions)에 Write/Edit 을 허용한다. 빌드 도구(_build/.claude/Makefile)는 제외.

기존 permissions.allow 는 보존(추가만). usage: grant-vault-access.py <project_dir> <vault_root>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

WRITABLE = ["project/memory", "project/contracts", "project/specs", "project/decisions",
            "governance/rules", "governance/guidance", "governance/procedures",
            "governance/_skills", "governance/agents"]


def main() -> int:
    if len(sys.argv) != 3:
        sys.stderr.write("usage: grant-vault-access.py <project_dir> <vault_root>\n")
        return 2
    project, vault = Path(sys.argv[1]), Path(sys.argv[2])
    # CC 절대경로 권한 표기: //<abs path>/**
    v = str(vault.resolve())
    perms = [f"Read(/{v}/**)"]
    for folder in WRITABLE:
        perms.append(f"Write(/{v}/{folder}/**)")
        perms.append(f"Edit(/{v}/{folder}/**)")

    sp = project / ".claude" / "settings.local.json"
    data: dict = {}
    if sp.exists():
        try:
            data = json.loads(sp.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            sys.stderr.write(f"기존 settings.local.json 파싱 실패 — 중단: {sp}\n")
            return 1

    allow = data.setdefault("permissions", {}).setdefault("allow", [])
    added = [p for p in perms if p not in allow]
    allow.extend(added)

    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  vault 접근 권한: {len(added)}개 추가, {len(perms) - len(added)}개 기존 → {sp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
