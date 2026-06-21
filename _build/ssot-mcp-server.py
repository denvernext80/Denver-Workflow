#!/usr/bin/env python3
"""SSOT vault MCP 서버 — Claude Code(및 모든 MCP 클라이언트)가 vault에 연결하는 게이트웨이.

vault = SSOT. 에이전트는 raw 파일이 아니라 타입 도구로 읽고 쓴다(status 파라미터 없음 = validate-by-construction).
비준 모델(사람 비준은 제거됨):
  - LIVE(memory/contract/spec): status:stable 직행 — 읽기가 status 무관이라 게이트 무의미.
  - OBEY(procedure/rule): status:draft 제안 → ssot-ratify(결정론)가 검증 후 자동 stable 승격,
    판단 필요분만 ssot-ratifier(LLM)로 에스컬레이션. 사람 비준 불요.
  scope 는 _canonical_scope 로 쓰기 시 정규화(orphan 방지).

vault 경로는 --vault arg 로 받는다(클라이언트가 env 를 제한할 수 있으므로 env/cwd 의존 금지).
stdio MCP 서버. 의존성: mcp(FastMCP), pyyaml.
usage(클라이언트가 spawn): <venv>/bin/python ssot-mcp-server.py --vault /abs/path/to/vault
"""
from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

import yaml
from mcp.server.fastmcp import FastMCP

_ap = argparse.ArgumentParser()
_ap.add_argument("--vault", required=True)
_args, _ = _ap.parse_known_args()
VAULT = Path(_args.vault).resolve()

CONTENT_DIRS = ["governance/rules", "governance/guidance", "governance/procedures",
                "governance/_skills", "governance/agents",
                "project/memory", "project/contracts", "project/specs", "project/decisions"]
DIRECTIONS = {"backend-to-app", "app-to-backend", "shared"}
KINDS = {"request", "reply", "signoff", "contract", "notice"}
SPEC_KINDS = {"plan", "spec", "design"}

mcp = FastMCP("ssot-vault")


# --- helpers ---------------------------------------------------------------
def _iter_notes():
    for d in CONTENT_DIRS:
        base = VAULT / d
        if base.is_dir():
            for p in sorted(base.rglob("*.md")):
                # 아카이브된 옛 계약은 활성 검색·목록에서 제외(경로로 직접 ssot_read 는 가능).
                if "archive" in p.relative_to(base).parts:
                    continue
                # CC auto-memory 인덱스는 콘텐츠가 아니므로 제외.
                if p.name == "MEMORY.md":
                    continue
                yield p


def _frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def _slugify(s: str) -> str:
    s = re.sub(r"[\s/\\]+", "-", s.strip().lower())
    s = re.sub(r"[^0-9a-z가-힣ㄱ-ㅎㅏ-ㅣ_-]", "", s)
    return s.strip("-")[:60] or "note"


# scope 정규화 — 에이전트가 freeform/junk scope 를 줘도 canonical manifest scope 로 보정한다.
# (OBEY 쓰기 전용: 안 맞으면 ratifier 가 orphan 으로 hold → 컴파일 안 됨. 보정으로 항상 ratifiable.)
_SCOPE_ALIASES = {
    "backend": "backend-php", "admin": "backend-php", "web": "backend-php",
    "dev-engineering-charter": "engineering", "workspace": "engineering",
    "workflow": "engineering", "general": "engineering", "infra": "engineering",
    "orchestration": "engineering",
    "balipick-design": "design-system",
    "balipick-mobile": "mobile-flutter", "balipick-app": "mobile-flutter",
    "balipick-ios-release": "mobile-flutter", "ios": "mobile-flutter",
    "balipick-api-contract": "api-contract", "chat": "api-contract",
}


def _manifest_scopes() -> set:
    out = set()
    for p in (VAULT / "governance" / "_skills").glob("*.md"):
        try:
            sc = _frontmatter(p.read_text(encoding="utf-8")).get("scope")
        except OSError:
            sc = None
        if sc:
            out.add(str(sc).strip())
    return out


def _canonical_scope(scope: str) -> tuple[str, str]:
    """(정규화된 scope, 설명). manifest scope 면 그대로. alias 면 매핑. 그 외 단어들에서 alias 토큰을
    찾고, 못 찾으면 engineering(공유 catch-all)으로. OBEY 가 항상 컴파일 가능한 scope 를 갖게 한다."""
    raw = (scope or "").strip()
    manifests = _manifest_scopes()
    if raw in manifests:
        return raw, ""
    if raw in _SCOPE_ALIASES:
        c = _SCOPE_ALIASES[raw]
        return c, f"(scope '{raw}'→'{c}' 정규화)"
    # 여러-단어 freeform: 토큰 중 alias/manifest 매칭 시도
    for tok in re.split(r"[\s,/_-]+", raw.lower()):
        if tok in manifests:
            return tok, f"(scope '{raw}'→'{tok}' 정규화)"
        if tok in _SCOPE_ALIASES:
            c = _SCOPE_ALIASES[tok]
            return c, f"(scope '{raw}'→'{c}' 정규화)"
    return "engineering", f"(scope '{raw}' 미매칭 → engineering 으로 — 부정확하면 사람이 교정)"


def _emit(folder: str, fname: str, fm: dict, body: str) -> str:
    front = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
    content = f"---\n{front}\n---\n\n{body.strip()}\n"
    d = VAULT / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / fname).write_text(content, encoding="utf-8")
    return f"{folder}/{fname}"


# --- read tools ------------------------------------------------------------
@mcp.tool()
def ssot_search(query: str, limit: int = 20) -> list[dict]:
    """SSOT vault(규칙·원칙·메모리·계약)에서 query 를 검색한다. 작업 전 관련 학습·규칙·계약을 찾을 때 쓴다."""
    q = query.lower()
    out: list[dict] = []
    for p in _iter_notes():
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        if q not in text.lower():
            continue
        fm = _frontmatter(text)
        idx = text.lower().find(q)
        out.append({
            "path": str(p.relative_to(VAULT)),
            "type": fm.get("type") or ("auto-memory" if fm.get("name") else ""),
            "title": fm.get("title") or fm.get("name") or p.stem,
            "snippet": text[max(0, idx - 40): idx + 120].replace("\n", " "),
        })
        if len(out) >= limit:
            break
    return out


@mcp.tool()
def ssot_read(name: str) -> str:
    """SSOT vault 노트 하나의 전체 내용을 읽는다. name=상대경로 또는 파일명 stem."""
    target = (VAULT / name) if name.endswith(".md") else None
    if target and target.is_file():
        return target.read_text(encoding="utf-8")
    stem = name[:-3] if name.endswith(".md") else name
    for p in _iter_notes():
        if p.stem == stem or str(p.relative_to(VAULT)) == name:
            return p.read_text(encoding="utf-8")
    return f"(찾을 수 없음: {name})"


@mcp.tool()
def ssot_list(note_type: str = "") -> list[dict]:
    """SSOT vault 노트 목록(선택: note_type=rule|guidance|memory|contract|decision 으로 필터). 둘러볼 때 쓴다."""
    out = []
    for p in _iter_notes():
        fm = _frontmatter(p.read_text(encoding="utf-8"))
        ty = fm.get("type", "")
        if note_type and ty != note_type:
            continue
        out.append({"path": str(p.relative_to(VAULT)),
                    "type": ty or ("auto-memory" if fm.get("name") else ""),
                    "status": fm.get("status", ""),
                    "title": fm.get("title") or fm.get("name") or p.stem})
    return out


# --- write tools (전부 하드 draft 게이트) ----------------------------------
@mcp.tool()
def ssot_write_memory(scope: str, title: str, learning: str,
                      evidence: str = "", apply: str = "", agent: str = "") -> str:
    """에이전트 학습을 vault memory/ 에 기록한다(status:stable — LIVE 콘텐츠는 즉시 사용 가능).
    비자명한 학습만 — 레포·git 기록은 중복 금지. memory 는 비컴파일 LIVE 라 강제되지 않으므로 사람 비준 불요.
    evidence=근거(file:line·커밋), apply=다음에 행동을 어떻게 바꾸는가."""
    today = datetime.date.today().isoformat()
    fm = {"type": "memory", "status": "stable", "scope": scope or "general",
          "agent": agent or "mcp-client", "date": today, "title": title, "source": "ssot mcp"}
    body = learning.strip()
    if evidence.strip():
        body += f"\n\n**증거:** {evidence.strip()}"
    if apply.strip():
        body += f"\n\n**적용:** {apply.strip()}"
    path = _emit("project/memory", f"{today}-{_slugify(title)}.md", fm, body)
    return f"기록됨: {path} — LIVE 메모리라 ssot_search 로 즉시 검색됩니다(비준 불요)."


@mcp.tool()
def ssot_write_contract(direction: str, kind: str, title: str, body: str, scope: str = "") -> str:
    """백엔드↔앱 계약(요청/회신/sign-off)을 vault contracts/ 에 기록한다(status:stable — LIVE 라 즉시 사용 가능).
    direction=backend-to-app|app-to-backend|shared, kind=request|reply|signoff|contract|notice.
    계약은 비컴파일 LIVE SSOT 라 사람 비준 불요. 완결분만 contracts/archive/ 로 옮긴다(활성 검색 제외)."""
    if direction not in DIRECTIONS:
        return f"(거부) direction 은 {sorted(DIRECTIONS)} 중 하나여야 합니다."
    if kind not in KINDS:
        return f"(거부) kind 는 {sorted(KINDS)} 중 하나여야 합니다."
    today = datetime.date.today().isoformat()
    side = {"backend-to-app": "backend", "app-to-backend": "app", "shared": "shared"}[direction]
    fm = {"type": "contract", "status": "stable", "scope": scope or "api-contract",
          "date": today, "direction": direction, "kind": kind, "title": title}
    path = _emit("project/contracts", f"{today}-{side}-{kind}-{_slugify(title)}.md", fm, body)
    return f"기록됨: {path} — LIVE 계약이라 ssot_search 로 즉시 검색됩니다(비준 불요)."


@mcp.tool()
def ssot_write_spec(scope: str, title: str, body: str, kind: str = "spec") -> str:
    """기능 구현 계획·스펙·설계를 vault specs/ 에 기록한다(status:stable — LIVE 라 즉시 사용 가능).

    스펙·계획은 vault SSOT 에 둔다 — repo/worktree 에 두면 worktree 청소 시 휘발된다.
    kind=plan|spec|design. spec 은 비컴파일 LIVE 라 사람 비준 불요. repo 코드 경로는 본문에 링크로 남긴다.
    """
    if kind not in SPEC_KINDS:
        return f"(거부) kind 는 {sorted(SPEC_KINDS)} 중 하나여야 합니다."
    today = datetime.date.today().isoformat()
    fm = {"type": "spec", "status": "stable", "scope": scope or "general",
          "date": today, "kind": kind, "title": title}
    path = _emit("project/specs", f"{today}-{_slugify(title)}.md", fm, body)
    return f"기록됨: {path} — vault SSOT 에 보존(worktree 휘발 방지). LIVE 라 ssot_search 로 즉시 검색."


@mcp.tool()
def ssot_write_procedure(scope: str, title: str, steps: str) -> str:
    """재사용 가능한 절차(playbook/how-to)를 vault procedures/ 에 기록한다(항상 status:draft).

    비자명한 작업을 풀어낸 뒤 "다음에 또 이걸 어떻게 하지"를 절차로 남긴다(Hermes 식 자동 스킬 생성을
    Denver 거버넌스로 감싼 것). draft 로 제안하면 ssot-ratifier 가 검증 후 자동 stable·컴파일한다.
    rule(강제)이 아니라 reusable how-to 다 — enforced-by 없음. steps 는 번호 단계로.
    """
    today = datetime.date.today().isoformat()
    scope, note = _canonical_scope(scope)
    fm = {"type": "procedure", "status": "draft", "scope": scope,
          "compiles-to": "skill", "date": today, "title": title}
    path = _emit("governance/procedures", f"{_slugify(title)}.md", fm, steps)
    return (f"제안됨(draft): {path} {note}— draft 라 아직 컴파일 안 됨. "
            "ssot-ratifier 가 검증 통과 시 자동 stable·`make install` 합니다(사람 불요).")


@mcp.tool()
def ssot_propose_rule(scope: str, title: str, rule: str, enforced_by: str) -> str:
    """규칙 변경을 vault rules/ 에 제안한다(항상 status:draft — 절대 stable 아님).
    draft 규칙은 컴파일되지 않아 강제되지 않는다. ssot-ratifier 가 검증(스키마·enforced-by 실재·충돌 없음·
    check 패턴을 실제 코드에 돌려 오탐 0)을 통과시키면 자동 stable·컴파일한다 — 탈락 시 draft 유지·사유 주석.
    enforced_by 는 실재 검증자(security-qa|code-review|design-review|perf-tester)여야 한다."""
    scope, note = _canonical_scope(scope)
    fm = {"type": "rule", "status": "draft", "scope": scope, "enforced-by": enforced_by,
          "compiles-to": "skill", "title": title}
    path = _emit("governance/rules", f"{_slugify(title)}.md", fm, rule)
    return (f"제안됨(draft): {path} {note}— draft 라 아직 강제되지 않습니다. "
            "ssot-ratifier 가 검증 통과 시 자동 stable·`make install` 합니다(사람 불요).")


if __name__ == "__main__":
    sys.stderr.write(f"[ssot-vault mcp] vault={VAULT}\n")
    mcp.run()
