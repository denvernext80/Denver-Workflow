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

import importlib.util
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BUILD = Path(__file__).resolve().parent
ROOT = BUILD.parent
SERVER = BUILD / "dw-mcp-server.py"
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
        self.assertIn("install-project", out, "조치 방법이 안내돼야 한다")

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
        self.assertIn("install-project", msg, "등록 방법을 안내해야 한다")
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


def load_ratifier():
    """dw-ratify.py 를 모듈로 로드(파일명에 하이픈이 있어 일반 import 불가)."""
    spec = importlib.util.spec_from_file_location(f"dw_ratify_{next(_counter)}", RATIFIER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


if __name__ == "__main__":
    unittest.main(verbosity=2)
