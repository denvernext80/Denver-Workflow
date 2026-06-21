#!/usr/bin/env python3
"""SSOT 컴파일러 — Obsidian vault → .claude/skills

사람은 vault에서 규칙을 저작하고, 에이전트는 이 컴파일러가 만든 정적
산출물(.claude/skills)에 복종한다. 둘을 잇는 유일한 계약면은 frontmatter다.

불변식 (BOOTSTRAP.md 참조):
  - 폴더는 사람용, frontmatter는 기계용 라우팅. 폴더로 분기하지 않는다.
  - 컴파일은 순수·결정론적. 같은 vault → 같은 산출물(정렬 출력).
  - type:rule + status:stable 은 반드시 enforced-by 를 가진다.
  - ADR(type:decision)은 절대 컴파일되지 않는다.
  - scope = skill 묶음 단위. status:stable 만 통과.

CLI:
  python _build/ssot-compile.py --vault . --out .claude/skills [--dry-run] [--strict]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml  # 유일한 외부 의존성
except ModuleNotFoundError:  # pragma: no cover - Makefile 의 .venv 가 보장
    sys.stderr.write(
        "ERROR: pyyaml 가 필요합니다. `make build` / `make dry-run` 을 쓰면\n"
        "       Makefile 이 .venv 에 자동 설치합니다. 수동 실행 시:\n"
        "       python3 -m venv .venv && .venv/bin/pip install pyyaml\n"
    )
    raise

MANIFEST_NAME = ".ssot-manifest.json"
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)

# scope 어휘 정규화 — 에이전트가 freeform/skill-이름을 scope 로 쓴 것을 canonical skill scope 로 매핑.
# (거버넌스: vault 의 정본 scope 는 _skills/ 매니페스트의 scope 들. 그 외는 별칭으로 흡수.)
SCOPE_ALIASES = {
    "backend": "backend-php", "admin": "backend-php", "web": "backend-php",
    "dev-engineering-charter": "engineering", "workspace": "engineering",
    "workflow": "engineering", "general": "engineering", "infra": "engineering",
    "orchestration": "engineering",
    "balipick-design": "design-system",
    "balipick-mobile": "mobile-flutter", "balipick-app": "mobile-flutter",
    "balipick-ios-release": "mobile-flutter", "ios": "mobile-flutter",
    "balipick-api-contract": "api-contract", "chat": "api-contract",
}


def canonical_scope(scope: str) -> str:
    return SCOPE_ALIASES.get((scope or "").strip(), (scope or "").strip())

# 컴파일러 자신이 만드는/관리하는 경로는 스캔에서 제외한다(산출물을 소스로 오인 금지).
#   .obsidian   : Obsidian 앱 설정(.json) — 라우팅 대상 아님
#   _templates  : 저작용 템플릿. {{placeholder}} frontmatter 라 컴파일하면 안 됨
#   .claude     : 빌드 산출물(SKILL.md). out 을 다른 폴더로 돌려도 소스로 오인 금지
SKIP_DIRS = {".git", ".venv", "node_modules", ".bkit", "__pycache__",
             ".obsidian", "_templates", ".claude",
             "commands", "hooks", ".claude-plugin", "skills"}  # 플러그인 저작물·번들 스킬 — 라우팅 대상 아님


# ---------------------------------------------------------------------------
# 자료구조
# ---------------------------------------------------------------------------
@dataclass
class Note:
    path: Path          # vault 상대경로
    meta: dict
    body: str

    @property
    def type(self) -> str:
        return str(self.meta.get("type", "")).strip()

    @property
    def scope(self) -> str | None:
        v = self.meta.get("scope")
        return str(v).strip() if v is not None else None

    @property
    def status(self) -> str:
        return str(self.meta.get("status", "")).strip()


@dataclass
class Diagnostics:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def emit(self) -> None:
        for w in self.warnings:
            sys.stderr.write(f"  warning: {w}\n")
        for e in self.errors:
            sys.stderr.write(f"  error:   {e}\n")


# ---------------------------------------------------------------------------
# 1. Scan
# ---------------------------------------------------------------------------
def scan(vault: Path, out: Path) -> list[Path]:
    """vault 전체 *.md 수집(정렬). 산출물 디렉토리와 SKIP_DIRS 는 제외."""
    out_abs = out.resolve()
    found: list[Path] = []
    for p in vault.rglob("*.md"):
        # SKIP_DIRS 는 vault 내부 경로에만 적용한다. 절대경로 전체(p.parts)로 검사하면
        # vault 자체가 '~/.claude/...' 아래 있을 때 '.claude' 가 매칭돼 모든 노트가 제외된다.
        if any(part in SKIP_DIRS for part in p.relative_to(vault).parts):
            continue
        # 산출물(.claude/skills) 안의 SKILL.md 를 소스로 다시 읽지 않는다.
        try:
            p.resolve().relative_to(out_abs)
            continue
        except ValueError:
            pass
        found.append(p)
    return sorted(found, key=lambda x: str(x).lower())


# ---------------------------------------------------------------------------
# 2. Parse
# ---------------------------------------------------------------------------
def parse(path: Path, vault: Path, diag: Diagnostics) -> Note | None:
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(vault)
    m = FRONTMATTER_RE.match(text)
    if not m:
        # frontmatter 없는 순수 문서(README 등)는 라우팅 대상이 아니므로 조용히 무시.
        return None
    raw_fm, body = m.group(1), m.group(2)
    try:
        meta = yaml.safe_load(raw_fm) or {}
    except yaml.YAMLError as exc:  # noqa: BLE001
        diag.error(f"{rel}: frontmatter YAML 파싱 실패 ({exc})")
        return None
    if not isinstance(meta, dict):
        diag.error(f"{rel}: frontmatter 가 매핑이 아님")
        return None
    return Note(path=rel, meta=meta, body=body.strip())


# ---------------------------------------------------------------------------
# 5. Transform — Obsidian 문법 정제
# ---------------------------------------------------------------------------
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
EMBED_RE = re.compile(r"!\[\[([^\]]+)\]\]")
DATAVIEW_RE = re.compile(r"```dataview\b.*?```", re.DOTALL)


def transform(body: str, rel: Path, diag: Diagnostics) -> str:
    """위키링크 평탄화, embed 평탄화(경고), dataview 블록 제거(경고)."""
    if DATAVIEW_RE.search(body):
        diag.warn(f"{rel}: dataview 블록 제거됨(에이전트엔 무의미)")
        body = DATAVIEW_RE.sub("", body)

    def embed_sub(m: re.Match) -> str:
        diag.warn(f"{rel}: embed ![[{m.group(1)}]] 평탄화됨")
        target = m.group(1).split("|")[-1].split("#")[0]
        return target.strip()

    body = EMBED_RE.sub(embed_sub, body)

    def link_sub(m: re.Match) -> str:
        inner = m.group(1)
        # [[target|alias]] → alias, [[target#heading]] → target
        text = inner.split("|")[-1] if "|" in inner else inner.split("#")[0]
        return text.strip()

    body = WIKILINK_RE.sub(link_sub, body)
    return body.strip()


# ---------------------------------------------------------------------------
# 3. Validate (불변식 구현)
# ---------------------------------------------------------------------------
def collect_agent_ids(notes: list[Note]) -> set[str]:
    ids: set[str] = set()
    for n in notes:
        if n.type == "agent":
            ids.add(str(n.meta.get("id", n.path.stem)).strip())
    return ids


def validate(notes: list[Note], diag: Diagnostics) -> None:
    agent_ids = collect_agent_ids(notes)

    # scope -> skill-manifest 노트들
    manifests: dict[str, list[Note]] = {}
    for n in notes:
        if n.type == "skill-manifest":
            sc = n.scope
            if not sc:
                diag.error(f"{n.path}: skill-manifest 에 scope 없음")
                continue
            if not n.meta.get("skill-name") or not n.meta.get("skill-description"):
                diag.error(f"{n.path}: skill-manifest 에 skill-name/skill-description 필수")
            manifests.setdefault(sc, []).append(n)

    for sc, ms in manifests.items():
        if len(ms) > 1:
            paths = ", ".join(str(m.path) for m in ms)
            diag.error(f"scope '{sc}' 의 skill-manifest 중복: {paths}")

    # 컴파일 대상 노트 검증
    compile_scopes: set[str] = set()
    for n in notes:
        if n.meta.get("compiles-to") == "skill":
            if not n.scope:
                diag.error(f"{n.path}: compiles-to:skill 인데 scope 없음")
            else:
                cs = canonical_scope(n.scope)
                compile_scopes.add(cs)
                if cs not in manifests and n.status == "stable":
                    # stable 만 fatal — 컴파일 대상이라 manifest 필수.
                    # draft 는 컴파일 안 되고 ratify 가 stable 승격 전 scope 를 검증하므로, junk-scope
                    # draft 는 조용히 skip(경고도 안 냄 — 자율 쓰기: 에이전트 자유 draft, 행동불가 노이즈 회피).
                    diag.error(f"{n.path}: scope '{n.scope}' 의 skill-manifest 가 없음(고아 노트)")

        # 불변식 3: rule 은 반드시 enforced-by. (status 무관하게 rule 이면 요구)
        if n.type == "rule":
            eb = n.meta.get("enforced-by")
            if not eb:
                diag.error(f"{n.path}: type:rule 인데 enforced-by 없음(검증 불가 규칙=소망)")
            elif str(eb).strip() not in agent_ids:
                # 존재하지 않는 에이전트 지목 = 경고(--strict 에서 에러로 승격)
                diag.warn(f"{n.path}: enforced-by '{eb}' 가 agents/ 에 없음")

    # skill-manifest 는 있는데 컴파일 대상 노트가 없는 scope = 경고
    for sc in manifests:
        emitted = any(
            n.meta.get("compiles-to") == "skill" and n.scope == sc and n.status == "stable"
            for n in notes
        )
        if not emitted:
            diag.warn(f"scope '{sc}': skill-manifest 는 있으나 컴파일될 stable 규칙이 없음")


# ---------------------------------------------------------------------------
# 4. Filter
# ---------------------------------------------------------------------------
def is_compilable_rule(n: Note) -> bool:
    return n.meta.get("compiles-to") == "skill" and n.status == "stable"


# ---------------------------------------------------------------------------
# 6. Emit
# ---------------------------------------------------------------------------
LIVE_TYPES = {"memory": "학습", "contract": "계약", "spec": "스펙"}
INDEX_CAP = 20    # scope 당 스킬 body 인덱스 최대 항목(스킬 body 는 자동로드 안 되므로 보수적)
DIGEST_CAP = 250  # SessionStart 다이제스트 — 학습(memory) 제목 전체 노출. 폭주 방지 backstop.
DIGEST_OTHER_CAP = 15  # 다이제스트의 계약·스펙은 최근 N 만(작업 시 특정 건 pull 이 자연스러움)


def _gist(body: str) -> str:
    """본문에서 한 줄 요지 추출(인덱스용)."""
    for line in body.splitlines():
        s = re.sub(r"[#>*`\-]", "", line).strip()
        if len(s) > 8:
            return s[:90]
    return ""


def build_knowledge_index(notes: list["Note"], scope: str, manifest_scopes: set[str]) -> list[str]:
    """이 scope 의 stable LIVE 지식(memory/contract/spec) 인덱스 — 제목+요지+ssot_read.
    pull-only 였던 LIVE 를 자동로드 스킬에 '카탈로그'로 노출(전문은 1-step ssot_read).
    engineering scope 스킬엔 canonical scope 가 어떤 매니페스트에도 안 맞는 orphan 도 흡수(무엇도 안 잃게)."""
    is_eng = scope == "engineering"
    picked: list["Note"] = []
    for n in notes:
        if n.type not in LIVE_TYPES:
            continue
        if "archive" in n.path.parts or n.path.name in ("README.md", "MEMORY.md"):
            continue
        cs = canonical_scope(n.scope)
        if cs == scope or (is_eng and cs not in manifest_scopes):
            picked.append(n)
    if not picked:
        return []
    picked.sort(key=lambda n: str(n.meta.get("date", "")), reverse=True)
    capped = picked[:INDEX_CAP]
    lines = ["", "## 이 scope 누적 학습 (LIVE — 전문은 `ssot_read(name)`)",
             "> 자동 생성 인덱스. 작업과 관련되면 해당 노트를 `ssot_read` 로 펼쳐 본다."]
    for n in capped:
        kind = LIVE_TYPES[n.type]
        title = str(n.meta.get("title", n.path.stem)).strip()
        g = _gist(n.body)
        lines.append(f"- [{kind}] **{title}** — {g}  ·  `ssot_read({n.path.stem})`")
    if len(picked) > INDEX_CAP:
        lines.append(f"- … 외 {len(picked) - INDEX_CAP}건 — `ssot_list` / `ssot_search` 로 더 찾기")
    return lines


def build_session_digest(notes: list["Note"], scopes: set[str]) -> str:
    """SessionStart 주입용 다이제스트. CC 스킬 body 는 자동 로드 안 되므로(progressive disclosure),
    '항상 적용할 규율 + 누적 지식 인덱스'를 세션 시작 시 컨텍스트에 직접 주입한다.
    scopes = 이 프로젝트가 받는 scope 집합. engineering 포함 시 orphan-scope LIVE 도 흡수."""
    manifest_scopes = {n.scope for n in notes if n.type == "skill-manifest" and n.scope}
    in_scope = lambda cs: cs in scopes or ("engineering" in scopes and cs not in manifest_scopes)

    guidance = sorted((n for n in notes if n.type == "guidance" and n.status == "stable"
                       and canonical_scope(n.scope) in scopes), key=lambda n: str(n.path))
    rules = sorted((n for n in notes if is_compilable_rule(n) and n.type == "rule"
                    and canonical_scope(n.scope) in scopes),
                   key=lambda n: str(n.path))
    live = [n for n in notes if n.type in LIVE_TYPES and "archive" not in n.path.parts
            and n.path.name not in ("README.md", "MEMORY.md") and in_scope(canonical_scope(n.scope))]
    live.sort(key=lambda n: str(n.meta.get("date", "")), reverse=True)

    # pin: top guidance — 최우선 전제(다른 모든 섹션보다 위). pin:top 은 digest:full 함의.
    pinned = [n for n in guidance if str(n.meta.get("pin", "")).strip() == "top"]
    guidance = [n for n in guidance if str(n.meta.get("pin", "")).strip() != "top"]

    # repo-map (프로젝트 토폴로지/라우팅) — axis-A 의 의도된 digest 예외(VAULT-STRUCTURE 문서화).
    repo_maps = sorted((n for n in notes if n.type == "repo-map" and n.status == "stable"
                        and in_scope(canonical_scope(n.scope))), key=lambda n: str(n.path))

    L: list[str] = [
        "# Denver AI Workflow — 세션 컨텍스트 (자동 주입, 이 프로젝트의 거버넌스 지식)",
        "> CC 스킬 body 는 자동 로드되지 않아 여기 직접 주입한다. 아래 **규율은 항상 적용**하고,",
        "> 누적 지식은 관련 작업 시 `ssot_read(name)` 로 전문을 펼친다(전체 규칙·계약은 스킬/MCP).",
    ]
    if pinned:
        L += ["", "## ⭐ 최우선 전제 — 모든 작업·모든 단계에 우선 적용"]
        for n in pinned:
            L += ["", f"### {str(n.meta.get('title', n.path.stem)).strip()}", n.body.strip(), ""]
    if repo_maps:
        L += ["", "## 레포 맵 (라우팅)"]
        for n in repo_maps:
            L += ["", n.body.strip(), ""]
    if guidance:
        L += ["", "## 항상 적용할 작업 규율 (guidance)"]
        for n in guidance:
            title = str(n.meta.get("title", n.path.stem)).strip()
            # digest: full → 전문 주입(매 세션 항상 컨텍스트). 기본 → 제목+한 줄.
            if str(n.meta.get("digest", "")).strip() == "full":
                L += ["", f"### {title}", n.body.strip(), ""]
            else:
                L.append(f"- **{title}** — {_gist(n.body)}")
    if rules:
        L += ["", "## 이 프로젝트의 강제 규칙 (위반 시 검사·검증자가 차단 — 전문은 스킬)"]
        for n in rules:
            eb = str(n.meta.get("enforced-by", "")).strip()
            L.append(f"- **{str(n.meta.get('title', n.path.stem)).strip()}**"
                     + (f"  ·  enforced-by: {eb}" if eb else ""))
    def row(n):
        return f"- [{LIVE_TYPES[n.type]}] {str(n.meta.get('title', n.path.stem)).strip()}  ·  `ssot_read({n.path.stem})`"
    mem = [n for n in live if n.type == "memory"]          # 학습 — 전체 항상 노출
    other = [n for n in live if n.type != "memory"]        # 계약·스펙 — 최근 N (date desc 정렬 유지)
    if mem:
        L += ["", f"## 누적 학습 (memory {len(mem)}건 — 제목 전체 항상 노출, 전문은 `ssot_read`)"]
        L += [row(n) for n in mem[:DIGEST_CAP]]
        if len(mem) > DIGEST_CAP:
            L.append(f"- … 외 {len(mem) - DIGEST_CAP}건 — `ssot_search`/`ssot_list`")
    if other:
        L += ["", f"## 계약·스펙 (최근 {min(len(other), DIGEST_OTHER_CAP)}건 — 작업 관련 건은 `ssot_read`/`ssot_search`)"]
        L += [row(n) for n in other[:DIGEST_OTHER_CAP]]
        if len(other) > DIGEST_OTHER_CAP:
            L.append(f"- … 계약·스펙 외 {len(other) - DIGEST_OTHER_CAP}건 — `ssot_search`/`ssot_list` 로 찾기")
    return "\n".join(L).rstrip() + "\n"


def emit(
    notes: list[Note], out: Path, diag: Diagnostics, dry_run: bool,
    only_scopes: set[str] | None = None,
) -> dict[str, str]:
    """scope 별로 묶어 SKILL.md 생성. 반환: {skill-name: scope} 매니페스트.

    only_scopes 가 주어지면 해당 scope 만 산출(프로젝트별 부분 설치용). 검증은 전체
    노트 대상으로 이미 끝났으므로 emit 만 거른다.
    """
    manifests = {n.scope: n for n in notes if n.type == "skill-manifest" and n.scope}

    emitted: dict[str, str] = {}
    for scope, manifest in sorted(manifests.items()):
        if only_scopes is not None and scope not in only_scopes:
            continue
        rules = sorted(
            (n for n in notes if is_compilable_rule(n) and n.scope == scope),
            key=lambda n: str(n.path).lower(),
        )
        if not rules:
            # 컴파일될 규칙이 없는 skill 은 디렉토리를 만들지 않는다(불변식 5/clean).
            continue

        skill_name = str(manifest.meta["skill-name"]).strip()
        description = str(manifest.meta["skill-description"]).strip()
        version = str(manifest.meta.get("version", "1.0.0")).strip()

        # agentskills.io 표준 호환 frontmatter(name/description/version/metadata) — 이식성.
        # CC 는 name/description 만 읽고 나머지는 무시(additive, 동작 불변).
        parts: list[str] = [
            "---",
            f"name: {skill_name}",
            f"description: {description}",
            f"version: {version}",
            "metadata:",
            "  source: denver-ssot",
            f"  scope: {scope}",
            "---",
            "<!-- 생성 파일 — 직접 편집 금지. vault 에서 컴파일됨. -->",
        ]
        manifest_body = transform(manifest.body, manifest.path, diag)
        if manifest_body:
            parts += ["", manifest_body]

        for r in rules:
            title = str(r.meta.get("title", r.path.stem)).strip()
            enforcer = str(r.meta.get("enforced-by", "")).strip()
            # rule 은 enforced-by 를 표기, guidance 등은 출처만(검증자 없음).
            src = f"> 출처: `{r.path}`" + (f" · enforced-by: `{enforcer}`" if enforcer else "")
            rule_body = transform(r.body, r.path, diag)
            parts += [
                "",
                f"## {title}",
                src,
                "",
                rule_body,
            ]

        # LIVE 지식 인덱스 — pull-only 였던 memory/contract/spec 을 자동로드 스킬에 카탈로그로 노출.
        parts += build_knowledge_index(notes, scope, set(manifests))

        content = "\n".join(parts).rstrip() + "\n"
        emitted[skill_name] = scope

        if not dry_run:
            skill_dir = out / skill_name
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    return emitted


# ---------------------------------------------------------------------------
# 7. Clean — 사라진 skill 디렉토리 제거 + 매니페스트 갱신
# ---------------------------------------------------------------------------
def clean(out: Path, emitted: dict[str, str], dry_run: bool) -> list[str]:
    manifest_path = out / MANIFEST_NAME
    previous: dict[str, str] = {}
    if manifest_path.exists():
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8")).get("skills", {})
        except (json.JSONDecodeError, OSError):
            previous = {}

    removed = sorted(set(previous) - set(emitted))
    if not dry_run:
        for name in removed:
            shutil.rmtree(out / name, ignore_errors=True)
        out.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps({"skills": dict(sorted(emitted.items()))}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
    return removed


# ---------------------------------------------------------------------------
# 검사(check) 수집 — 결정론적 린터용. 규칙 frontmatter 의 check-* 를 모은다.
# ---------------------------------------------------------------------------
def _as_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v]
    return [str(v)]


def collect_checks(
    notes: list[Note], diag: Diagnostics, only_scopes: set[str] | None = None
) -> list[dict]:
    """compilable rule 중 check-deny/check-require 를 가진 것을 린터 매니페스트로 변환.

    deny  : 파일에 있으면 위반(정규식)
    require: 파일에 없으면 위반(정규식)
    glob  : 적용 대상 파일(없으면 검사 비활성 — 전체 스캔 오탐 방지)
    """
    checks: list[dict] = []
    for n in notes:
        if not is_compilable_rule(n):
            continue
        if only_scopes is not None and n.scope not in only_scopes:
            continue
        deny = _as_list(n.meta.get("check-deny"))
        require = _as_list(n.meta.get("check-require"))
        if not deny and not require:
            continue
        glob = _as_list(n.meta.get("check-glob"))
        if not glob:
            diag.warn(f"{n.path}: check-deny/require 가 있으나 check-glob 없음 → 검사 비활성")
            continue
        checks.append({
            "rule": str(n.path),
            "title": str(n.meta.get("title", n.path.stem)).strip(),
            "scope": n.scope,
            "enforced_by": str(n.meta.get("enforced-by", "?")).strip(),
            "deny": deny,
            "require": require,
            "glob": glob,
            "exclude": _as_list(n.meta.get("check-exclude")),
            "hint": str(n.meta.get("check-hint", "")).strip(),
        })
    return sorted(checks, key=lambda c: c["rule"])


# ---------------------------------------------------------------------------
# 서브에이전트 emit — enforced-by 가 가리키는 agent 를 CC 서브에이전트로 설치.
# ---------------------------------------------------------------------------
AGENTS_MANIFEST = ".ssot-agents.json"


def emit_agents(
    notes: list[Note], agents_out: Path, diag: Diagnostics, dry_run: bool,
    only_scopes: set[str] | None = None,
) -> list[str]:
    """설치된 scope 의 규칙이 enforced-by 로 참조하는 agent 만 CC 서브에이전트로 emit.

    대상 .claude/agents/ 의 기존 외부 에이전트(예: backend-lead)는 건드리지 않는다 —
    이전에 우리가 쓴 것(.ssot-agents.json)만 stale 정리.
    """
    referenced: set[str] = set()
    for n in notes:
        if is_compilable_rule(n) and (only_scopes is None or n.scope in only_scopes):
            eb = str(n.meta.get("enforced-by", "")).strip()
            if eb:
                referenced.add(eb)

    by_id = {
        str(n.meta.get("id", n.path.stem)).strip(): n
        for n in notes if n.type == "agent"
    }
    # install: always 에이전트(거버넌스 하네스 등)는 enforced-by 참조와 무관하게 항상 설치.
    always = {aid for aid, n in by_id.items()
              if str(n.meta.get("install", "")).strip() == "always"}

    written: list[str] = []
    for aid in sorted(referenced | always):
        agent = by_id.get(aid)
        if agent is None:
            continue  # 존재하지 않는 검증자 → 이미 validate 에서 경고됨
        desc = str(agent.meta.get("description", agent.meta.get("title", aid))).strip()
        body = transform(agent.body, agent.path, diag)
        # 검증자(reviewer)에만 리뷰 지시 appendix 를 붙인다. 하네스(install:always)는 자체 프롬프트.
        appendix = (
            "\n\n이 프로젝트 `.claude/skills/` 에 설치된 SSOT 규칙을 기준으로 검토하라. "
            "위반을 발견하면 출처 규칙과 함께 구체적으로 보고한다.\n"
            if aid not in always else "\n"
        )
        # Emit description as a YAML block scalar so multi-line descriptions
        # (description: | blocks) produce valid YAML regardless of newlines.
        desc_block = "\n".join(
            ("  " + ln) if ln.strip() else ""
            for ln in desc.splitlines()
        )
        content = (
            f"---\nname: {aid}\ndescription: |\n{desc_block}\n---\n"
            "<!-- 생성: vault agents/ 에서 컴파일. 직접 편집 금지. -->\n\n"
            f"{body}{appendix}"
        )
        fname = f"{aid}.md"
        written.append(fname)
        if not dry_run:
            agents_out.mkdir(parents=True, exist_ok=True)
            (agents_out / fname).write_text(content, encoding="utf-8")

    # stale 정리(우리 매니페스트 기준)
    manifest_path = agents_out / AGENTS_MANIFEST
    previous: list[str] = []
    if manifest_path.exists():
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8")).get("agents", [])
        except (json.JSONDecodeError, OSError):
            previous = []
    if not dry_run:
        for stale in sorted(set(previous) - set(written)):
            (agents_out / stale).unlink(missing_ok=True)
        agents_out.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps({"agents": sorted(written)}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return written


# ---------------------------------------------------------------------------
# 드라이버
# ---------------------------------------------------------------------------
def run(vault: Path, out: Path, dry_run: bool, strict: bool,
        only_scopes: set[str] | None = None, checks_out: Path | None = None,
        agents_out: Path | None = None, digest_out: Path | None = None) -> int:
    diag = Diagnostics()

    md_paths = scan(vault, out)
    notes: list[Note] = []
    for p in md_paths:
        note = parse(p, vault, diag)
        if note is not None and note.type:
            notes.append(note)

    validate(notes, diag)

    # --scopes 로 존재하지 않는 scope 를 지정하면 사용자 실수 — 경고
    if only_scopes is not None:
        known = {n.scope for n in notes if n.scope}
        for sc in sorted(only_scopes - known):
            diag.warn(f"--scopes '{sc}': vault 에 존재하지 않는 scope")

    # --strict: 경고를 에러로 승격
    fatal = bool(diag.errors) or (strict and bool(diag.warnings))

    scope_note = f" scopes={','.join(sorted(only_scopes))}" if only_scopes else ""
    print(f"SSOT compile: vault={vault} out={out}{scope_note} "
          f"({'dry-run' if dry_run else 'build'}{', strict' if strict else ''})")
    print(f"  스캔 {len(md_paths)} md · 라우팅 노트 {len(notes)} "
          f"· 에러 {len(diag.errors)} · 경고 {len(diag.warnings)}")

    if fatal:
        diag.emit()
        print("실패: 검증 에러로 중단(산출물 미생성).")
        return 1

    emitted = emit(notes, out, diag, dry_run, only_scopes)
    removed = clean(out, emitted, dry_run)

    checks = collect_checks(notes, diag, only_scopes)
    if checks_out is not None and not dry_run:
        checks_out.parent.mkdir(parents=True, exist_ok=True)
        checks_out.write_text(
            json.dumps({"checks": checks}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    agents_written: list[str] = []
    if agents_out is not None:
        agents_written = emit_agents(notes, agents_out, diag, dry_run, only_scopes)

    if digest_out is not None and not dry_run:
        # union 빌드(only_scopes=None=오케스트레이터)도 다이제스트를 emit한다.
        # scope 미지정 시 vault 전체 정규 scope 를 대상으로(build_session_digest 의
        # `canonical_scope(n.scope) in scopes` 필터와 정합).
        digest_scopes = only_scopes or {canonical_scope(n.scope) for n in notes if n.scope}
        digest_out.parent.mkdir(parents=True, exist_ok=True)
        digest_out.write_text(build_session_digest(notes, digest_scopes), encoding="utf-8")

    diag.emit()
    print(f"  생성 skill {len(emitted)}: {', '.join(sorted(emitted)) or '(없음)'}")
    if removed:
        print(f"  제거된 stale skill: {', '.join(removed)}")
    if checks_out is not None:
        print(f"  결정론적 검사 {len(checks)}건"
              + (f" → {checks_out}" if not dry_run else " (dry-run, 미기록)"))
    if agents_out is not None:
        print(f"  서브에이전트 {len(agents_written)}: "
              + (", ".join(s[:-3] for s in agents_written) or "(없음)"))
    print("dry-run 완료(쓰기 없음)." if dry_run else "build 완료.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SSOT vault → .claude/skills 컴파일러")
    ap.add_argument("--vault", default=".", type=Path)
    ap.add_argument("--out", default=".claude/skills", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="파일 쓰지 않고 검증/요약만")
    ap.add_argument("--strict", action="store_true", help="경고도 에러로 취급(CI용)")
    ap.add_argument("--scopes", default="", help="쉼표구분 scope 만 산출(프로젝트별 부분 설치). 비우면 전체")
    ap.add_argument("--checks-out", default="", help="결정론적 린터용 검사 매니페스트(JSON) 출력 경로")
    ap.add_argument("--agents-out", default="", help="enforced-by 가 참조하는 agent 를 CC 서브에이전트로 설치할 디렉토리")
    ap.add_argument("--digest-out", default="", help="SessionStart 주입용 다이제스트(md) 출력 경로(스코프별 프로젝트 설치)")
    args = ap.parse_args(argv)
    only = {s.strip() for s in args.scopes.split(",") if s.strip()} or None
    checks_out = Path(args.checks_out) if args.checks_out else None
    agents_out = Path(args.agents_out) if args.agents_out else None
    digest_out = Path(args.digest_out) if args.digest_out else None
    return run(args.vault.resolve(), (args.vault / args.out).resolve()
               if not args.out.is_absolute() else args.out,
               args.dry_run, args.strict, only, checks_out, agents_out, digest_out)


if __name__ == "__main__":
    raise SystemExit(main())
