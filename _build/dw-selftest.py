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


if __name__ == "__main__":
    unittest.main(verbosity=2)
