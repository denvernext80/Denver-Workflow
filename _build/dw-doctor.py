#!/usr/bin/env python3
"""dw-doctor — denver-workflow 외부 의존·vault 상태 감지.

무엇을 하나: 이 워크플로우가 기대는 외부 프로그램들 — Obsidian(팀 지식 vault 를 여는 노트 앱),
superpowers(기획·구현 순서를 잡아 주는 플러그인), impeccable(화면 디자인 검수 플러그인),
gstack(디자인·QA 스킬 모음) — 과 vault(팀 지식을 모아두는 폴더)의 설치 여부를 확인한다.

사용처: SessionStart 훅(빠진 항목 안내), /dw-setup(설치 대상 산출), make doctor.
원칙: 파일/폴더 존재 검사만 — 서브프로세스·네트워크 호출 금지(훅 15초 타임아웃 안전).
표준 라이브러리만 사용. macOS + Windows 지원(Linux 는 안내만).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def vault_dir() -> Path:
    """vault 해석 규약: DW_VAULT_DIR(env) > ~/denver-workflow-vault. (~·$HOME·%USERPROFILE% 확장)"""
    env = os.environ.get("DW_VAULT_DIR", "").strip()
    if env:
        p = Path(os.path.expandvars(os.path.expanduser(env)))
        if p.is_dir():
            return p
    return Path.home() / "denver-workflow-vault"


def _obsidian_installed() -> bool:
    if sys.platform == "darwin":
        return any(Path(p).is_dir() for p in (
            "/Applications/Obsidian.app",
            str(Path.home() / "Applications" / "Obsidian.app"),
        ))
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        return bool(local) and any((Path(local) / d).is_dir() for d in ("Obsidian", r"Programs\Obsidian"))
    return False  # Linux: 지원 예정 — 미설치로 보고해 /dw-setup 이 안내하게 한다


def _cc_plugin_installed(name: str) -> bool:
    """Claude Code 플러그인 캐시(~/.claude/plugins/cache/<마켓플레이스>/<플러그인>/) 존재 검사."""
    cache = Path.home() / ".claude" / "plugins" / "cache"
    return cache.is_dir() and any(cache.glob(f"*/{name}"))


def _gstack_installed() -> bool:
    return (Path.home() / ".claude" / "skills" / "gstack").is_dir()


def _vault_ready() -> bool:
    """vault 존재 + seed 주입 마커(VAULT-STRUCTURE.md)."""
    v = vault_dir()
    return v.is_dir() and (v / "VAULT-STRUCTURE.md").is_file()


def check_all() -> list[dict]:
    """의존 상태 목록. required=True 가 빠지면 워크플로우 핵심(vault 지식 순환)이 동작하지 않는다."""
    v = vault_dir()
    return [
        {"name": "Obsidian", "ok": _obsidian_installed(), "required": True,
         "hint": "팀 지식 vault 를 여는 노트 앱 — /dw-setup 이 설치를 대신해 드립니다"},
        {"name": "vault", "ok": _vault_ready(), "required": True,
         "hint": f"팀 지식 폴더({v}) — /dw-setup 이 기본 구조(seed)를 만들어 드립니다"},
        {"name": "superpowers", "ok": _cc_plugin_installed("superpowers"), "required": True,
         "hint": "기획·구현 순서를 잡아 주는 플러그인 — /dw-setup 이 설치해 드립니다"},
        {"name": "impeccable", "ok": _cc_plugin_installed("impeccable"), "required": False,
         "hint": "화면(UI) 디자인 검수 플러그인 — UI 작업 시 필수"},
        {"name": "gstack", "ok": _gstack_installed(), "required": False,
         "hint": "디자인·QA 스킬 모음 — 디자인/QA 단계에서 사용"},
    ]


def missing_required() -> list[str]:
    return [c["name"] for c in check_all() if c["required"] and not c["ok"]]


def main() -> int:
    checks = check_all()
    if "--json" in sys.argv:
        print(json.dumps({
            "missing": [c["name"] for c in checks if not c["ok"]],
            "missing_required": [c["name"] for c in checks if c["required"] and not c["ok"]],
            "ok": [c["name"] for c in checks if c["ok"]],
        }, ensure_ascii=False))
        return 0
    for c in checks:
        mark = "✓" if c["ok"] else ("✗" if c["required"] else "·")
        req = "필수" if c["required"] else "권장"
        print(f"  [{mark}] {c['name']:<12} ({req}) — {c['hint']}")
    miss = missing_required()
    if miss:
        print(f"\n  → 빠진 필수 항목: {', '.join(miss)}. `/dw-setup` 을 실행하세요"
              f" (설정 도우미 — 설치를 대신해 드립니다).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
