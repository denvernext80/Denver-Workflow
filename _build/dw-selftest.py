#!/usr/bin/env python3
"""엔진 자기검사(self-test) — 표준 라이브러리 unittest 만 사용(pytest 미도입).

레포에 기존 테스트 하네스가 없었다(2026-08-07 실측: pytest/pyproject/conftest 부재,
venv 의존성은 pyyaml+mcp 뿐). 그래서 venv 에 새 의존성을 추가하지 않는 stdlib unittest 로
최소 하네스를 만들고 `make test` 로 노출한다.

픽스처는 **`_seed`(제네릭 vault) 복사본**을 쓴다 — `make seed-check` 가 이미 seed 의 strict
컴파일 가능성을 보증하므로 "컴파일되는 vault" 를 새로 발명할 필요가 없다. 사용자 실제 vault
($DW_VAULT_DIR)는 절대 건드리지 않는다(읽기조차 하지 않는다).

usage: <venv>/bin/python _build/dw-selftest.py   (또는 make test)
"""
from __future__ import annotations

import argparse
import importlib.util
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import unittest.mock
from pathlib import Path

import dw_runtime          # 하이픈 없는 모듈 — sys.path[0]=_build 이라 그대로 임포트된다

BUILD = Path(__file__).resolve().parent
ROOT = BUILD.parent
SERVER = BUILD / "dw-mcp-server.py"
LAUNCHER = BUILD / "dw-mcp-launch.py"
COMPILER = BUILD / "dw-compile.py"
LINTER = BUILD / "dw-lint.py"
RATIFIER = BUILD / "dw-ratify.py"
WIRE_HOOK = BUILD / "wire-hook.py"
SEED = ROOT / "_seed"

_counter = itertools.count()


def load_server(vault: Path):
    """dw-mcp-server.py 를 주어진 vault 로 임포트한다.

    VAULT 는 모듈 최상단에서 `--vault` argparse 로 확정되므로(env/cwd 의존 금지 설계),
    sys.argv 를 갈아끼운 뒤 매번 새 모듈 객체로 로드해 테스트 간 vault 를 격리한다.
    `@mcp.tool()` 데코레이터는 원본 함수를 그대로 반환하므로 도구를 직접 호출할 수 있다.
    """
    name = f"dw_mcp_server_selftest_{next(_counter)}"
    spec = importlib.util.spec_from_file_location(name, SERVER)
    mod = importlib.util.module_from_spec(spec)
    saved = sys.argv
    sys.argv = ["dw-mcp-server.py", "--vault", str(vault)]
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = saved
    return mod


def frontmatter(text: str) -> dict:
    import yaml
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    assert m, "프론트매터 없음"
    return yaml.safe_load(m.group(1)) or {}


class ProposeRuleChecksTest(unittest.TestCase):
    """dw_propose_rule 의 check-* 왕복(제안 → 프론트매터 → 컴파일 → dw-checks.json → 린터)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dw-selftest-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.vault = self.tmp / "vault"
        shutil.copytree(SEED, self.vault)
        self.srv = load_server(self.vault)
        self.rules_dir = self.vault / "governance" / "rules"

    # --- helpers ----------------------------------------------------------
    def propose(self, title: str, **kw) -> str:
        """제안 후 **vault 상대경로**를 돌려준다.

        경로를 반환 메시지 파싱으로 얻지 않는다 — 메시지 문구가 바뀌면 6곳이 조용히 깨진다.
        슬러그 규칙(_slugify)으로 유도하고, 메시지가 그 경로를 담는지는 별도로 단정한다.
        """
        msg = self.srv.dw_propose_rule(
            scope=kw.pop("scope", "engineering"), title=title,
            rule=kw.pop("rule", "본문."),
            enforced_by=kw.pop("enforced_by", "code-review"), **kw)
        rel = f"governance/rules/{self.srv._slugify(title)}.md"
        self.assertIn(rel, msg, f"성공 메시지가 경로를 담지 않았다: {msg!r}")
        return rel

    def reject(self, title: str, **kw) -> str:
        """거부를 기대하는 제안. 거부 메시지를 돌려주고 **파일이 생기지 않았음**을 단정한다."""
        before = sorted(p.name for p in self.rules_dir.glob("*.md"))
        msg = self.srv.dw_propose_rule(
            scope=kw.pop("scope", "engineering"), title=title,
            rule=kw.pop("rule", "본문."),
            enforced_by=kw.pop("enforced_by", "code-review"), **kw)
        self.assertTrue(msg.startswith("(거부)"), f"거부되지 않았다: {msg!r}")
        self.assertEqual(before, sorted(p.name for p in self.rules_dir.glob("*.md")),
                         "거부인데 vault 에 파일이 생겼다")
        return msg

    def note(self, rel: str) -> str:
        return (self.vault / rel).read_text(encoding="utf-8")

    def promote_to_stable(self, rel: str) -> None:
        """draft → stable. **비준(dw-ratify)을 대신하는 테스트용 조작**이다 —
        dw_propose_rule 은 stable 을 만들 수 없어야 하고(항상 draft), 컴파일러의
        is_compilable_rule 은 status:stable 만 검사로 수집하므로 왕복 검증에 필요하다.
        (이 조작은 테스트 안에서만 일어난다 — 도구엔 status 파라미터가 없다.)"""
        p = self.vault / rel
        t = p.read_text(encoding="utf-8")
        end = re.match(r"^---\n(.*?)\n---", t, re.DOTALL).end()
        p.write_text(
            re.sub(r"^status:\s*draft\s*$", "status: stable", t[:end],
                   count=1, flags=re.MULTILINE) + t[end:],
            encoding="utf-8",
        )

    def compile_checks(self) -> list[dict]:
        out = self.tmp / "checks.json"
        r = subprocess.run(
            [sys.executable, str(COMPILER), "--vault", str(self.vault),
             "--out", str(self.tmp / "skills"), "--checks-out", str(out), "--strict"],
            capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0, f"컴파일 실패:\n{r.stdout}\n{r.stderr}")
        return json.loads(out.read_text(encoding="utf-8"))["checks"]

    def entry(self, checks: list[dict], rel: str) -> list[dict]:
        return [c for c in checks if c["rule"] == rel]

    # --- 하위호환: 파라미터 미제공 ---------------------------------------
    def test_no_check_params_emits_byte_identical_note(self):
        """check_* 를 안 주면 종전과 **바이트 동일한** 산출물이어야 한다.

        새 키는 fm 딕셔너리 **끝에** 조건부로 붙어야 한다(safe_dump(sort_keys=False) 는
        삽입 순서를 보존하므로, 중간에 끼우면 이 골든이 깨진다)."""
        rel = self.propose("검사없는 규칙", rule="본문 한 줄.")
        self.assertEqual(self.note(rel), (
            "---\n"
            "type: rule\n"
            "status: draft\n"
            "scope: engineering\n"
            "enforced-by: code-review\n"
            "compiles-to: skill\n"
            "title: 검사없는 규칙\n"
            "---\n"
            "\n"
            "본문 한 줄.\n"
        ))
        self.assertNotIn("check-", self.note(rel))

    def test_no_check_params_yields_no_check_entry(self):
        rel = self.propose("검사없는 규칙2")
        self.promote_to_stable(rel)
        self.assertEqual(self.entry(self.compile_checks(), rel), [])

    # --- 프론트매터 기록 --------------------------------------------------
    def test_check_params_recorded_in_frontmatter(self):
        rel = self.propose(
            "pbxproj 에 절대경로 금지",
            check_deny=[r"/Users/[a-z]+/"],
            check_glob=["*.pbxproj"],
            check_exclude=["Pods/*"],
            check_hint="상대경로/변수로 바꿔라",
        )
        fm = frontmatter(self.note(rel))
        self.assertEqual(fm["check-deny"], [r"/Users/[a-z]+/"])
        self.assertEqual(fm["check-glob"], ["*.pbxproj"])
        self.assertEqual(fm["check-exclude"], ["Pods/*"])
        self.assertEqual(fm["check-hint"], "상대경로/변수로 바꿔라")

    def test_status_is_always_draft_even_with_checks(self):
        """이 도구는 stable 을 만들 수 없어야 한다(비준은 사람·비준기 몫)."""
        rel = self.propose("드래프트 불변 확인",
                           check_deny=["ZZZ_NEVER"], check_glob=["*.dart"])
        self.assertEqual(frontmatter(self.note(rel))["status"], "draft")

    def test_draft_with_checks_does_not_compile_to_checks(self):
        """draft 인 동안은 검사가 생기지 않아야 한다(비준 전엔 강제 없음)."""
        rel = self.propose("비준전 무강제 확인",
                           check_deny=["ZZZ_NEVER"], check_glob=["*.dart"])
        self.assertEqual(self.entry(self.compile_checks(), rel), [])

    # --- 왕복 ------------------------------------------------------------
    def test_round_trip_deny_reaches_dw_checks_json(self):
        rel = self.propose(
            "왕복 deny 규칙",
            check_deny=[r"DEBUG_ONLY_[A-Z]+"],
            check_glob=["*.dart", "*.php"],
            check_exclude=["test/*"],
            check_hint="디버그 토큰 제거",
        )
        self.promote_to_stable(rel)
        hits = self.entry(self.compile_checks(), rel)
        self.assertEqual(len(hits), 1, "dw-checks.json 에 해당 항목이 실재해야 한다")
        c = hits[0]
        self.assertEqual(c["deny"], [r"DEBUG_ONLY_[A-Z]+"])
        self.assertEqual(c["require"], [])
        self.assertEqual(c["glob"], ["*.dart", "*.php"])
        self.assertEqual(c["exclude"], ["test/*"])
        self.assertEqual(c["hint"], "디버그 토큰 제거")
        self.assertEqual(c["scope"], "engineering")
        self.assertEqual(c["enforced_by"], "code-review")
        self.assertEqual(c["title"], "왕복 deny 규칙")

    def test_round_trip_require_reaches_dw_checks_json(self):
        rel = self.propose(
            "왕복 require 규칙",
            check_require=[r"^declare\(strict_types=1\);"],
            check_glob=["*.php"],
        )
        self.promote_to_stable(rel)
        hits = self.entry(self.compile_checks(), rel)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["require"], [r"^declare\(strict_types=1\);"])
        self.assertEqual(hits[0]["deny"], [])

    def test_round_trip_check_fires_in_linter(self):
        """왕복의 마지막 한 칸 — 컴파일된 검사가 dw-lint 로 실제 발화하는지."""
        rel = self.propose("린터 발화 확인",
                           check_deny=[r"DEBUG_ONLY_[A-Z]+"], check_glob=["*.dart"],
                           check_hint="디버그 토큰 제거")
        self.promote_to_stable(rel)
        checks = self.compile_checks()

        proj = self.tmp / "proj"
        (proj / ".claude").mkdir(parents=True)
        (proj / ".claude" / "dw-checks.json").write_text(
            json.dumps({"checks": checks}, ensure_ascii=False), encoding="utf-8")
        target = proj / "lib" / "main.dart"
        target.parent.mkdir(parents=True)
        target.write_text("var x = DEBUG_ONLY_FLAG;\n", encoding="utf-8")

        # proj 는 git 저장소가 아니므로 dw-lint 의 _roots 는 ③ 폴백(CLAUDE_PROJECT_DIR)으로
        # 해석된다 — 그 경로를 의도적으로 태운다. env 는 os.environ 을 상속해(git 존재 등)
        # 스트립된 환경에 결과가 의존하지 않게 한다.
        r = subprocess.run(
            [sys.executable, str(LINTER)],
            input=json.dumps({"hook_event_name": "PostToolUse", "cwd": str(proj),
                              "tool_input": {"file_path": str(target)}}),
            capture_output=True, text=True, cwd=str(proj),
            env=os.environ | {"CLAUDE_PROJECT_DIR": str(proj)},
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("DEBUG_ONLY", r.stdout, f"린터가 위반을 보고하지 않았다: {r.stdout!r}")
        self.assertIn("디버그 토큰 제거", r.stdout)

    # --- 거부(죽은 검사 양산 방지) ---------------------------------------
    def test_deny_without_glob_is_rejected(self):
        """check-glob 없는 deny/require 는 컴파일러가 warn 후 검사를 **비활성**한다
        (dw-compile.py collect_checks) — '규칙은 있는데 검사는 없는' 상태를 제안 단계에서 막는다."""
        self.assertIn("check_glob", self.reject("글롭없는 규칙", check_deny=["ZZZ"]))

    def test_require_without_glob_is_rejected(self):
        self.assertIn("check_glob", self.reject("글롭없는 require 규칙", check_require=["ZZZ"]))

    def test_hint_only_is_rejected(self):
        """check_hint 만 주면 collect_checks 가 항목을 아예 만들지 않는다(경고조차 없다)
        → '검사처럼 생긴 죽은 키' 만 남는다. 다른 두 가드와 같은 이유로 거부한다."""
        self.assertIn("check_deny", self.reject("힌트만 있는 규칙", check_hint="참고"))

    def test_glob_only_is_rejected(self):
        self.assertIn("check_deny", self.reject("글롭만 있는 규칙", check_glob=["*.dart"]))

    def test_no_check_params_still_accepted(self):
        """check_* 를 하나도 안 주면 검사 없는 서술 규칙으로 정상 수락된다(거부 아님)."""
        rel = self.propose("서술만 하는 규칙")
        self.assertNotIn("check-", self.note(rel))

    def test_invalid_deny_regex_is_rejected(self):
        """깨진 정규식은 dw-lint 의 re.finditer 에서 매 파일 터진다 — 입구에서 막는다."""
        self.assertIn("foo(", self.reject("깨진 정규식 규칙",
                                          check_deny=["foo("], check_glob=["*.dart"]))

    def test_invalid_require_regex_is_rejected(self):
        self.assertIn("a[b", self.reject("깨진 require 규칙",
                                         check_require=["a[b"], check_glob=["*.dart"]))

    # --- MCP 스키마 -------------------------------------------------------
    def test_mcp_schema_exposes_optional_check_params(self):
        """MCP 도구 스키마에 5개 check 파라미터가 **옵션**으로 노출되는지.
        (스키마는 클라이언트가 서버를 spawn 할 때 읽힌다 — 재시작 전엔 세션에 안 보인다.)"""
        import asyncio
        tools = asyncio.run(self.srv.mcp.list_tools())
        tool = next(t for t in tools if t.name == "dw_propose_rule")
        props = tool.inputSchema["properties"]
        required = tool.inputSchema.get("required", [])
        for k in ("check_deny", "check_require", "check_glob", "check_exclude", "check_hint"):
            self.assertIn(k, props)
            self.assertNotIn(k, required)
        for k in ("scope", "title", "rule", "enforced_by"):
            self.assertIn(k, required)


class RatifyScanGateTest(unittest.TestCase):
    """비준기의 check 검증이 **실제로 돌고**, 검증 불가를 통과로 보고하지 않는지.

    종전엔 `make ratify` 가 `--project` 를 주지 않아 `scan_codebase` 의 루프가 한 번도 돌지 않고
    `hits=[]` → 무조건 승격이었다(2026-08-07 실측). 그리고 SKIP 에 `ios`·`android` 가 있어
    `--project` 를 줘도 `ios/**/project.pbxproj` 는 검사 대상 0 건이었다.

    ⚠️ 전부 `--dry-run` + 임시 픽스처다. 실제 `make ratify` 는 vault 를 변형하므로 돌리지 않는다.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dw-selftest-ratify-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.vault = self.tmp / "vault"
        shutil.copytree(SEED, self.vault)
        self.proj = self.tmp / "repo"
        (self.proj / "lib").mkdir(parents=True)

    # --- helpers ----------------------------------------------------------
    def write_rule(self, name: str, **fm_extra) -> str:
        fm = {"type": "rule", "status": "draft", "scope": "engineering",
              "enforced-by": "code-review", "compiles-to": "skill", "title": name}
        fm.update(fm_extra)
        body = "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" if isinstance(v, list)
                         else f"{k}: {v}" for k, v in fm.items())
        rel = f"governance/rules/{name}.md"
        (self.vault / rel).write_text(f"---\n{body}\n---\n\n본문.\n", encoding="utf-8")
        return rel

    def register(self, *projects: Path) -> None:
        """`.dw-state/projects.json` 레지스트리에 직접 등록(설치 경로와 동일한 정본)."""
        d = self.vault / ".dw-state"
        d.mkdir(parents=True, exist_ok=True)
        (d / "projects.json").write_text(
            json.dumps({"projects": [str(p) for p in projects]}, ensure_ascii=False),
            encoding="utf-8")

    def ratify(self, *extra: str) -> str:
        r = subprocess.run(
            [sys.executable, str(RATIFIER), "--vault", str(self.vault), "--dry-run", *extra],
            capture_output=True, text=True)
        self.assertIn(r.returncode, (0, 10), f"비준기 비정상 종료:\n{r.stdout}\n{r.stderr}")
        return r.stdout

    def assertHeld(self, out: str, rel: str, because: str) -> str:
        self.assertIn(rel, out)
        block = out.split(rel, 1)[1]
        self.assertIn(because, block, f"hold 사유가 기대와 다르다:\n{block[:400]}")
        self.assertNotIn(f"+ {rel}", out, "hold 되어야 하는데 승격됐다")
        return block

    # --- A/B 재현 ---------------------------------------------------------
    def test_deny_matching_existing_code_is_held(self):
        (self.proj / "lib" / "a.dart").write_text("var x = FORBIDDEN_XYZ;\n", encoding="utf-8")
        self.register(self.proj)
        rel = self.write_rule("금지패턴 매치 규칙",
                              **{"check-deny": ["FORBIDDEN_XYZ"], "check-glob": ["*.dart"]})
        out = self.ratify()
        self.assertHeld(out, rel, "매치")
        self.assertIn("검사대상 1건", out)

    def test_clean_codebase_with_candidates_is_promoted(self):
        (self.proj / "lib" / "a.dart").write_text("var x = 1;\n", encoding="utf-8")
        self.register(self.proj)
        rel = self.write_rule("깨끗한 규칙",
                              **{"check-deny": ["FORBIDDEN_XYZ"], "check-glob": ["*.dart"]})
        out = self.ratify()
        self.assertIn(f"+ {rel}", out, f"승격되어야 한다:\n{out}")
        # 승격 근거로 '무엇에 비추어 0 인가'가 함께 보고돼야 한다.
        self.assertIn("검사대상 1건 · 위반 0", out)

    # --- ③ 검증 불가를 통과로 보고하지 않는다 ------------------------------
    def test_zero_projects_is_held_not_promoted(self):
        """레지스트리가 비면 오탐 0 을 주장할 근거가 없다 — 종전엔 무조건 승격이었다."""
        rel = self.write_rule("스캔대상 없는 규칙",
                              **{"check-deny": ["FORBIDDEN_XYZ"], "check-glob": ["*.dart"]})
        out = self.ratify()
        self.assertHeld(out, rel, "스캔 대상 프로젝트 0")
        self.assertIn("/dw-install", out, "조치 방법이 안내돼야 한다")

    def test_glob_matching_zero_files_is_held(self):
        """이번 사건의 핵심 — glob 이 아무 파일도 못 잡으면 '위반 0' 은 공허하다."""
        (self.proj / "lib" / "a.dart").write_text("var x = 1;\n", encoding="utf-8")
        self.register(self.proj)
        rel = self.write_rule("대상 없는 glob 규칙",
                              **{"check-deny": ["FORBIDDEN_XYZ"], "check-glob": ["*.kt"]})
        out = self.ratify()
        self.assertHeld(out, rel, "검사대상 파일 0건")

    def test_zero_projects_does_not_hold_rules_without_checks(self):
        """**큐 정체 방지** — check 패턴이 없는 서술 규칙·guidance·procedure 는
        검증 대상이 없으므로 스캔 대상 0 이어도 정상 승격돼야 한다."""
        rule = self.write_rule("검사 없는 서술 규칙")
        (self.vault / "governance/guidance/실험용-지침.md").write_text(
            "---\ntype: guidance\nstatus: draft\nscope: engineering\ncompiles-to: skill\n"
            "title: 실험용 지침\n---\n\n본문.\n", encoding="utf-8")
        (self.vault / "governance/procedures/실험용-절차.md").write_text(
            "---\ntype: procedure\nstatus: draft\nscope: engineering\ncompiles-to: skill\n"
            "title: 실험용 절차\n---\n\n1. 본문.\n", encoding="utf-8")
        out = self.ratify()   # --project 없음, 레지스트리 없음
        for rel in (rule, "governance/guidance/실험용-지침.md",
                    "governance/procedures/실험용-절차.md"):
            self.assertIn(f"+ {rel}", out, f"검사 없는 OBEY 가 hold 됐다(큐 정체):\n{out}")

    # --- ② SKIP 좁히기: pbxproj 는 스캔되고 Pods 는 제외 --------------------
    def test_pbxproj_is_scanned_but_pods_copy_is_skipped(self):
        """`ios` 가 SKIP 에 있어 이 규칙은 검사 대상이 0 건이었다 — 이번 수정의 동기.
        동시에 `ios/Pods/` 의 벤더된 pbxproj 사본(실측 3개)은 계속 건너뛰어야 한다."""
        runner = self.proj / "ios" / "Runner.xcodeproj" / "project.pbxproj"
        runner.parent.mkdir(parents=True)
        runner.write_text("/* Runner */ shellScript = \"echo build\";\n", encoding="utf-8")
        pods = self.proj / "ios" / "Pods" / "Pods.xcodeproj" / "project.pbxproj"
        pods.parent.mkdir(parents=True)
        pods.write_text("upload-symbols\n", encoding="utf-8")   # 여기 있으면 오탐이 된다
        self.register(self.proj)
        rel = self.write_rule("pbxproj 침묵 업로드 금지",
                              **{"check-deny": ["upload-symbols"], "check-glob": ["*.pbxproj"]})
        out = self.ratify()
        # Pods 사본이 스캔됐다면 매치가 잡혀 hold 된다 → 승격 = Pods 제외 성공
        self.assertIn(f"+ {rel}", out, f"Pods 의 벤더 pbxproj 가 오탐을 만들었다:\n{out}")
        # 그리고 Runner.xcodeproj 는 **실제로** 검사 대상이어야 한다(공허한 0 이 아니어야 한다)
        self.assertIn("검사대상 1건 · 위반 0", out)

    def test_scan_prunes_heavy_trees(self):
        """SKIP 트리는 walk 자체가 내려가지 않는다(rglob 사후필터 → 프루닝)."""
        srv = load_ratifier()
        for d in ("node_modules", "ios/Pods", "target", ".git", ".worktrees", "_worktrees"):
            p = self.proj / d / "deep"
            p.mkdir(parents=True)
            (p / "x.dart").write_text("FORBIDDEN_XYZ\n", encoding="utf-8")
        (self.proj / "lib" / "ok.dart").write_text("clean\n", encoding="utf-8")
        hits, cand = srv.scan_codebase([self.proj], ["*.dart"], [], ["FORBIDDEN_XYZ"], [])
        self.assertEqual(hits, [], f"프루닝돼야 할 트리에서 매치가 나왔다: {hits}")
        self.assertEqual(cand, 1, "lib/ok.dart 만 검사 대상이어야 한다")

    # --- 레지스트리: 설치가 곧 등록 ----------------------------------------
    def test_install_registers_project_for_scanning(self):
        """`make install-project` 경로(wire-hook.py <proj> <vault> --config-only)가
        레지스트리에 역링크를 남겨야 한다 — 크론에서 인자 없이 동작하게 하는 정본."""
        r = subprocess.run(
            [sys.executable, str(WIRE_HOOK), str(self.proj), str(self.vault), "--config-only"],
            capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        reg = json.loads((self.vault / ".dw-state" / "projects.json").read_text(encoding="utf-8"))
        self.assertEqual(reg["projects"], [str(self.proj.resolve())])
        # 멱등 — 두 번 돌려도 중복되지 않는다
        subprocess.run([sys.executable, str(WIRE_HOOK), str(self.proj), str(self.vault),
                        "--config-only"], capture_output=True, text=True)
        reg2 = json.loads((self.vault / ".dw-state" / "projects.json").read_text(encoding="utf-8"))
        self.assertEqual(reg2["projects"], reg["projects"])

    def test_registry_is_outside_vault_content_dirs(self):
        """레지스트리가 vault 콘텐츠를 오염시키면 검색·컴파일에 새어 나온다."""
        subprocess.run([sys.executable, str(WIRE_HOOK), str(self.proj), str(self.vault),
                        "--config-only"], capture_output=True, text=True)
        self.assertTrue((self.vault / ".dw-state" / "projects.json").is_file())
        for d in ("governance", "project"):
            self.assertEqual(list((self.vault / d).rglob("projects.json")), [])


class RatifyInstallChainTest(unittest.TestCase):
    """비준 → **실제 compile+install** 사슬. 종전엔 여기가 @echo 두 줄이라 끊겨 있었다.

    ⚠️ 임시 vault 픽스처 + 임시 프로젝트만 쓴다. 실제 vault·실제 레포·`make ratify` 는 건드리지
    않는다(다른 세션의 draft 를 승격시키면 안 된다).
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dw-selftest-chain-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.vault = self.tmp / "vault"
        shutil.copytree(SEED, self.vault)
        self.p1 = self.tmp / "repo1"
        self.p2 = self.tmp / "repo2"
        for p in (self.p1, self.p2):
            (p / "lib").mkdir(parents=True)
            (p / "lib" / "a.dart").write_text("var x = 1;\n", encoding="utf-8")

    def register(self, *projects: Path) -> None:
        d = self.vault / ".dw-state"
        d.mkdir(parents=True, exist_ok=True)
        (d / "projects.json").write_text(
            json.dumps({"projects": [str(p) for p in projects]}, ensure_ascii=False),
            encoding="utf-8")

    def install_registered(self, *extra: str):
        return subprocess.run(
            [sys.executable, str(BUILD / "dw-install-registered.py"),
             "--vault", str(self.vault), *extra],
            capture_output=True, text=True)

    def test_installs_to_every_registered_project(self):
        self.register(self.p1, self.p2)
        r = self.install_registered()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for p in (self.p1, self.p2):
            self.assertTrue((p / ".claude" / "dw-checks.json").is_file(), f"{p} 미설치")
            self.assertTrue((p / ".claude" / "skills").is_dir())
            self.assertTrue((p / ".claude" / "dw-session-digest.md").is_file())

    def test_install_is_idempotent(self):
        self.register(self.p1)
        first = self.install_registered()
        before = (self.p1 / ".claude" / "dw-checks.json").read_text(encoding="utf-8")
        second = self.install_registered()
        self.assertEqual((first.returncode, second.returncode), (0, 0))
        self.assertEqual(before, (self.p1 / ".claude" / "dw-checks.json").read_text(encoding="utf-8"))

    def test_empty_registry_is_warning_not_failure(self):
        """설치할 곳이 없는 것은 '요청된 일이 없음' 이라 실패가 아니다(매일 빨간 실행 방지)."""
        r = self.install_registered()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("설치 대상 0개", r.stdout)

    def test_missing_registered_path_is_reported_but_not_failure(self):
        """사라진 등록 하나가 매 실행을 실패로 만들면 로그를 아무도 안 보게 된다 →
        경고로 계속 드러내되 exit 0. (자동 제거는 상태를 조용히 바꾸므로 하지 않는다.)"""
        self.register(self.p1, self.tmp / "없어진-레포")
        r = self.install_registered()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("등록 경로 없음", r.stdout)
        self.assertTrue((self.p1 / ".claude" / "dw-checks.json").is_file(), "남은 것은 계속 설치돼야 한다")

    def test_partial_failure_exits_nonzero_and_continues(self):
        """한 프로젝트 실패가 나머지를 막지 않고, **끝에 모아 보고하고 비정상 종료**한다."""
        blocked = self.tmp / "blocked"
        blocked.mkdir()
        (blocked / ".claude").write_text("나는 디렉터리가 아니라 파일이다\n", encoding="utf-8")
        self.register(blocked, self.p1)
        r = self.install_registered()
        self.assertEqual(r.returncode, 1, f"부분 실패인데 exit 0 이다:\n{r.stdout}")
        self.assertIn("실패 1", r.stdout)
        self.assertTrue((self.p1 / ".claude" / "dw-checks.json").is_file(),
                        "실패 뒤 프로젝트도 계속 처리돼야 한다")

    def test_promoted_rule_reaches_installed_checks(self):
        """전체 사슬 — draft(검사 포함) → 승격 → 설치 → 각 레포 dw-checks.json 에 실재."""
        self.register(self.p1, self.p2)
        rel = "governance/rules/사슬-검증-규칙.md"
        (self.vault / rel).write_text(
            "---\ntype: rule\nstatus: draft\nscope: engineering\nenforced-by: code-review\n"
            "compiles-to: skill\ncheck-deny: ['NEVER_ZZZ']\ncheck-glob: ['*.dart']\n"
            "title: 사슬 검증 규칙\n---\n\n본문.\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(RATIFIER), "--vault", str(self.vault)],
                           capture_output=True, text=True)
        self.assertIn(f"+ {rel}", r.stdout, f"승격되어야 한다:\n{r.stdout}")
        self.assertEqual(self.install_registered().returncode, 0)
        for p in (self.p1, self.p2):
            checks = json.loads((p / ".claude" / "dw-checks.json").read_text(encoding="utf-8"))
            self.assertIn(rel, [c["rule"] for c in checks["checks"]],
                          f"{p.name} 의 dw-checks.json 에 승격 규칙이 없다(사슬 끊김)")


class ProposeTimeVerificationTest(unittest.TestCase):
    """(A) 제안 시점 검증 — 비준기와 **같은 코드**(dw_verify)로 예측을 반환한다."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dw-selftest-predict-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.vault = self.tmp / "vault"
        shutil.copytree(SEED, self.vault)
        self.proj = self.tmp / "repo"
        (self.proj / "lib").mkdir(parents=True)
        self.srv = load_server(self.vault)

    def register(self, *projects: Path) -> None:
        d = self.vault / ".dw-state"
        d.mkdir(parents=True, exist_ok=True)
        (d / "projects.json").write_text(
            json.dumps({"projects": [str(p) for p in projects]}, ensure_ascii=False),
            encoding="utf-8")

    def test_predicts_matches_without_asserting_cause(self):
        """제안 즉시 **매치**를 알려준다 — 며칠 뒤 보류로 알게 되는 대신.

        문구 규율(비준기 자신의 계약 = dw-ratify.py:7,14): 매치를 **오탐으로 단정하지 않는다.**
        패턴 문제일 수도, 기존 코드의 실제 위반일 수도 있고 조치가 정반대다(패턴 수정 vs 코드
        수정·예외 명시). 그래서 두 해석과 각 조치를 함께 제시하고 판단은 사람·LLM 에 남긴다."""
        (self.proj / "lib" / "a.dart").write_text("var x = FORBIDDEN_ZZZ;\n", encoding="utf-8")
        self.register(self.proj)
        msg = self.srv.dw_propose_rule(
            scope="engineering", title="예측 위반 규칙", rule="본문.", enforced_by="code-review",
            check_deny=["FORBIDDEN_ZZZ"], check_glob=["*.dart"])
        self.assertIn("검증 예측", msg)
        self.assertIn("매치", msg)
        self.assertNotIn("오탐", msg, "매치를 오탐으로 단정하면 안 된다 — 조치가 정반대일 수 있다")
        self.assertIn("패턴 문제", msg)   # 해석 ① 과 그 조치
        self.assertIn("실제 위반", msg)   # 해석 ② 와 그 조치
        self.assertIn("검사대상 1건", msg, "분모(검사대상 N)를 반드시 함께 내야 한다")
        self.assertIn("보류", msg, "hold 는 거절이 아니라 '자동 승격 보류'로 읽혀야 한다")
        self.assertIn("lib/a.dart:1", msg, "어느 해석인지 판단하려면 파일:행 이 필요하다")
        rel = f"governance/rules/{self.srv._slugify('예측 위반 규칙')}.md"
        self.assertIn("status: draft", (self.vault / rel).read_text(encoding="utf-8"))

    def test_predicts_clean_pass(self):
        (self.proj / "lib" / "a.dart").write_text("var x = 1;\n", encoding="utf-8")
        self.register(self.proj)
        msg = self.srv.dw_propose_rule(
            scope="engineering", title="예측 통과 규칙", rule="본문.", enforced_by="code-review",
            check_deny=["FORBIDDEN_ZZZ"], check_glob=["*.dart"])
        self.assertIn("검사대상 1건 · 위반 0", msg)

    def test_predicts_no_candidates_distinctly(self):
        """검사대상 0 도 원인별로 갈라 안내한다 — glob 이 아무것도 잡지 못한 경우."""
        (self.proj / "lib" / "a.dart").write_text("var x = 1;\n", encoding="utf-8")
        self.register(self.proj)
        msg = self.srv.dw_propose_rule(
            scope="engineering", title="예측 대상없음 규칙", rule="본문.", enforced_by="code-review",
            check_deny=["FORBIDDEN_ZZZ"], check_glob=["*.kt"])
        self.assertIn("검사대상 0건", msg)
        self.assertIn("잡지 못했습니다", msg)
        self.assertIn("보류", msg)
        self.assertNotIn("거절", msg.replace("거절 아님", ""))

    def test_predicts_no_projects_distinctly(self):
        """같은 '검사대상 0' 이지만 원인이 레지스트리 미등록이면 조치가 다르다."""
        msg = self.srv.dw_propose_rule(
            scope="engineering", title="예측 미등록 규칙", rule="본문.", enforced_by="code-review",
            check_deny=["FORBIDDEN_ZZZ"], check_glob=["*.dart"])
        self.assertIn("검사대상 0건", msg)
        self.assertIn("/dw-install", msg, "등록 방법을 안내해야 한다")
        self.assertIn("보류", msg)

    def test_prediction_matches_ratifier_verdict(self):
        """**예측과 실제가 일치**해야 한다 — 두 구현이 갈라지면 예측이 없는 것보다 나쁘다."""
        (self.proj / "lib" / "a.dart").write_text("var x = FORBIDDEN_ZZZ;\n", encoding="utf-8")
        self.register(self.proj)
        self.srv.dw_propose_rule(
            scope="engineering", title="일치 확인 규칙", rule="본문.", enforced_by="code-review",
            check_deny=["FORBIDDEN_ZZZ"], check_glob=["*.dart"])
        rel = f"governance/rules/{self.srv._slugify('일치 확인 규칙')}.md"
        r = subprocess.run([sys.executable, str(RATIFIER), "--vault", str(self.vault), "--dry-run"],
                           capture_output=True, text=True)
        self.assertNotIn(f"+ {rel}", r.stdout, "예측은 hold 였는데 실제로는 승격됐다")
        self.assertIn(rel, r.stdout)


class SessionHookTest(unittest.TestCase):
    """(B) 세션 시작 훅 — 값싸고, 조용히 죽지 않고, 세션을 막지 않는다."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dw-selftest-hook-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.vault = self.tmp / "vault"
        shutil.copytree(SEED, self.vault)
        self.proj = self.tmp / "repo"
        (self.proj / "lib").mkdir(parents=True)
        (self.proj / "lib" / "a.dart").write_text("var x = 1;\n", encoding="utf-8")
        (self.proj / ".claude").mkdir(parents=True, exist_ok=True)
        (self.proj / ".claude" / "dw-config.json").write_text(
            json.dumps({"vault_root": str(self.vault)}), encoding="utf-8")

    def register(self, *projects: Path) -> None:
        d = self.vault / ".dw-state"
        d.mkdir(parents=True, exist_ok=True)
        (d / "projects.json").write_text(
            json.dumps({"projects": [str(p) for p in projects]}, ensure_ascii=False),
            encoding="utf-8")

    def run_hook(self):
        return subprocess.run(
            [sys.executable, str(BUILD / "dw-ratify-session.py")],
            input=json.dumps({"hook_event_name": "SessionStart", "cwd": str(self.proj)}),
            capture_output=True, text=True,
            env=os.environ | {"CLAUDE_PROJECT_DIR": str(self.proj),
                              "DW_VAULT_DIR": str(self.vault)})

    def log(self) -> str:
        f = self.vault / ".dw-state" / "ratify.log"
        return f.read_text(encoding="utf-8") if f.is_file() else ""

    def test_no_drafts_is_cheap_and_silent(self):
        """draft 0 + 설치본 아님 → 무작업. 대부분의 세션이 이 경로다."""
        self.register(self.proj)
        r = self.run_hook()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "", "할 일이 없는데 세션에 문맥을 주입했다")
        self.assertIn("무작업", self.log())

    def test_promotion_installs_and_reports_to_session(self):
        self.register(self.proj)
        (self.vault / "governance/rules/훅-승격-규칙.md").write_text(
            "---\ntype: rule\nstatus: draft\nscope: engineering\nenforced-by: code-review\n"
            "compiles-to: skill\ntitle: 훅 승격 규칙\n---\n\n본문.\n", encoding="utf-8")
        r = self.run_hook()
        self.assertEqual(r.returncode, 0, r.stderr)
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("승격", ctx)
        self.assertTrue((self.proj / ".claude" / "dw-checks.json").is_file(), "설치가 안 됐다")
        self.assertIn("설치", self.log())

    def test_hold_is_surfaced_to_session(self):
        """hold 는 조용히 사라지면 안 된다 — 세션이 보게 한다."""
        self.register()
        (self.vault / "governance/rules/훅-홀드-규칙.md").write_text(
            "---\ntype: rule\nstatus: draft\nscope: engineering\nenforced-by: code-review\n"
            "compiles-to: skill\ncheck-deny: ['ZZZ']\ncheck-glob: ['*.dart']\n"
            "title: 훅 홀드 규칙\n---\n\n본문.\n", encoding="utf-8")
        r = self.run_hook()
        self.assertEqual(r.returncode, 0)
        self.assertIn("hold", r.stdout)
        self.assertIn("hold 1", self.log())

    def test_broken_vault_never_blocks_session(self):
        """어떤 상황에서도 세션 시작을 막지 않는다(exit 0)."""
        r = subprocess.run(
            [sys.executable, str(BUILD / "dw-ratify-session.py")],
            input="not json at all", capture_output=True, text=True,
            env=os.environ | {"CLAUDE_PROJECT_DIR": str(self.proj),
                              "DW_VAULT_DIR": str(self.tmp / "존재하지-않는-vault")})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_stale_artifacts_are_refreshed_for_current_repo_only(self):
        """사람이 vault stable 을 고친 경우 — 이 레포만 갱신한다(교차 레포 비용 없음)."""
        other = self.tmp / "other"
        (other / ".claude").mkdir(parents=True)
        self.register(self.proj, other)
        subprocess.run([sys.executable, str(BUILD / "dw-install-registered.py"),
                        "--vault", str(self.vault), "--project", str(self.proj), "--quiet"],
                       capture_output=True, text=True)
        marker = self.proj / ".claude" / "dw-checks.json"
        os.utime(marker, (1, 1))
        r = self.run_hook()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertGreater(marker.stat().st_mtime, 1, "낡은 산출물이 갱신되지 않았다")
        self.assertFalse((other / ".claude" / "dw-checks.json").exists(),
                         "승격이 없는데 다른 레포까지 설치했다(비용 낭비)")


def load_launcher():
    """dw-mcp-launch.py 를 모듈로 로드(파일명에 하이픈이 있어 일반 import 불가).

    런처는 `if __name__ == "__main__"` 가드가 있어야 한다 — 없으면 이 임포트 한 줄이
    실제 venv 부트스트랩 + exec 를 일으킨다(그 자체가 아래 테스트의 암묵 검증이다).
    """
    spec = importlib.util.spec_from_file_location(f"dw_mcp_launch_{next(_counter)}", LAUNCHER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class McpLauncherTest(unittest.TestCase):
    """(C) dw-vault MCP 런처 — 셸 없이 vault 를 해석하고 서버를 띄운다.

    이 레포의 플러그인 핵심은 dw-vault MCP 다. 런처가 기동하지 못하면 도구 11 개가 전부
    사라진다. 플랫폼 분기는 **양쪽 다** 고정한다 — Windows 실기가 없으므로(2026-08-08)
    단위 테스트가 그 분기에 대해 우리가 가진 유일한 증거다.
    """

    def setUp(self):
        # 기반 로직(vault 해석·venv 레이아웃·핀)의 정본은 dw_runtime 이다(2.15.0) — 런처와 CLI
        # 가 공유한다. 런처에 남은 것은 기동 분기(execv vs 자식)뿐이라 둘을 나눠 잡는다.
        self.mod = dw_runtime
        self.launcher = load_launcher()
        self.tmp = Path(tempfile.mkdtemp(prefix="dw-selftest-launch-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    # ── venv 레이아웃 분기 ────────────────────────────────────────────────
    def test_venv_python_posix_layout(self):
        self.assertEqual(self.mod.venv_python(Path("/x/.venv"), "posix"),
                         Path("/x/.venv/bin/python"))

    def test_venv_python_windows_layout(self):
        """Windows: Scripts/python.exe. 실기 없이 고정할 수 있는 최대치."""
        self.assertEqual(self.mod.venv_python(Path("/x/.venv"), "nt"),
                         Path("/x/.venv/Scripts/python.exe"))

    def test_venv_python_falls_back_when_venv_schemes_absent(self):
        """py<3.11 경로 — `nt_venv`/`posix_venv` 스킴이 없으면 CPython 리터럴 레이아웃으로.

        가정이 아니라 **살아있는 경로**다: 배선이 `command: "python3"` 이라 CC 가 해석한 아무
        python3 이 런처를 임포트한다. 실측(2026-08-08) 이 워크스테이션의 `/usr/bin/python3` 는
        3.9.6 이고 두 스킴 모두 `KeyError` 다 — 이 분기가 안 맞으면 dw-vault 가 조용히 죽는다.
        """
        with unittest.mock.patch.object(self.mod.sysconfig, "get_path",
                                        side_effect=KeyError("posix_venv")):
            self.assertEqual(self.mod.venv_python(Path("/x/.venv"), "posix"),
                             Path("/x/.venv/bin/python"))
            self.assertEqual(self.mod.venv_python(Path("/x/.venv"), "nt"),
                             Path("/x/.venv/Scripts/python.exe"))

    def test_venv_python_default_matches_running_platform(self):
        """기본 인자는 돌고 있는 플랫폼을 따른다(호출부가 os_name 을 잊어도 맞는다)."""
        self.assertEqual(self.mod.venv_python(Path("/x/.venv")),
                         self.mod.venv_python(Path("/x/.venv"), os.name))

    # ── DW_VAULT_DIR 홈 접두 확장 ─────────────────────────────────────────
    def test_home_prefix_expansion(self):
        e = self.mod.expand_home_prefix
        self.assertEqual(e("~/v", "/home/d"), "/home/d/v")
        self.assertEqual(e("$HOME/v", "/home/d"), "/home/d/v")

    def test_home_prefix_expansion_is_prefix_only(self):
        """경로 중간의 `~`·`$` 는 건드리지 않는다 — 실제 경로를 변형하면 안 된다."""
        e = self.mod.expand_home_prefix
        self.assertEqual(e("/abs/~/v", "/home/d"), "/abs/~/v")
        self.assertEqual(e("/abs/$HOME/v", "/home/d"), "/abs/$HOME/v")
        self.assertEqual(e("/vaults/my $stuff", "/home/d"), "/vaults/my $stuff")

    # ── vault 해석 순서(env > 규약 > 에러, 폴백 없음) ──────────────────────
    def test_vault_env_wins(self):
        v = self.tmp / "custom vault"          # 공백 포함 — 따옴표 없는 세상에서도 안전해야 한다
        v.mkdir()
        self.assertEqual(self.mod.resolve_vault({"DW_VAULT_DIR": str(v)}, str(self.tmp),
                                                warn=lambda m: None), v)

    def test_vault_falls_back_to_convention_when_env_dir_missing(self):
        conv = self.tmp / self.mod.CONVENTIONAL_VAULT
        conv.mkdir()
        warned = []
        got = self.mod.resolve_vault({"DW_VAULT_DIR": str(self.tmp / "없음")}, str(self.tmp),
                                     warn=warned.append)
        self.assertEqual(got, conv)
        self.assertTrue(any("폴더 없음" in w for w in warned), "조용히 폴백했다")

    def test_vault_absent_refuses_to_start(self):
        """vault 없이 뜬 서버는 조용히 빈 지식으로 답한다 — 기동을 거부해야 한다."""
        warned = []
        with self.assertRaises(SystemExit) as cm:
            self.mod.resolve_vault({}, str(self.tmp), warn=warned.append)
        self.assertEqual(cm.exception.code, 1)
        self.assertTrue(any("vault 없음" in w for w in warned))

    # ── 기동 방식 분기 ────────────────────────────────────────────────────
    def test_launch_uses_execv_on_posix(self):
        calls = {}
        self.launcher.launch(
            Path("/py"), Path("/s.py"), Path("/v"), "posix",
            execv=lambda p, a: calls.setdefault("execv", (p, a)),
            run=lambda a: self.fail("POSIX 에서 자식 프로세스를 만들었다"))
        self.assertEqual(calls["execv"],
                         ("/py", ["/py", "/s.py", "--vault", "/v"]))

    def test_launch_spawns_child_on_windows(self):
        """Windows 의 execv 는 원래 PID 를 종료시켜 클라이언트가 '서버 죽음' 으로 읽는다."""
        class R:
            returncode = 7
        calls = {}

        def fake_run(argv):
            calls["run"] = argv
            return R()

        rc = self.launcher.launch(
            Path("/py"), Path("/s.py"), Path("/v"), "nt",
            execv=lambda p, a: self.fail("Windows 에서 execv 를 썼다"),
            run=fake_run)
        self.assertEqual(rc, 7, "자식 종료코드를 전달하지 않았다")
        self.assertEqual(calls["run"], ["/py", "/s.py", "--vault", "/v"])

    # ── venv 부트스트랩 멱등 ──────────────────────────────────────────────
    def test_existing_venv_is_reused(self):
        venv = self.tmp / ".venv"
        (venv / "bin").mkdir(parents=True)
        (venv / "bin" / "python").write_text("", encoding="utf-8")
        self.mod.ensure_venv(venv, "posix",
                             run=lambda cmd, what: self.fail(f"기존 venv 를 재설치했다: {what}"))

    def test_bootstrap_failure_is_loud(self):
        """venv 생성 실패(예: Debian 계열 python3-venv 미설치)는 조용히 죽으면 안 된다."""
        def boom(cmd, what):
            raise SystemExit(1)
        with self.assertRaises(SystemExit):
            self.mod.ensure_venv(self.tmp / ".venv", "posix", run=boom)

    # ── 배선 회귀 가드 ────────────────────────────────────────────────────
    def test_plugin_wiring_needs_no_shell(self):
        """plugin.json 의 mcpServers 는 exec 형태(command+args)여야 한다.

        `command` 에 `.sh`/`.bat` 를 두면 그 셸이 없는 플랫폼에서 MCP 가 통째로 죽는다.
        (mcpServers.command 는 셸을 경유하지 않고 직접 spawn 된다.)
        """
        cfg = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        srv = cfg["mcpServers"]["dw-vault"]
        self.assertEqual(srv["command"], "python3")
        self.assertEqual(srv["args"], ["${CLAUDE_PLUGIN_ROOT}/_build/dw-mcp-launch.py"])
        self.assertTrue(LAUNCHER.is_file(), "배선이 가리키는 런처가 없다")
        self.assertFalse((BUILD / "dw-mcp-launch.sh").exists(),
                         "POSIX 셸 런처가 되살아났다 — 부트스트랩 경로가 둘로 갈린다")

    def test_dependency_pin_lives_in_exactly_one_place(self):
        """`mcp<2` 핀의 정본은 `dw_runtime.DEPS` **한 곳**이어야 한다.

        2.14.0 까지는 Makefile 레시피와 런처 양쪽에 리터럴로 있었다 — 갈리면 **신규 venv 에서만**
        발현하는 조용한 파손이 된다(기존 venv 는 1.x 를 들고 있어 무증상). 사본이 다시 늘어나는
        것을 막는 게 이 테스트의 일이다. 소비자(런처·CLI·Makefile)는 전부 DEPS 를 경유한다.
        """
        self.assertEqual(self.mod.DEPS, ("pyyaml", "mcp<2"))
        # 산문에서 핀을 **언급**하는 것은 정상이다(주석·독스트링). 금지되는 건 **두 번째 설치
        # 지점** — 즉 소비자 파일 안의 `pip install … mcp…` 다.
        for name in ("Makefile", "_build/dw-mcp-launch.py", "_build/dw.py"):
            for lineno, line in enumerate((ROOT / name).read_text(encoding="utf-8").splitlines(), 1):
                if "pip install" in line:
                    self.assertNotIn("mcp", line,
                                     f"{name}:{lineno} 에 두 번째 설치 지점이 생겼다 "
                                     f"— dw_runtime.DEPS 를 경유하라: {line.strip()}")

    # ── 실제 기동(JSON-RPC handshake) ─────────────────────────────────────
    def test_launcher_serves_all_tools_over_stdio(self):
        """런처로 띄운 서버가 initialize 하고 도구를 전부 노출하는지 — 최종 게이트.

        stdout 은 JSON-RPC 채널이므로 한 줄이라도 오염되면 `json.loads` 에서 터진다
        (부트스트랩 출력이 새는 회귀를 이 테스트가 잡는다).
        """
        py = self.mod.venv_python(ROOT / ".venv")
        if not py.exists():
            self.skipTest(f"venv 없음({py}) — `make test` 는 부트스트랩 후 실행된다")
        expected = (BUILD / "dw-mcp-server.py").read_text(encoding="utf-8").count("@mcp.tool()")

        vault = self.tmp / "vault"
        shutil.copytree(SEED, vault)
        env = {k: v for k, v in os.environ.items() if k != "DW_VAULT_DIR"}
        env |= {"CLAUDE_PLUGIN_ROOT": str(ROOT), "DW_VAULT_DIR": str(vault)}

        proc = subprocess.Popen([sys.executable, str(LAUNCHER)],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=env, bufsize=1)
        self.addCleanup(proc.kill)
        killer = threading.Timer(120, proc.kill)   # 블로킹 read 를 깨우는 워치독
        killer.start()
        self.addCleanup(killer.cancel)
        proc.stdin.write(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "dw-selftest", "version": "0"}}}) + "\n"
            + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
            + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}) + "\n")
        proc.stdin.flush()

        got = {}
        try:
            for line in proc.stdout:          # 워치독이 kill 하면 EOF 로 풀린다(무한 대기 없음)
                line = line.strip()
                if not line:
                    continue
                msg = json.loads(line)
                if msg.get("id") is not None:
                    got[msg["id"]] = msg
                if 2 in got:
                    break
        finally:
            # ⚠️ stderr 는 **프로세스를 먼저 끝낸 뒤** 읽는다. 살아있는 자식의 stderr.read()
            #    는 EOF 까지 블록한다(어서션 메시지 안에서 부르면 즉시 교착 — 실제로 밟았다).
            killer.cancel()
            try:
                proc.stdin.close()
            except OSError:
                pass
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        err = proc.stderr.read()
        proc.stdout.close()
        proc.stderr.close()
        self.assertIn(1, got, f"initialize 응답 없음. stderr={err}")
        self.assertEqual(got[1]["result"]["serverInfo"]["name"], "dw-vault")
        names = {t["name"] for t in got[2]["result"]["tools"]}
        self.assertEqual(len(names), expected, f"도구 수 불일치: {sorted(names)}")
        self.assertIn("dw_search", names)


class PortableCliTest(unittest.TestCase):
    """(D) `dw.py` CLI — 슬래시 커맨드의 make 의존을 없앤 **로직 정본**.

    가장 중요한 검사는 **드리프트 방지**다: Makefile 타깃이 CLI 에 실제로 위임하는지.
    두 구현이 갈라지면 `make X` 와 `/dw-X` 가 다르게 동작한다(이 레포에서 반복 관측된 결함).
    make/CLI 산출물 동등성 자체는 임시 vault·설정으로 세션에서 실측했다 —
    여기서는 그 구조가 유지되는지를 고정한다.
    """

    # 위임 대상 = 슬래시 커맨드가 필요로 하는 9 개 타깃 + 파생 2 개.
    DELEGATED = (
        "build", "dry-run", "install-project", "ratify", "review",
        "scaffold-vault", "plugin-scope-user", "plugin-scope-project", "plugin-scope-off",
        "doctor", "venv",
    )

    def setUp(self):
        self.cli = load_cli()
        self.tmp = Path(tempfile.mkdtemp(prefix="dw-selftest-cli-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def recipes(self) -> dict:
        """Makefile 을 파싱해 `타깃 -> 레시피 줄 리스트`. (make 는 탭으로 레시피를 표시한다.)"""
        out: dict[str, list[str]] = {}
        target = None
        for line in (ROOT / "Makefile").read_text(encoding="utf-8").splitlines():
            if line.startswith("\t"):
                if target:
                    body = line.lstrip("\t").lstrip("@").strip()
                    if body:
                        out[target].append(body)
            elif ":" in line and not line.startswith(("#", " ", ".")):
                target = line.split(":", 1)[0].strip()
                out.setdefault(target, [])
        return out

    def test_every_delegated_target_only_calls_the_cli(self):
        """위임 타깃의 레시피는 **CLI 호출(+입력 가드)뿐**이어야 한다.

        레시피가 컴파일러·스크립트를 직접 부르기 시작하면 그 순간 구현이 둘이 된다.
        `@test -n` 가드는 예외로 허용한다 — 로직이 아니라 입력 검증이고, make 는 P 없이
        불렸을 때 플러그인 루트 자신에 설치하지 않고 멈춰야 한다(CLI 는 cwd 기본값).
        """
        recipes = self.recipes()
        sub = "bootstrap"
        for target in self.DELEGATED:
            self.assertIn(target, recipes, f"Makefile 에 {target} 타깃이 없다")
            body = [l for l in recipes[target] if not l.startswith("test -n ")]
            self.assertTrue(body, f"{target}: 레시피가 비었다")
            expect = sub if target == "venv" else target
            for line in body:
                self.assertTrue(line.startswith("$(DW) "),
                                f"{target}: CLI 위임이 아닌 레시피 줄 — {line}")
                self.assertIn(expect, line, f"{target}: 다른 서브커맨드를 부른다 — {line}")
            for banned in ("$(VPY)", "$(COMPILE)", "cp -R", "mkdir -p", "$(MAKE)"):
                self.assertFalse(any(banned in l for l in recipes[target]),
                                 f"{target}: 위임 타깃이 {banned} 를 직접 쓴다(구현 이중화)")

    def test_cli_exposes_a_subcommand_for_every_delegated_target(self):
        """타깃 ↔ 서브커맨드 이름이 1:1 이어야 한다(문서·감사가 그 매핑에 의존한다)."""
        names = set(self.cli.SUBCOMMANDS)
        for target in self.DELEGATED:
            expect = "bootstrap" if target == "venv" else target
            self.assertIn(expect, names, f"CLI 에 {expect} 서브커맨드가 없다")

    def test_commands_call_the_cli_not_make(self):
        """슬래시 커맨드 문서에 `make` 호출이 남아 있으면 안 된다 — L3 의 본체."""
        offenders = []
        for md in sorted((ROOT / "commands").glob("*.md")):
            for lineno, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"\bmake\s+(-C|[a-z][a-z-]*\b)", line):
                    offenders.append(f"{md.name}:{lineno}: {line.strip()}")
        self.assertEqual(offenders, [], "커맨드가 아직 make 를 부른다:\n" + "\n".join(offenders))

    def test_commands_have_no_shell_command_substitution(self):
        """`dw.py` 호출에 `$(pwd)` 류 셸 치환이 없어야 한다 — CLI 가 cwd 를 기본값으로 받는다.

        범위: **CLI 를 부르는 줄**. 커맨드 문서엔 아직 `dw-graphify-register.py`·`dw-ci-review.py`
        같은 선택 단계가 `--project "$(pwd)"` 를 쓴다(의도적 잔여 — CHANGELOG 명시). Git Bash 는
        셸 치환을 제공하므로 make 부재만큼 치명적이지 않고, 그 스크립트들은 이번 범위 밖이다.
        """
        offenders = []
        for md in sorted((ROOT / "commands").glob("*.md")):
            for lineno, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
                if "dw.py" in line and ("$(pwd)" in line or "`pwd`" in line):
                    offenders.append(f"{md.name}:{lineno}: {line.strip()}")
        self.assertEqual(offenders, [], "커맨드에 셸 치환이 남았다:\n" + "\n".join(offenders))

    def test_project_defaults_to_cwd(self):
        """`--project` 생략 = 현재 디렉토리(커맨드 문서에서 `$(pwd)` 를 없앤 근거)."""
        self.assertEqual(self.cli._project(None), Path.cwd().resolve())
        self.assertEqual(self.cli._project(str(self.tmp)), self.tmp.resolve())

    def test_scope_off_does_not_default_to_cwd(self):
        """`off` 만 예외 — 어쩌다 들어온 디렉토리에 settings.json 을 만들면 안 된다."""
        calls = []
        with unittest.mock.patch.object(self.cli, "_run", lambda argv: calls.append(argv) or 0), \
             unittest.mock.patch.object(self.cli, "_venv_py", lambda: Path("/py")):
            self.cli.cmd_plugin_scope_off(argparse.Namespace(project=None))
            self.cli.cmd_plugin_scope_project(argparse.Namespace(project=str(self.tmp)))
        self.assertEqual(len(calls[0]), 3, f"off 가 프로젝트 인자를 붙였다: {calls[0]}")
        self.assertEqual(str(calls[1][-1]), str(self.tmp.resolve()))

    def test_scaffold_copy_never_clobbers(self):
        """seed 복사는 `cp -Rn` 등가 — 사용자가 쌓은 vault 노트를 되돌리면 사고다."""
        src, dst = self.tmp / "src", self.tmp / "dst"
        (src / "governance").mkdir(parents=True)
        (src / "governance" / "a.md").write_text("seed\n", encoding="utf-8")
        (src / "b.md").write_text("seed-b\n", encoding="utf-8")
        (dst / "governance").mkdir(parents=True)
        (dst / "governance" / "a.md").write_text("사용자가 고친 내용\n", encoding="utf-8")

        copied, kept = self.cli._copy_no_clobber(src, dst)
        self.assertEqual((copied, kept), (1, 1))
        self.assertEqual((dst / "governance" / "a.md").read_text(encoding="utf-8"),
                         "사용자가 고친 내용\n", "기존 파일을 덮었다")
        self.assertEqual((dst / "b.md").read_text(encoding="utf-8"), "seed-b\n")
        self.assertEqual(self.cli._copy_no_clobber(src, dst), (0, 2), "재실행이 멱등이 아니다")

    def test_output_order_survives_a_pipe(self):
        """파이프로 받아도 부모/자식 출력 순서가 유지돼야 한다.

        파이썬 stdout 은 파이프에서 block-buffered 라, 자식을 띄우기 전에 flush 하지 않으면
        부모의 `print` 가 프로세스 종료 시점에야 나가 자식 출력 **뒤로** 밀린다. 실측으로 밟은
        회귀다 — `dw.py doctor | cat` 이 헬스체크 헤더를 외부 의존 목록 뒤에 찍었다.
        에이전트(Bash 도구)가 보는 경로가 바로 이 파이프 경로라, tty 에서만 확인하면 못 잡는다.
        """
        r = subprocess.run([sys.executable, str(BUILD / "dw.py"), "doctor"],
                           capture_output=True, text=True)   # capture_output = 파이프
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = [l for l in r.stdout.splitlines() if l.strip()]
        self.assertTrue(lines[0].startswith("== denver-workflow 헬스체크"),
                        f"헤더가 첫 줄이 아니다(자식 출력이 앞질렀다):\n{r.stdout}")
        own = next(i for i, l in enumerate(lines) if "MCP 서버" in l)
        external = next(i for i, l in enumerate(lines) if "Obsidian" in l)
        self.assertLess(own, external, f"자체 점검이 외부 의존 목록 뒤로 밀렸다:\n{r.stdout}")

    def test_review_still_diagnoses_when_vault_is_missing(self):
        """vault 가 없어도 `review` 는 헬스체크까지 출력해야 한다.

        `/dw-review` 의 절반은 진단이다 — vault 부재가 바로 진단이 필요한 상황이므로, 큐를 못
        읽는다는 이유로 조기 종료하면 **신규 머신에서 아무 안내도 못 받는다**. 종전
        `make review` 는 빈 큐 + 헬스체크를 보여줬다(2.15.0 개발 중 실제로 회귀시켰다가 잡음).
        """
        env = os.environ | {"DW_VAULT_DIR": str(self.tmp / "없는-vault"),
                            "HOME": str(self.tmp)}      # 규약 경로도 비게 만든다
        r = subprocess.run([sys.executable, str(BUILD / "dw.py"), "review"],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, f"진단 커맨드가 실패로 끝났다: {r.stderr}")
        self.assertIn("헬스체크", r.stdout, f"헬스체크가 출력되지 않았다:\n{r.stdout}")
        self.assertIn("vault 없음", r.stdout, f"vault 부재를 알리지 않았다:\n{r.stdout}")

    def test_cli_runs_under_the_repo_python_floor(self):
        """CLI 는 CC 가 해석한 아무 python3 으로 돌 수 있어야 한다 — `--help` 가 그 최소 증거.

        배선·커맨드가 `python3` 을 부르므로, 3.9 처럼 낮은 인터프리터에서 문법/임포트가 깨지면
        모든 슬래시 커맨드가 죽는다(이 워크스테이션의 `/usr/bin/python3` 는 3.9.6).
        """
        for interp in ("/usr/bin/python3", sys.executable):
            if not Path(interp).exists():
                continue
            r = subprocess.run([interp, str(BUILD / "dw.py"), "--help"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{interp}: {r.stderr}")
            self.assertIn("install-project", r.stdout, interp)


def load_cli():
    """dw.py 를 모듈로 로드. 하이픈이 없어 직접 import 도 되지만, 테스트 간 격리를 위해 매번 새로."""
    spec = importlib.util.spec_from_file_location(f"dw_cli_{next(_counter)}", BUILD / "dw.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_ratifier():
    """dw-ratify.py 를 모듈로 로드(파일명에 하이픈이 있어 일반 import 불가)."""
    spec = importlib.util.spec_from_file_location(f"dw_ratify_{next(_counter)}", RATIFIER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class VaultResolutionTest(unittest.TestCase):
    """(E) vault 해석의 **단일 정본**(`dw_runtime`) — 2.16.0 에서 11 곳을 통합한 그 계약.

    왜 이 클래스가 필요한가: 통합 전 11 곳은 **복제가 아니라 시맨틱이 갈려 있었다**.
    우선순위 2 종(env-first 4 곳 / config-first 7 곳), 홈 확장 3 종, 존재 요구 4 종 —
    그래서 같은 머신에서 도구별로 **다른 vault 를 가리킬 수 있었다**(오늘은 `dw-config.json`
    값이 env 와 같아 증상이 없었을 뿐, 갈라지는 순간 조용히 갈라진다). 여기서 각 분기를
    고정해 두지 않으면 사본이 다시 늘어난다.

    모든 케이스는 **주입된 env·home** 으로만 결정된다(cwd·실제 vault 를 읽지 않는다).
    """

    def setUp(self):
        self.mod = dw_runtime
        self.tmp = Path(tempfile.mkdtemp(prefix="dw-selftest-vault-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        self.env_vault = self._vault("vaultE")
        self.cfg_vault = self._vault("vaultC")
        self.conv = self._vault(Path("home") / dw_runtime.CONVENTIONAL_VAULT)
        self.project = self.tmp / "proj"
        self.project.mkdir(parents=True, exist_ok=True)

    def _vault(self, rel) -> Path:
        p = self.tmp / rel
        (p / "governance").mkdir(parents=True, exist_ok=True)
        return p

    def _config(self, value, where: Path | None = None) -> Path:
        cfg = (where or self.project) / ".claude" / "dw-config.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({"vault_root": str(value)}), encoding="utf-8")
        return cfg

    def _find(self, env=None, **kw):
        return self.mod.find_vault(kw.pop("project", self.project), env or {},
                                   str(self.home), **kw)

    # ── 우선순위: env > dw-config.json > 규약 ──────────────────────────────
    def test_env_wins_over_config(self):
        """분기의 핵심 케이스. 종전 가드·graphify 7 곳은 여기서 **config** 를 골랐다.

        사용자 결정("vault 는 하나를 가리켜야 한다")에 따라 env 를 정본으로 삼는다 — env 는
        머신 전역 단일 답이고, config 는 프로젝트별 파일이라 레포마다 갈릴 수 있다.
        """
        self._config(self.cfg_vault)
        self.assertEqual(self._find({"DW_VAULT_DIR": str(self.env_vault)}), self.env_vault)

    def test_config_is_used_when_env_absent(self):
        """env 를 못 받는 컨텍스트(러너·다른 셸)의 안전망."""
        self._config(self.cfg_vault)
        self.assertEqual(self._find({}), self.cfg_vault)

    def test_config_is_used_when_env_points_at_missing_dir(self):
        """stale env(옮겨진 vault)는 다음 출처로 넘어간다 — 종전 env-first 4 곳은 규약으로 갔다."""
        self._config(self.cfg_vault)
        got = self._find({"DW_VAULT_DIR": str(self.tmp / "없음")})
        self.assertEqual(got, self.cfg_vault)

    def test_config_is_the_only_safety_net_when_convention_is_absent(self):
        """이 머신의 형상: 규약 경로(`~/denver-workflow-vault`)가 **없다**(실측 2026-08-08).

        그래서 env 가 없을 때 규약 폴백은 죽은 경로이고 `dw-config.json` 이 유일한 안전망이다.
        """
        shutil.rmtree(self.conv)
        self._config(self.cfg_vault)
        self.assertEqual(self._find({}), self.cfg_vault)

    def test_convention_is_last(self):
        self.assertEqual(self._find({}), self.conv)

    def test_nothing_found_is_none_not_exception(self):
        """훅에서 부른다 — 못 찾으면 None 이어야 한다(예외는 세션을 깨뜨린다)."""
        shutil.rmtree(self.conv)
        self.assertIsNone(self._find({}))

    def test_config_value_expands_home_prefix(self):
        """`dw-config.json` 에 `~/…` 가 적혀도 확장된다 — 종전 가드 5 곳은 못 했다(원문 is_dir)."""
        rel = self.cfg_vault.relative_to(self.tmp)
        self._config(f"~/../{rel}")
        self.assertEqual(self._find({}).resolve(), self.cfg_vault.resolve())

    # ── 홈 접두 확장 (3 종의 통합) ─────────────────────────────────────────
    def test_userprofile_prefix_expands_on_every_platform(self):
        """`%USERPROFILE%` 는 **posix 에서 expandvars 로 확장되지 않는다**(실측 3.9.6·3.14.6).

        종전 doctor·가드 5 곳은 `expandvars` 로 그것을 처리한다고 주석에 적었지만 Windows 에서만
        참이었다. Windows 전제를 실제로 보존하려면 접두를 명시해야 한다.
        """
        e = self.mod.expand_home_prefix
        self.assertEqual(e("%USERPROFILE%/v", "/home/d"), "/home/d/v")
        self.assertEqual(e("%USERPROFILE%\\v", "/home/d"), "/home/d/v")
        self.assertEqual(e("~\\v", "/home/d"), "/home/d/v")
        self.assertEqual(os.path.expandvars("%USERPROFILE%/v") if os.name != "nt" else "/home/d/v",
                         "%USERPROFILE%/v" if os.name != "nt" else "/home/d/v",
                         "expandvars 가 posix 에서 %VAR% 를 확장하기 시작했다 — 근거 재확인 필요")

    def test_mid_path_variables_are_not_expanded(self):
        """경로 **중간**의 `$VAR` 는 건드리지 않는다.

        종전 `make` 의 `eval echo` 는 미정의 `$NOPE` 를 빈 문자열로 지워 `/x/$NOPE/v` 를
        `/x//v` 로 만들었다 — **존재하는 엉뚱한 경로**가 되는 형태다.
        """
        e = self.mod.expand_home_prefix
        self.assertEqual(e("/x/$NOPE/v", "/home/d"), "/x/$NOPE/v")
        self.assertEqual(e("/abs/~/v", "/home/d"), "/abs/~/v")

    # ── 호출자별 차이는 파라미터로 보존한다 ────────────────────────────────
    def test_ancestor_walk_finds_config_in_worktree(self):
        """do-er 워크트리는 `.claude/` 가 gitignore 라 config 가 없다 — 조상에서 찾아야 한다."""
        wt = self.project / "wt"
        wt.mkdir(parents=True, exist_ok=True)
        self._config(self.cfg_vault)                     # project(=조상)에만 둔다
        self.assertEqual(self._find({}, project=wt), self.cfg_vault)

    def test_ancestors_one_does_not_walk_up(self):
        """`dw-ratify-session` 은 종전부터 조상을 보지 않는다 — '일관성' 으로 바꾸지 않는다."""
        wt = self.project / "wt"
        wt.mkdir(parents=True, exist_ok=True)
        self._config(self.cfg_vault)
        self.assertEqual(self._find({}, project=wt, ancestors=1), self.conv)

    def test_governance_requirement_is_stricter_than_dir(self):
        """비준은 `governance/` 를 읽는다 — 폴더 존재만으로는 채택하지 않는다."""
        bare = self.tmp / "bare"
        bare.mkdir()
        env = {"DW_VAULT_DIR": str(bare)}
        self.assertEqual(self._find(env, require="dir"), bare)
        self.assertEqual(self._find(env, require="governance"), self.conv)

    def test_self_repo_fallback_is_opt_in(self):
        """가드 4 개는 '이 레포가 플러그인 본체면 자기 자신' 폴백을 갖고, artifact-guard 는 **없다**.

        종전의 그 비대칭을 파라미터로 보존한다(통합을 이유로 조용히 바꾸지 않는다).
        """
        shutil.rmtree(self.conv)
        repo = self.tmp / "repo"
        (repo / "_build").mkdir(parents=True)
        (repo / "_build" / "dw-compile.py").write_text("", encoding="utf-8")
        self.assertEqual(self._find({}, project=repo, self_repo_fallback=True), repo)
        self.assertIsNone(self._find({}, project=repo, self_repo_fallback=False))

    def test_vault_target_does_not_require_existence(self):
        """`scaffold-vault` 는 "만들 자리" 를 묻는다 — 없는 env 경로도 그대로 돌려줘야 한다."""
        missing = self.tmp / "아직-없음"
        got = self.mod.vault_target({"DW_VAULT_DIR": str(missing)}, str(self.home))
        self.assertEqual(got, missing)

    def test_vault_target_shares_the_priority_of_resolve_vault(self):
        """"만드는 곳" 과 "읽는 곳" 이 갈리면 안 된다 — 같은 순서를 쓴다."""
        self._config(self.cfg_vault)
        env = {"CLAUDE_PROJECT_DIR": str(self.project)}
        self.assertEqual(self.mod.vault_target(env, str(self.home)), self.cfg_vault)
        self.assertEqual(self.mod.resolve_vault(env, str(self.home), lambda m: None),
                         self.cfg_vault)

    # ── 계약 보호(시그니처·밀폐성) ─────────────────────────────────────────
    def test_resolve_vault_keeps_its_positional_contract(self):
        """`(env, home, warn)` 위치 순서는 계약이다 — `project` 를 위치에 끼우면 조용히 어긋난다."""
        v = self.tmp / "custom vault"     # 공백 포함
        v.mkdir()
        self.assertEqual(
            self.mod.resolve_vault({"DW_VAULT_DIR": str(v)}, str(self.tmp), lambda m: None), v)

    def test_resolution_never_falls_back_to_cwd(self):
        """프로젝트는 `CLAUDE_PROJECT_DIR`(env)·명시 인자로만 온다.

        cwd 폴백을 넣으면 이 자기검사가 **개발 머신의 실제 `.claude/dw-config.json`** 을 읽어
        실물 vault 를 잡는다(픽스처 격리가 조용히 깨진다). 실제로 밟은 함정이라 고정한다.
        """
        self._config(self.cfg_vault)
        os.chdir(self.project)            # cwd 를 config 가 있는 곳으로 옮겨도
        self.addCleanup(os.chdir, str(ROOT))
        shutil.rmtree(self.conv)
        self.assertIsNone(self.mod.find_vault(None, {}, str(self.home)))
        with self.assertRaises(SystemExit):
            self.mod.resolve_vault({}, str(self.home), lambda m: None)

    def test_project_env_supplies_the_config_tier(self):
        """MCP 런처는 `project` 를 모르지만 `CLAUDE_PROJECT_DIR` 를 **실제로 받는다**.

        실측(2026-08-08): 살아있는 dw-vault 서버 프로세스 환경에 `CLAUDE_PROJECT_DIR`·
        `DW_VAULT_DIR` 가 둘 다 있었다. 그래서 env 가 비어도 config 안전망이 남는다.
        """
        self._config(self.cfg_vault)
        shutil.rmtree(self.conv)
        env = {"CLAUDE_PROJECT_DIR": str(self.project)}
        self.assertEqual(self.mod.resolve_vault(env, str(self.home), lambda m: None),
                         self.cfg_vault)

    def test_broken_config_is_skipped_not_raised(self):
        """깨진 JSON·엉뚱한 타입·읽기 실패는 다음 후보로 넘어간다(훅은 죽지 않는다).

        `[]` 를 넣는 이유: 종전 사본 7 곳은 파싱 결과에 바로 `.get` 을 불러 최상위가 dict 가
        아니면 **`AttributeError`** 였다(훅에서 그건 세션·가드 파손). 실제로 이 케이스가 잡았다.
        NUL(`a\\u0000b`)은 `is_dir()` 이 `OSError` 가 아니라 `ValueError` 를 던지는 경로다 —
        env 로는 도달 불가(OS 가 막는다)라 **JSON 이 유일한 도달 경로**다.
        """
        cfg = self.project / ".claude" / "dw-config.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        for bad in ("{ not json", "[]", '"문자열"', "42", '{"vault_root": null}',
                    '{"vault_root": 12}', '{"vault_root": ["a"]}', '{"other": 1}',
                    '{"vault_root": "a\\u0000b"}'):
            cfg.write_text(bad, encoding="utf-8")
            self.assertEqual(self._find({}), self.conv, f"입력={bad!r}")
            self.assertIsInstance(self.mod.vault_conflict_note(self.project, {}, str(self.home)),
                                  str, f"입력={bad!r}")


class VaultConflictNoticeTest(unittest.TestCase):
    """(F) 출처 불일치 노출 — env-first 전환의 **전제조건**.

    결정론적으로 하나를 고르는 것만으로는 "vault 는 하나" 를 보증하지 못한다: 출처들이 서로
    다른 값을 말하는데 조용히 하나를 고르면 **두 곳을 가리키는 상태가 오류 없이 지나간다**.
    특히 env-first 로 뒤집힌 뒤엔 "프로젝트는 config 로 vault B 에 묶였는데 가드는 env 의
    vault A 를 지킨다" 는 새 실패 모드가 생긴다.
    """

    def setUp(self):
        self.mod = dw_runtime
        self.tmp = Path(tempfile.mkdtemp(prefix="dw-selftest-conflict-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        for name in ("vaultA", "vaultB", Path("home") / dw_runtime.CONVENTIONAL_VAULT):
            (self.tmp / name / "governance").mkdir(parents=True, exist_ok=True)
        self.a, self.b = self.tmp / "vaultA", self.tmp / "vaultB"
        self.project = self.tmp / "proj"
        self.project.mkdir()

    def _config(self, value, where: Path | None = None):
        cfg = (where or self.project) / ".claude" / "dw-config.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({"vault_root": str(value)}), encoding="utf-8")

    def _note(self, env):
        return self.mod.vault_conflict_note(self.project, env, str(self.home))

    def test_sources_that_agree_are_silent(self):
        self._config(self.a)
        self.assertEqual(self._note({"DW_VAULT_DIR": str(self.a)}), "")

    def test_single_source_is_silent(self):
        self._config(self.a)
        self.assertEqual(self._note({}), "")
        self.assertEqual(self.mod.vault_conflict_note(self.tmp / "없는-프로젝트",
                                                      {"DW_VAULT_DIR": str(self.a)},
                                                      str(self.home)), "")

    def test_nothing_declared_is_silent(self):
        self.assertEqual(self._note({}), "")

    def test_divergence_names_both_sources_and_the_fix(self):
        """문구 요건: 어느 출처가 무엇을 말하는지 + 무엇이 쓰이는지 + 맞추는 방법."""
        self._config(self.b)
        note = self._note({"DW_VAULT_DIR": str(self.a)})
        self.assertTrue(note, "불일치를 조용히 넘겼다")
        self.assertIn(str(self.a), note)
        self.assertIn(str(self.b), note)
        self.assertIn("dw-config.json", note)
        self.assertIn("DW_VAULT_DIR", note)
        self.assertIn("사용 중", note)
        chosen_line = next(l for l in note.splitlines() if "사용 중" in l)
        self.assertIn(str(self.a), chosen_line, "채택된 출처가 잘못 표시됐다")
        self.assertIn("/dw-install", note, "해소 방법이 없다")

    def test_stale_env_is_surfaced_with_its_reason(self):
        """선언은 있는데 폴더가 없는 경우도 드러낸다 — 사람이 원인을 바로 본다."""
        missing = self.tmp / "옮겨진-vault"
        self._config(self.b)
        note = self._note({"DW_VAULT_DIR": str(missing)})
        self.assertIn("폴더 없음", note)
        self.assertIn(str(missing), note)

    def test_note_never_raises(self):
        """훅에서 부른다 — 어떤 입력에도 문자열을 돌려준다."""
        for bad in ("{ not json", '{"vault_root": 12}', ""):
            (self.project / ".claude").mkdir(parents=True, exist_ok=True)
            (self.project / ".claude" / "dw-config.json").write_text(bad, encoding="utf-8")
            self.assertIsInstance(self._note({"DW_VAULT_DIR": str(self.a)}), str)
        self.assertIsInstance(self.mod.vault_conflict_note(None, {}, str(self.home)), str)

    def test_projects_bound_to_different_vaults_are_reported(self):
        """레포마다 config 가 다르면 "vault 는 하나" 가 깨진다 — on-demand 스캔이 그걸 잡는다."""
        p1, p2 = self.tmp / "p1", self.tmp / "p2"
        for p, v in ((p1, self.a), (p2, self.b)):
            p.mkdir()
            self._config(v, where=p)
        import dw_state
        vault = self.a
        dw_state.register_project(vault, p1)
        dw_state.register_project(vault, p2)
        rows = self.mod.cross_project_conflicts(vault, {}, str(self.home))
        self.assertEqual(len(rows), 2, rows)
        self.assertTrue(any(str(p1) in r and str(self.a) in r for r in rows), rows)
        self.assertTrue(any(str(p2) in r and str(self.b) in r for r in rows), rows)

    def test_projects_agreeing_report_nothing(self):
        p1, p2 = self.tmp / "p1", self.tmp / "p2"
        for p in (p1, p2):
            p.mkdir()
            self._config(self.a, where=p)
        import dw_state
        dw_state.register_project(self.a, p1)
        dw_state.register_project(self.a, p2)
        self.assertEqual(self.mod.cross_project_conflicts(self.a, {}, str(self.home)), [])

    def test_session_digest_carries_the_warning(self):
        """노출 채널은 **기존 것**을 쓴다 — 매 세션 주입되는 SessionStart 다이제스트.

        hard-fail 이 아닌 이유: 훅에서 예외를 올리면 세션이 깨진다(그건 가드가 엉뚱한 vault 를
        지키는 것보다 나쁘다). 그래서 사람이 읽는 채널로 시끄럽게만 만든다.
        """
        self._config(self.b)
        digest = self.project / ".claude" / "dw-session-digest.md"
        digest.write_text("# 다이제스트\n본문\n", encoding="utf-8")
        env = os.environ | {"DW_VAULT_DIR": str(self.a), "HOME": str(self.home),
                            "CLAUDE_PROJECT_DIR": str(self.project)}
        r = subprocess.run([sys.executable, str(BUILD / "dw-session-context.py")],
                           input=json.dumps({"hook_event_name": "SessionStart",
                                             "cwd": str(self.project)}),
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("vault", r.stdout)
        self.assertIn(str(self.b), r.stdout, f"불일치가 다이제스트에 안 실렸다:\n{r.stdout}")


class VaultResolutionSingleSourceTest(unittest.TestCase):
    """(G) **드리프트 방지** — 이 PR 의 최고가치 산출물.

    11 곳이 생긴 원인은 "복제가 검사되지 않았다" 다(`mcp<2` 핀이 두 곳으로 갈렸던 것과 같은
    결함 클래스 — 2.15.0 에서 같은 방식으로 고정했다). 사본이 다시 늘어나는 것을 막는 게
    이 클래스의 일이다.
    """

    # 정본 자신 + 검사기 자신 + env 이름을 **재작성 규칙**으로만 아는 마이그레이터.
    ALLOWED = {"dw_runtime.py", "dw-selftest.py", "dw-migrate-vault.py"}

    def _offenders(self, needle: str) -> list[str]:
        out = []
        for p in sorted(BUILD.glob("*.py")):
            if p.name in self.ALLOWED:
                continue
            for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("#") or needle not in line:
                    continue
                out.append(f"{p.name}:{lineno}: {line.strip()}")
        return out

    def test_conventional_vault_literal_lives_only_in_the_canonical_module(self):
        self.assertEqual(self._offenders(dw_runtime.CONVENTIONAL_VAULT), [],
                         "규약 경로 리터럴이 다시 복제됐다 — dw_runtime 를 경유하라:\n"
                         + "\n".join(self._offenders(dw_runtime.CONVENTIONAL_VAULT)))

    def test_env_lookup_lives_only_in_the_canonical_module(self):
        offenders = [o for o in self._offenders(f'"{dw_runtime.VAULT_ENV}"')
                     if "PROJECT_ENV" not in o]
        self.assertEqual(offenders, [],
                         f"{dw_runtime.VAULT_ENV} 를 직접 읽는 두 번째 지점이 생겼다:\n"
                         + "\n".join(offenders))

    def test_config_key_lookup_lives_only_in_the_canonical_module(self):
        """`dw-config.json` 의 `vault_root` 를 직접 읽는 곳도 정본 하나여야 한다.

        예외: `wire-hook.py` 는 그 파일을 **쓴다**(생산자), `dw-session-context.py` 는
        플러그인 **버전**을 찾을 뿐 vault 를 해석하지 않는다.
        """
        writers = {"wire-hook.py", "dw-session-context.py"}
        offenders = [o for o in self._offenders(f'"{dw_runtime.CONFIG_KEY}"')
                     if o.split(":")[0] not in writers]
        self.assertEqual(offenders, [],
                         "dw-config.json vault_root 해석이 다시 복제됐다:\n" + "\n".join(offenders))

    def test_home_expansion_helpers_are_not_reintroduced(self):
        """`os.path.expandvars`/`expanduser` 사본이 되살아나면 확장 **범위**가 갈린다.

        종전 doctor·가드 5 개가 그 둘을 썼다 — 경로 중간의 `$VAR` 까지 확장하고(미정의면 빈
        문자열로 지워 엉뚱한 경로가 된다), 정작 `%USERPROFILE%` 는 posix 에서 확장하지 못했다.
        범위 검사가 `os.path.` 로 한정된 이유: `args.vault.expanduser()` 처럼 **사용자가 준 CLI
        인자**를 푸는 것은 vault 해석이 아니다(`dw-install-registered.py` 가 그 경우다).
        """
        offenders = (self._offenders("os.path.expandvars") + self._offenders("os.path.expanduser"))
        self.assertEqual(offenders, [], "vault 경로 확장 사본이 되살아났다:\n" + "\n".join(offenders))

    def test_every_consumer_imports_the_canonical_module(self):
        """위임을 지웠는데 테스트가 통과하는 상태를 막는다."""
        consumers = ("dw-doctor.py", "dw-graphify-register.py", "dw-vault-guard.py",
                     "dw-artifact-guard.py", "dw-telemetry.py", "dw-graphify-gate.py",
                     "dw-vault-write-guard.py", "dw-ratify-session.py", "dw.py",
                     "dw-mcp-launch.py")
        for name in consumers:
            text = (BUILD / name).read_text(encoding="utf-8")
            self.assertIn("import dw_runtime", text, f"{name} 가 정본을 경유하지 않는다")

    def test_makefile_has_no_vault_resolution_of_its_own(self):
        """`make` 도 CLI 를 경유한다 — 종전 `$(shell eval echo …)` 사본이 되살아나면 안 된다."""
        for lineno, line in enumerate((ROOT / "Makefile").read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            self.assertNotIn("DW_VAULT_DIR", line, f"Makefile:{lineno} 가 env 를 직접 푼다: {line}")
            self.assertNotIn(dw_runtime.CONVENTIONAL_VAULT, line,
                             f"Makefile:{lineno} 에 규약 경로 리터럴이 있다: {line}")

    def test_canonical_module_stays_cheap_to_import(self):
        """훅 경로 예산 — `import dw_runtime` 가 `subprocess` 를 끌어오면 안 된다.

        이 모듈은 SessionStart/PostToolUse 훅 7 개가 임포트한다. `subprocess` 는 3.9.6 에서
        임포트 8.6ms 로 이 모듈 비용의 대부분이었다(실측). 측정치가 아니라 **불변식**으로
        고정한다 — 다음 편집에서 조용히 되돌아오는 것을 막는다.
        """
        for interp in ("/usr/bin/python3", sys.executable):
            if not Path(interp).exists():
                continue
            r = subprocess.run(
                [interp, "-c", "import sys; sys.path.insert(0, %r); import dw_runtime; "
                               "print('subprocess' in sys.modules, 'typing' in sys.modules)"
                 % str(BUILD)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{interp}: {r.stderr}")
            self.assertEqual(r.stdout.strip(), "False False",
                             f"{interp}: 무거운 모듈이 임포트 시점에 끌려왔다 — "
                             f"함수 안으로 옮겨라 ({r.stdout.strip()})")


class DoctorHookSafetyTest(unittest.TestCase):
    """(H) `dw-doctor.py` 는 SessionStart 훅 안에서 돈다(`dw-session-context.py` 가 호출, timeout 15).

    그래서 두 가지가 계약이다: ⓐ 어떤 입력에도 예외를 올려 훅을 깨뜨리지 않는다
    ⓑ 서브프로세스·네트워크를 쓰지 않는다(그 파일 docstring 의 「원칙」).
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dw-selftest-doctor-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.project = self.tmp / "proj"
        (self.project / ".claude").mkdir(parents=True)
        self.home = self.tmp / "home"
        self.home.mkdir()

    def _run(self, env_value=None, config=None, args=()):
        if config is not None:
            (self.project / ".claude" / "dw-config.json").write_text(config, encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k != "DW_VAULT_DIR"}
        env |= {"HOME": str(self.home), "USERPROFILE": str(self.home),
                "CLAUDE_PROJECT_DIR": str(self.project)}
        if env_value is not None:
            env["DW_VAULT_DIR"] = env_value
        return subprocess.run([sys.executable, str(BUILD / "dw-doctor.py"), *args],
                              capture_output=True, text=True, env=env)

    def test_hostile_inputs_never_break_the_hook(self):
        cases = [
            (None, None),
            ("", None),
            ("   ", None),
            (str(self.tmp / "없음"), None),
            ("~/없음", None),
            ("$HOME/없음", None),
            ("%USERPROFILE%/없음", None),
            ("/x/$NOPE/v", None),
            # NUL 은 **env 로는 도달할 수 없다**(OS 가 환경변수에 NUL 을 허용하지 않아
            # subprocess spawn 자체가 ValueError 다 — 실측). 도달 경로는 JSON 뿐이다:
            (None, '{"vault_root": "a\\u0000b"}'),
            (None, "{ not json"),
            (None, "[]"),
            (None, '{"vault_root": 12}'),
            (None, '{"vault_root": "/does/not/exist"}'),
        ]
        for env_value, config in cases:
            for args in ((), ("--json",)):
                r = self._run(env_value, config, args)
                self.assertEqual(r.returncode, 0,
                                 f"env={env_value!r} config={config!r} args={args}: {r.stderr}")
                self.assertEqual(r.stderr.strip(), "",
                                 f"env={env_value!r} config={config!r}: stderr 오염 {r.stderr!r}")
        # --json 은 기계가 읽는다 — 형태가 유지되는지도 본다
        payload = json.loads(self._run(None, None, ("--json",)).stdout)
        self.assertIn("missing_required", payload)
        self.assertIn("vault_conflict", payload)

    def test_doctor_spawns_no_subprocess(self):
        """「파일/폴더 존재 검사만」 — git 탐색(`git_probe`)을 켜면 훅 예산이 깨진다."""
        text = (BUILD / "dw-doctor.py").read_text(encoding="utf-8")
        self.assertNotIn("import subprocess", text)
        self.assertIn("git_probe=False", text, "doctor 가 서브프로세스 탐색을 켰다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
