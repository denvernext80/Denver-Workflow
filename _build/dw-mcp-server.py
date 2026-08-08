#!/usr/bin/env python3
"""SSOT vault MCP 서버 — Claude Code(및 모든 MCP 클라이언트)가 vault에 연결하는 게이트웨이.

vault = SSOT. 에이전트는 raw 파일이 아니라 타입 도구로 읽고 쓴다(status 파라미터 없음 = validate-by-construction).
비준 모델(사람 비준은 제거됨):
  - LIVE(memory/contract/spec): status:stable 직행 — 읽기가 status 무관이라 게이트 무의미.
  - OBEY(procedure/rule): status:draft 제안 → dw-ratify(결정론)가 검증 후 자동 stable 승격,
    판단 필요분만 dw-ratifier(LLM)로 에스컬레이션. 사람 비준 불요.
  scope 는 _canonical_scope 로 쓰기 시 정규화(orphan 방지).

vault 경로는 --vault arg 로 받는다(클라이언트가 env 를 제한할 수 있으므로 env/cwd 의존 금지).
stdio MCP 서버. 의존성: mcp(FastMCP), pyyaml.
usage(클라이언트가 spawn): <venv>/bin/python dw-mcp-server.py --vault /abs/path/to/vault
"""
from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

import yaml
from mcp.server.fastmcp import FastMCP

import dw_verify  # check 패턴 검증 — 비준기와 공유하는 단일 정본(예측 ≠ 실제 를 막는다)

_ap = argparse.ArgumentParser()
_ap.add_argument("--vault", required=True)
_args, _ = _ap.parse_known_args()
VAULT = Path(_args.vault).resolve()

CONTENT_DIRS = ["governance/rules", "governance/guidance", "governance/procedures",
                "governance/_skills", "governance/agents",
                "project/memory", "project/contracts", "project/specs",
                "project/decisions", "project/backlog", "project/reference"]
DIRECTIONS = {"backend-to-app", "app-to-backend", "shared"}
KINDS = {"request", "reply", "signoff", "contract", "notice"}
SPEC_KINDS = {"plan", "spec", "design"}
SIGNOFF_STATES = {"pending", "agreed"}      # 양측 최종 합의 여부(status=비준상태와 별개)
BLOCKING_STATES = {"blocking", "non-blocking"}  # 소비측 차단 여부(§5 "차단/비차단 명시")

mcp = FastMCP("dw-vault")


# --- helpers ---------------------------------------------------------------
def _iter_notes():
    for d in CONTENT_DIRS:
        base = VAULT / d
        if base.is_dir():
            for p in sorted(base.rglob("*.md")):
                # 아카이브된 옛 계약은 활성 검색·목록에서 제외(경로로 직접 dw_read 는 가능).
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
def _score(query: str, title_low: str, text_low: str) -> tuple[int, int]:
    """(관련도 점수, 스니펫 앵커 위치). 점수 0 = 미매치.

    ⚠️ 종전 구현은 `query` **전체 문자열**을 본문에서 substring 으로만 찾았다. 어순·띄어쓰기까지
    정확히 일치해야 해서 자연어 다단어 질의가 **조용히 0 건**을 반환했고, 그 0 건이 "vault 에 없다"
    로 오독돼 중복 노트 생성·기록된 함정 재발을 실제로 일으켰다(백로그 2026-07-30, 3회 재현).
    그래서 토큰 단위 OR + 관련도 정렬로 바꾼다.
    """
    q = query.lower().strip()
    if not q:
        return 0, 0
    score, anchor, whole = 0, -1, text_low.find(q)
    if whole >= 0:            # 질의 전체가 연속 등장 — 가장 강한 신호(종전의 유일한 조건).
        score += 10
        anchor = whole
    if q in title_low:
        score += 10
    tokens = [t for t in q.split() if t]
    hit = 0
    for t in tokens:
        if t in title_low:    # 제목 일치는 본문보다 무겁게.
            score += 3
        pos = text_low.find(t)
        if pos >= 0:
            score += 1
            hit += 1
            if anchor < 0:
                anchor = pos
    if tokens and hit:        # 커버리지 — 질의 토큰을 많이 덮을수록 위로.
        score += int(6 * hit / len(tokens))
    matched = hit > 0 or whole >= 0 or q in title_low
    return (score if matched else 0), max(anchor, 0)


@mcp.tool()
def dw_search(query: str, limit: int = 20) -> list[dict]:
    """SSOT vault(규칙·원칙·메모리·계약)에서 query 를 검색한다. 작업 전 관련 학습·규칙·계약을 찾을 때 쓴다.

    공백으로 나눈 토큰 중 **하나라도** 맞으면 후보이고, 관련도(제목 일치·질의 전체 일치·토큰 커버리지)
    순으로 정렬해 상위 limit 개를 돌려준다. 종전처럼 앞에서부터 limit 개를 채우고 끊지 않으므로
    가장 관련 있는 노트가 순회 뒤쪽에 있어도 누락되지 않는다.
    """
    scored: list[tuple[int, dict]] = []
    for p in _iter_notes():
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = _frontmatter(text)
        title = fm.get("title") or fm.get("name") or p.stem
        s, idx = _score(query, title.lower(), text.lower())
        if s <= 0:
            continue
        scored.append((s, {
            "path": str(p.relative_to(VAULT)),
            "type": fm.get("type") or ("auto-memory" if fm.get("name") else ""),
            "title": title,
            "snippet": text[max(0, idx - 40): idx + 120].replace("\n", " "),
        }))
    scored.sort(key=lambda x: (-x[0], x[1]["path"]))
    return [d for _, d in scored[:limit]]


@mcp.tool()
def dw_read(name: str) -> str:
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
def dw_list(note_type: str = "") -> list[dict]:
    """SSOT vault 노트 목록(선택: note_type=rule|guidance|memory|contract|decision|backlog|reference 으로 필터). 둘러볼 때 쓴다."""
    out = []
    for p in _iter_notes():
        fm = _frontmatter(p.read_text(encoding="utf-8"))
        ty = fm.get("type", "")
        if note_type and ty != note_type:
            continue
        entry = {"path": str(p.relative_to(VAULT)),
                 "type": ty or ("auto-memory" if fm.get("name") else ""),
                 "status": fm.get("status", ""),
                 "title": fm.get("title") or fm.get("name") or p.stem}
        # 계약은 sign-off·차단 상태를 목록에서 한눈에(있을 때만 노출 — 다른 타입 노이즈 없음).
        for k in ("signoff", "blocking"):
            if fm.get(k):
                entry[k] = fm[k]
        out.append(entry)
    return out


# --- write tools (전부 하드 draft 게이트) ----------------------------------
@mcp.tool()
def dw_write_memory(scope: str, title: str, learning: str,
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
    return f"기록됨: {path} — LIVE 메모리라 dw_search 로 즉시 검색됩니다(비준 불요)."


@mcp.tool()
def dw_write_backlog(scope: str, title: str, item: str,
                     context: str = "", agent: str = "") -> str:
    """후속·백로그 항목을 vault backlog/ 에 기록한다(status:stable — LIVE 라 즉시 검색 가능).

    **프로젝트 repo 에 BACKLOG.md·TODO 류 파일을 만들지 마라** — worktree 청소·브랜치 삭제 시
    휘발하고 팀이 못 본다. 나중에 다룰 후속 작업(발견했지만 이번 범위 밖)은 여기 vault 로 남긴다.
    backlog 는 비컴파일 LIVE 라 강제되지 않으므로 사람 비준 불요. item=무엇을 해야 하나,
    context=어디서 나왔나·왜(file:line·커밋·연관). **완료하면 `dw_resolve(name)` 로 archive 이동**
    (status 는 비준상태라 완료 표시가 아니다 — 완료/미완료는 archive 이동으로 구분한다)."""
    today = datetime.date.today().isoformat()
    fm = {"type": "backlog", "status": "stable", "scope": scope or "general",
          "agent": agent or "mcp-client", "date": today, "title": title, "source": "ssot mcp"}
    body = item.strip()
    if context.strip():
        body += f"\n\n**맥락:** {context.strip()}"
    path = _emit("project/backlog", f"{today}-{_slugify(title)}.md", fm, body)
    return f"기록됨: {path} — LIVE 백로그라 dw_search/dw_list(note_type=backlog)로 즉시 조회됩니다(비준 불요)."


@mcp.tool()
def dw_write_reference(scope: str, title: str, body: str, source: str = "", agent: str = "") -> str:
    """스냅샷형 참조 문서를 vault reference/ 에 기록한다(status:stable — LIVE 라 즉시 검색 가능).

    reference = **현재 시스템 상태의 스냅샷 추출** — DB 스키마 덤프, API 전수 인덱스, 아키텍처
    다이어그램 등. "할 일"(backlog)이나 "구현 계획"(spec)이 아니라 "지금 시스템이 어떻게 생겼나"의
    캡처다. **완료/미완료가 없다** — 오직 최신 vs 드리프트(stale)만 있으므로 `dw_resolve` 대상이
    아니다(archive 라이프사이클 없음). 드리프트 감지 시 **재추출(같은 title 로 새 스냅샷 교체)**이
    정본 조치 — 재추출이 당장 안 되면 본문 상단에 스테일 경고만 붙이고 유지한다(삭제/archive 하면
    유일한 참조를 잃음). source=추출 근거·시점(덤프 명령·커밋·날짜). 계획/설계면 dw_write_spec 을 쓴다."""
    today = datetime.date.today().isoformat()
    fm = {"type": "reference", "status": "stable", "scope": scope or "general",
          "agent": agent or "mcp-client", "date": today, "title": title, "source": "ssot mcp"}
    text = body.strip()
    if source.strip():
        text += f"\n\n**추출 근거:** {source.strip()}"
    # 날짜 없는 slug 파일명 — reference 는 "최신 1개"라 같은 title 재추출 시 덮어써 교체한다
    # (추출 시점은 frontmatter date 가 추적). date-prefix 면 재추출이 교체가 아니라 중복이 됨.
    path = _emit("project/reference", f"{_slugify(title)}.md", fm, text)
    return (f"기록됨: {path} — LIVE 참조라 dw_search/dw_list(note_type=reference)로 즉시 조회됩니다(비준 불요). "
            "드리프트 시 같은 title 로 다시 부르면 이 파일을 덮어써 교체합니다(완료 개념 없음 — dw_resolve 대상 아님).")


# project/ LIVE 산출물 중 완료/적용 라이프사이클이 있는 타입 — archive/ 관례로 완료를 표현한다.
# (memory·decision 은 완료 개념이 없어 제외. reference 는 완료가 아니라 최신/드리프트만 있어 제외 —
#  드리프트는 재추출로 교체. status 는 비준상태라 완료 표시가 아님 → 이동으로 구분.)
_RESOLVABLE_DIRS = ["project/backlog", "project/specs", "project/contracts"]


@mcp.tool()
def dw_resolve(name: str, resolution: str = "") -> str:
    """LIVE 프로젝트 산출물(백로그·스펙/계획·계약)을 완료/적용 처리한다 — 해당 폴더의 `archive/` 로
    옮겨 활성 목록에서 내린다. `status`(비준상태)로는 완료/미완료를 못 나눠서, 완료는 archive 이동으로
    표현한다(dw_search·dw_list·세션 다이제스트 모두 archive 제외 → 활성 뷰엔 미완료만 남음).

    name=파일명 stem 또는 상대경로. resolution=어떻게 됐나(구현 PR·커밋·결정 — 이력에 남긴다).
    대상: backlog(완료)·spec(구현/적용 완료)·contract(완결). 완료분은 경로로 직접 `dw_read` 는 가능."""
    stem = name[:-3] if name.endswith(".md") else name
    base_dir: Path | None = None
    target: Path | None = None
    for d in _RESOLVABLE_DIRS:
        base = VAULT / d
        if not base.is_dir():
            continue
        for p in sorted(base.glob("*.md")):  # 최상위만 매칭 = 활성(archive/ 하위 자동 제외)
            if p.stem == stem or p.name == name or str(p.relative_to(VAULT)) == name:
                base_dir, target = base, p
                break
        if target:
            break
    if target is None:
        return (f"(찾을 수 없음: {name}) — 활성 backlog/specs/contracts 에 없습니다. "
                "이미 완료(archive)됐거나 이름이 다를 수 있습니다. dw_list 로 확인하세요.")
    today = datetime.date.today().isoformat()
    note = resolution.strip() or "완료"
    text = target.read_text(encoding="utf-8").rstrip() + f"\n\n**완료/적용:** {note} ({today})\n"
    archive = base_dir / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    (archive / target.name).write_text(text, encoding="utf-8")
    target.unlink()
    rel = base_dir.relative_to(VAULT).as_posix()
    return (f"완료 처리: {target.name} → {rel}/archive/ 로 이동했습니다. "
            "활성 목록(dw_search·dw_list)에서 내려갔고, 원문은 경로로 dw_read 하면 이력이 남습니다.")


@mcp.tool()
def dw_write_contract(direction: str, kind: str, title: str, body: str, scope: str = "",
                      signoff: str = "pending", blocking: str = "blocking") -> str:
    """백엔드↔앱 계약(요청/회신/sign-off)을 vault contracts/ 에 기록한다(status:stable — LIVE 라 즉시 사용 가능).
    direction=backend-to-app|app-to-backend|shared, kind=request|reply|signoff|contract|notice.

    **signoff** = 양측 최종 합의 상태(`pending`|`agreed`) — `status`(비준상태)와 별개다. 요청/제안은
    `pending`, 양측 합의된 최종 계약은 `agreed` 로 쓴다. **blocking** = 소비측 차단 여부(`blocking`|
    `non-blocking`) — 합의 전까지 소비측이 진행 못 하면 `blocking`(안전 기본값). 둘 다 frontmatter 에
    남아 `dw_list` 로 한눈에 보인다(§5 "sign-off, 차단/비차단 명시"의 구조화).

    계약은 비컴파일 LIVE SSOT 라 사람 비준 불요. **완결분은 `dw_resolve(name)` 로 contracts/archive/ 이동**
    (활성 검색 제외)."""
    if direction not in DIRECTIONS:
        return f"(거부) direction 은 {sorted(DIRECTIONS)} 중 하나여야 합니다."
    if kind not in KINDS:
        return f"(거부) kind 는 {sorted(KINDS)} 중 하나여야 합니다."
    if signoff not in SIGNOFF_STATES:
        return f"(거부) signoff 는 {sorted(SIGNOFF_STATES)} 중 하나여야 합니다."
    if blocking not in BLOCKING_STATES:
        return f"(거부) blocking 은 {sorted(BLOCKING_STATES)} 중 하나여야 합니다."
    today = datetime.date.today().isoformat()
    side = {"backend-to-app": "backend", "app-to-backend": "app", "shared": "shared"}[direction]
    fm = {"type": "contract", "status": "stable", "scope": scope or "api-contract",
          "signoff": signoff, "blocking": blocking,
          "date": today, "direction": direction, "kind": kind, "title": title}
    path = _emit("project/contracts", f"{today}-{side}-{kind}-{_slugify(title)}.md", fm, body)
    return (f"기록됨: {path} — LIVE 계약(signoff={signoff}·{blocking})이라 dw_search/dw_list 로 즉시 조회됩니다"
            "(비준 불요).")


@mcp.tool()
def dw_write_spec(scope: str, title: str, body: str, kind: str = "spec") -> str:
    """기능 구현 계획·스펙·설계를 vault specs/ 에 기록한다(status:stable — LIVE 라 즉시 사용 가능).

    스펙·계획은 vault SSOT 에 둔다 — repo/worktree 에 두면 worktree 청소 시 휘발된다.
    kind=plan|spec|design. spec 은 비컴파일 LIVE 라 사람 비준 불요. repo 코드 경로는 본문에 링크로 남긴다.
    **구현/적용 완료하면 `dw_resolve(name)` 로 specs/archive/ 이동**(status 는 비준상태라 적용완료 표시가
    아니다 — 적용 여부는 archive 이동으로 구분한다).
    """
    if kind not in SPEC_KINDS:
        return f"(거부) kind 는 {sorted(SPEC_KINDS)} 중 하나여야 합니다."
    today = datetime.date.today().isoformat()
    fm = {"type": "spec", "status": "stable", "scope": scope or "general",
          "date": today, "kind": kind, "title": title}
    path = _emit("project/specs", f"{today}-{_slugify(title)}.md", fm, body)
    return f"기록됨: {path} — vault SSOT 에 보존(worktree 휘발 방지). LIVE 라 dw_search 로 즉시 검색."


@mcp.tool()
def dw_write_procedure(scope: str, title: str, steps: str) -> str:
    """재사용 가능한 절차(playbook/how-to)를 vault procedures/ 에 기록한다(항상 status:draft).

    비자명한 작업을 풀어낸 뒤 "다음에 또 이걸 어떻게 하지"를 절차로 남긴다(Hermes 식 자동 스킬 생성을
    Denver 거버넌스로 감싼 것). draft 로 제안하면 dw-ratifier 가 검증 후 자동 stable·컴파일한다.
    rule(강제)이 아니라 reusable how-to 다 — enforced-by 없음. steps 는 번호 단계로.
    """
    today = datetime.date.today().isoformat()
    scope, note = _canonical_scope(scope)
    fm = {"type": "procedure", "status": "draft", "scope": scope,
          "compiles-to": "skill", "date": today, "title": title}
    path = _emit("governance/procedures", f"{_slugify(title)}.md", fm, steps)
    return (f"제안됨(draft): {path} {note}— draft 라 아직 컴파일 안 됨. "
            "dw-ratifier 가 검증 통과 시 자동 stable·`make install` 합니다(사람 불요).")


def _clean_patterns(v: list[str] | None) -> list[str]:
    """빈/공백-only 항목 제거. 빈 정규식은 glob 내 **모든 파일**을 위반으로 만든다(재앙)."""
    return [str(x) for x in (v or []) if str(x).strip()]


@mcp.tool()
def dw_propose_rule(scope: str, title: str, rule: str, enforced_by: str,
                    check_deny: list[str] | None = None,
                    check_require: list[str] | None = None,
                    check_glob: list[str] | None = None,
                    check_exclude: list[str] | None = None,
                    check_hint: str = "") -> str:
    """규칙 변경을 vault rules/ 에 제안한다(항상 status:draft — 절대 stable 아님).
    draft 규칙은 컴파일되지 않아 강제되지 않는다. dw-ratifier 가 검증(스키마·enforced-by 실재·충돌 없음·
    check 패턴을 실제 코드에 돌려 오탐 0)을 통과시키면 자동 stable·컴파일한다 — 탈락 시 draft 유지·사유 주석.
    enforced_by 는 실재 검증자(security-qa|code-review|design-review|perf-tester)여야 한다.

    **결정론 검사(check_*)** — 주면 `.claude/dw-checks.json` 항목으로 컴파일돼 dw-lint 훅이
    편집된 파일마다 자동 검사한다(사람·LLM 판단 없이 발화). 안 주면 검사 없는 서술 규칙이다.
      check_deny    : 파일에 **있으면** 위반. 파이썬 정규식 **원문**(이스케이프 가공 없음).
      check_require : 파일에 **없으면** 위반. 동일하게 정규식 원문.
      check_glob    : 검사 대상 파일(fnmatch). deny/require 를 주면 **필수** — 없으면 컴파일러가
                      검사를 비활성해 "규칙은 있는데 검사는 없는" 상태가 되므로 여기서 거부한다.
      check_exclude : 예외 파일(fnmatch).
      check_hint    : 위반 메시지에 붙는 한 줄 교정 지침.
    glob/exclude 는 **프로젝트 상대 posix 경로와 basename 양쪽**에 매칭된다
    (`'*.pbxproj'` 가 `ios/Runner.xcodeproj/project.pbxproj` 에 맞는다).
    검사는 규칙이 **stable 로 비준된 뒤에만** 생성된다(draft 동안 강제 없음)."""
    deny = _clean_patterns(check_deny)
    require = _clean_patterns(check_require)
    glob = _clean_patterns(check_glob)
    exclude = _clean_patterns(check_exclude)
    hint = (check_hint or "").strip()

    # 깨진 정규식은 dw-lint 의 re.finditer 에서 **모든 프로젝트·모든 파일**마다 터진다 — 입구에서 막는다.
    for pat in deny + require:
        try:
            re.compile(pat)
        except re.error as e:
            return (f"(거부) 정규식이 컴파일되지 않습니다: {pat!r} — {e}. "
                    "check_deny/check_require 는 파이썬 정규식 원문입니다.")
    # deny/require 가 있는데 glob 이 없으면 컴파일러가 warn 후 검사를 비활성한다(collect_checks)
    # → 규칙만 남고 강제는 0 인 '살아 있는 척하는 가드'. 그 상태를 만들지 않는다.
    if (deny or require) and not glob:
        return ("(거부) check_deny/check_require 를 주려면 check_glob 도 필요합니다 "
                "(대상 파일 미지정 = 컴파일 시 검사 비활성 → 규칙만 있고 검사는 없는 상태). "
                "예: check_glob=['*.dart'] 또는 ['*.php']")
    # glob/exclude/hint 만 주는 것도 막는다 — deny/require 가 없으면 collect_checks 가 항목을
    # 아예 만들지 않아(경고조차 없이) '검사처럼 생긴 죽은 키' 가 프론트매터에 남는다.
    if not (deny or require) and (glob or exclude or hint):
        return ("(거부) check_glob/check_exclude/check_hint 는 check_deny 또는 check_require 와 "
                "함께여야 의미가 있습니다 — 패턴이 없으면 검사 항목이 생성되지 않고 "
                "'검사처럼 생긴 죽은 키' 만 남습니다. 강제할 패턴을 주시거나, "
                "검사 없는 서술 규칙이면 check_* 를 모두 비우세요(교정 지침은 rule 본문에).")

    scope, note = _canonical_scope(scope)
    fm = {"type": "rule", "status": "draft", "scope": scope, "enforced-by": enforced_by,
          "compiles-to": "skill", "title": title}
    # ⚠️ check-* 는 **맨 뒤에** 붙인다 — 미제공 시 종전과 바이트 동일한 산출물을 보장한다
    # (_emit 의 yaml.safe_dump(sort_keys=False) 는 삽입 순서를 그대로 쓴다).
    for key, val in (("check-deny", deny), ("check-require", require),
                     ("check-glob", glob), ("check-exclude", exclude)):
        if val:
            fm[key] = val
    if hint:
        fm["check-hint"] = hint

    path = _emit("governance/rules", f"{_slugify(title)}.md", fm, rule)

    # 비준기와 **동일한 검증**(dw_verify 단일 정본)을 지금 돌려 결과를 알려준다 — 제안자가
    # 며칠 뒤에야 hold 를 발견하는 대신 이 턴에서 고칠 수 있게. status 는 draft 그대로다
    # (승격은 제안한 에이전트의 턴 **밖** = 세션 시작 훅·`make ratify` 의 몫).
    try:
        verdict = dw_verify.verify_rule_checks(VAULT, deny=deny, require=require,
                                               glob=glob, exclude=exclude)
        predict = f" 검증 예측: {verdict.prediction}"
    except Exception as e:  # 예측 실패가 제안을 막지 않는다(다만 조용히 넘기지 않는다)
        predict = (f" (검증 예측 실패: {type(e).__name__}: {e} — 승격 시 비준기가 다시 검증합니다.)")

    return (f"제안됨(draft): {path} {note}— draft 라 아직 강제되지 않습니다.{predict} "
            "다음 세션 시작 시 비준기가 같은 검증을 다시 돌려 통과분만 자동 stable·설치합니다"
            "(사람 불요).")


if __name__ == "__main__":
    sys.stderr.write(f"[dw-vault mcp] vault={VAULT}\n")
    mcp.run()
