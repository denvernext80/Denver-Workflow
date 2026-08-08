#!/usr/bin/env python3
"""check 패턴 검증 — **비준기와 제안 시점이 공유하는 단일 정본**.

두 곳이 같은 판정을 내려야 한다:
  - `dw-ratify.py`      : 승격 여부(hold 사유)를 결정한다.
  - `dw_propose_rule`   : 제안 즉시 "이대로면 승격되나?" 를 **예측해 알려준다**.
구현이 갈라지면 예측과 실제가 어긋나 — 예측이 없는 것보다 나쁘다. 그래서 한 곳에 둔다.

핵심 계약(2026-08-07 실측으로 확립): "위반 0" 은 ⓐ대상이 있고 깨끗 ⓑ**대상이 아예 없음**
(검증 불가) 두 가지를 뜻한다. 그래서 이 모듈은 항상 **검사대상 수(candidates)** 를 함께
돌려준다 — vault stable 규칙 「검증 장치는 비교 대상이 비어있지 않음을 먼저 증명하라 —
0건을 성공으로 보고하는 게이트 금지」의 구현이다.

표준 라이브러리만 사용(pyyaml 불요).
"""
from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path

import dw_state

# 스캔 시 건너뛸 디렉터리 — os.walk 의 dirnames 를 **프루닝**한다(하위로 내려가지 않는다).
#
# ⚠️ `ios`·`android` 는 여기 **없다**. 그것들이 있던 탓에 `ios/**/project.pbxproj` 를 노리는
#   규칙은 검사대상이 0 건이었다(2026-08-07 실측). 대신 그 아래 **무거운 산출물 디렉터리만**
#   좁혀 막는다 — ios/ 는 878 → 102 파일로 줄고 Runner.xcodeproj 는 스캔된다.
SKIP = {
    # VCS·의존성·에디터
    ".git", ".venv", "node_modules", "vendor", "__pycache__", ".claude", ".obsidian",
    # 빌드 산출물(공통)
    "build", "dist", "_build", ".dart_tool", ".bkit",
    # 빌드 산출물·벤더 트리(모바일·러스트·웹) — ios·android 를 열면서 대신 좁혀 막는 대상.
    # Pods 엔 벤더된 project.pbxproj 사본이 3개 있어(실측) 열어두면 그대로 오탐이 된다.
    "Pods", "DerivedData", ".symlinks", "ephemeral", ".gradle", "Carthage",
    "target", ".next", "coverage",
    # git worktree 디렉터리 — 같은 코드의 사본이라 검사대상을 부풀리고 중복 보고를 낳는다.
    ".worktrees", "_worktrees",
}
MAX_BYTES = 2_000_000

# 판정 상태
NO_CHECKS = "no-checks"          # check 패턴 없음 — 검증 대상 아님(서술 규칙·guidance·procedure)
NO_GLOB = "no-glob"              # 패턴은 있는데 대상 파일 미지정 → 컴파일 시 검사 비활성
NO_PROJECTS = "no-projects"      # 스캔할 레포가 등록되지 않음 → 오탐 0 을 주장할 근거 없음
NO_CANDIDATES = "no-candidates"  # glob 이 아무 파일도 매치하지 않음 → '위반 0' 이 공허함
VIOLATIONS = "violations"        # 기존 코드에 매치 → 진짜위반/오탐 판단 필요
CLEAN = "clean"                  # 검사대상 ≥1 · 위반 0 → 승격 가능


def as_list(v) -> list[str]:
    if not v:
        return []
    return [str(x) for x in v] if isinstance(v, list) else [str(v)]


def matches_glob(rel: str, patterns: list[str]) -> bool:
    """프로젝트 상대 posix 경로와 basename **양쪽**에 fnmatch(dw-lint 와 동일 규칙)."""
    base = rel.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(base, p) for p in patterns)


def scan_codebase(projects, glob: list[str], exclude: list[str],
                  deny: list[str], require: list[str]) -> tuple[list[str], int]:
    """패턴을 기존 코드에 돌린다. 반환 `(위반목록, 검사대상 파일수)`.

    walk 는 `dirnames` 프루닝으로 SKIP 트리에 내려가지 않는다(4레포 9.9s → 0.15s 실측).
    symlink 는 따라가지 않는다(os.walk 기본값).
    """
    hits: list[str] = []
    candidates = 0
    deny_res = [re.compile(p) for p in deny]
    req_res = [re.compile(p) for p in require]
    for proj in projects:
        proj = Path(proj)
        if not proj.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(proj):
            dirnames[:] = [d for d in dirnames if d not in SKIP]
            for name in filenames:
                p = Path(dirpath) / name
                try:
                    rel = p.relative_to(proj).as_posix()
                except ValueError:
                    continue
                if glob and not matches_glob(rel, glob):
                    continue
                if exclude and matches_glob(rel, exclude):
                    continue
                candidates += 1
                try:
                    if p.stat().st_size > MAX_BYTES:
                        continue
                    text = p.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                for rx in deny_res:
                    if rx.search(text):
                        hits.append(f"{proj.name}/{rel}: 금지패턴 /{rx.pattern}/ 매치")
                        break
                for rx in req_res:
                    if not rx.search(text):
                        hits.append(f"{proj.name}/{rel}: 필수패턴 /{rx.pattern}/ 누락")
                        break
                if len(hits) >= 20:
                    return hits, candidates
    return hits, candidates


class Verdict:
    """검증 결과. `state` 로 분기하고, 사람용 문구는 `reason`/`prediction` 을 쓴다."""

    def __init__(self, state: str, reason: str, prediction: str,
                 hits: list[str] | None = None, candidates: int = 0, projects: int = 0):
        self.state = state
        self.reason = reason            # 비준기 hold 사유(왜 승격 못 하는가)
        self.prediction = prediction    # 제안자용 예측(이대로면 어떻게 되는가)
        self.hits = hits or []
        self.candidates = candidates
        self.projects = projects

    @property
    def promotable(self) -> bool:
        return self.state in (NO_CHECKS, CLEAN)


def verify_rule_checks(vault, deny: list[str], require: list[str], glob: list[str],
                       exclude: list[str], projects=None) -> Verdict:
    """규칙의 check 패턴을 등록 레포에 돌려 승격 가능성을 판정한다.

    `projects` 를 주지 않으면 레지스트리(`<vault>/.dw-state/projects.json`)를 쓴다.
    """
    deny, require = as_list(deny), as_list(require)
    glob, exclude = as_list(glob), as_list(exclude)
    if not (deny or require):
        return Verdict(NO_CHECKS, "", "검사 없는 서술 규칙 — 결정론 검사는 생성되지 않는다"
                                     "(자동 강제하려면 check_deny/check_glob 을 주세요).")
    if not glob:
        return Verdict(NO_GLOB,
                       "check 패턴은 있으나 check-glob 없음(검사 비활성 — 무의미)",
                       "check_glob 이 없어 검사가 비활성된다 — 규칙만 남고 강제는 0 이 된다.")
    if projects is None:
        projects = dw_state.registered_projects(vault)
    projects = list(projects)
    if not projects:
        return Verdict(NO_PROJECTS,
                       "스캔 대상 프로젝트 0 — 오탐 0 을 검증할 코드가 없다. "
                       "`make install-project P=/절대경로` 로 레포를 등록하라.",
                       "⚠️ 등록된 레포가 0개라 검증할 수 없다 → 이대로면 hold 된다. "
                       "`make install-project P=/절대경로` 로 레포를 등록하라.",
                       projects=0)
    hits, cand = scan_codebase(projects, glob, exclude, deny, require)
    if hits:
        shown = "; ".join(hits[:3])
        return Verdict(VIOLATIONS,
                       f"기존 코드에 {len(hits)}건 매치(검사대상 {cand}건) — "
                       f"진짜위반/오탐 판단 필요. 예: {hits[0]}",
                       f"⚠️ 오탐/위반 {len(hits)}건 발견(검사대상 {cand}건) → 이대로면 **hold** 된다. "
                       f"패턴을 좁히거나 check_exclude 를 주거나, 진짜 위반이면 코드를 먼저 고쳐라. "
                       f"예: {shown}",
                       hits=hits, candidates=cand, projects=len(projects))
    if cand == 0:
        return Verdict(NO_CANDIDATES,
                       f"검사대상 파일 0건 — check-glob {glob} 이 등록 레포 {len(projects)}개에서 "
                       f"아무 파일도 매치하지 않는다. 위반 0 은 공허하다(검증 불가). "
                       f"glob 오타/경로 착오인지 확인하고, 대상이 아직 없는 선제 규칙이면 사람이 승인하라.",
                       f"⚠️ check_glob {glob} 이 등록 레포 {len(projects)}개에서 **아무 파일도 매치하지 "
                       f"않는다** → 위반 0 이 공허하므로 이대로면 hold 된다. glob 오타를 확인하라.",
                       candidates=0, projects=len(projects))
    return Verdict(CLEAN, "",
                   f"검증 통과 예측 — 검사대상 {cand}건 · 위반 0 (등록 레포 {len(projects)}개). "
                   f"다음 세션 시작 시 자동 승격되어 강제된다.",
                   candidates=cand, projects=len(projects))
