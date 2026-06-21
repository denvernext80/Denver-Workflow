#!/usr/bin/env python3
"""Denver 플러그인 활성 범위(scope) 설정 — 사용자 전역 vs 프로젝트 한정.

CC 는 `claude plugin install` 시 플러그인을 계정 전역에 설치하고, 활성 범위는 settings.json 의
`enabledPlugins` 로 결정한다(설정 계층 user→project→local). 이 스크립트로 범위를 고른다:

  user    : 계정 settings.json 에 enabledPlugins[id]=true  → 모든 프로젝트에서 활성(기본).
  project : 프로젝트 .claude/settings.json 에 true, 계정 레벨엔 false → 그 프로젝트만 활성.
  off     : 계정·프로젝트 모두 false(비활성).

read-merge-write(기존 설정 보존). 표준 라이브러리만.
usage:
  ssot-plugin-scope.py user                         [--plugin ID] [--account-dir DIR]
  ssot-plugin-scope.py project <project_dir>         [--plugin ID] [--account-dir DIR]
  ssot-plugin-scope.py off     [<project_dir>]       [--plugin ID] [--account-dir DIR]
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

DEFAULT_PLUGIN = "denver-agent@denver-agent"


def load(p: Path) -> dict:
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raise SystemExit(f"파싱 실패(안전 중단): {p}")
    return {}


def set_enabled(path: Path, plugin: str, value: bool | None) -> None:
    """enabledPlugins[plugin] 를 설정(value=None 이면 키 제거). 기타 설정 보존."""
    path.parent.mkdir(parents=True, exist_ok=True)
    s = load(path)
    ep = s.setdefault("enabledPlugins", {})
    if value is None:
        ep.pop(plugin, None)
    else:
        ep[plugin] = value
    if not ep:
        s.pop("enabledPlugins", None)
    path.write_text(json.dumps(s, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["user", "project", "off"])
    ap.add_argument("project_dir", nargs="?")
    ap.add_argument("--plugin", default=DEFAULT_PLUGIN)
    ap.add_argument("--account-dir", default=os.environ.get("CLAUDE_CONFIG_DIR")
                    or str(Path.home() / ".claude"))
    args = ap.parse_args()

    account = Path(args.account_dir).expanduser() / "settings.json"
    proj = (Path(args.project_dir).expanduser() / ".claude" / "settings.json"
            if args.project_dir else None)

    if args.mode == "user":
        set_enabled(account, args.plugin, True)
        print(f"✓ 사용자 전역 활성: {args.plugin} → {account}")
        print("  (모든 프로젝트 세션에서 Denver 엔진 활성)")
    elif args.mode == "project":
        if not proj:
            raise SystemExit("project 모드는 <project_dir> 필요")
        set_enabled(account, args.plugin, False)       # 전역 비활성
        set_enabled(proj, args.plugin, True)           # 이 프로젝트만 활성
        print(f"✓ 프로젝트 한정 활성: {args.plugin}")
        print(f"  계정 false → {account}")
        print(f"  프로젝트 true → {proj}")
        print("  (이 프로젝트 세션에서만 Denver 엔진 활성)")
    else:  # off
        set_enabled(account, args.plugin, False)
        if proj:
            set_enabled(proj, args.plugin, None)
        print(f"✓ 비활성: {args.plugin}")
    print("\n  ⚠️ 설정 반영은 새 세션부터. (CC 가 project-scope enabledPlugins 를 존중하는지는 "
          "세션에서 최종 확인 — 안 되면 user 모드로 폴백.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
