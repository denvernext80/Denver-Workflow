#!/usr/bin/env python3
"""dw-graphify-register — graphify 감지 후 프로젝트 .mcp.json 에 graphify MCP 서버 등록.

graphify(시멘틱 그래프 도구)가 있고 graph.json 이 있으면, 프로젝트 .mcp.json 에 graphify.serve
(MCP stdio 서버)를 등록한다. graphify 는 optional 이라 전역 plugin.json 이 아닌 프로젝트별 .mcp.json 에 둔다.
mcp SDK 가 graphify venv 에 없으면 pipx inject 로 확보. 사용처: /dw-setup 옵인 단계.

사용:
  python3 dw-graphify-register.py --project <레포>            # dry-run(미리보기)
  python3 dw-graphify-register.py --project <레포> --apply    # 실제: inject + .mcp.json 병합
  (--graph <경로>로 graph.json 위치 지정, 기본 <레포>/graphify-out/graph.json)
"""
from __future__ import annotations
import argparse, json, shutil, subprocess, sys
from pathlib import Path

import dw_runtime


def _resolve_vault(project: Path) -> Path | None:
    """vault 루트 — 정본은 `dw_runtime.find_vault`(2.16.0). 못 찾으면 None.

    종전 사본은 **`dw-config.json` 을 env 보다 앞에** 뒀고("런처와 동일 순서" 라 적혀 있었지만
    런처는 config 를 보지도 않았다) **존재 검사를 하지 않았다** — 그래서 같은 머신에서 도구별로
    다른 vault 를 가리킬 수 있었고, config 가 옮겨진 경로를 가리키면 `graph.json` 탐색만 조용히
    실패했다. 지금은 env > config > 규약 한 순서를 쓰고, 없는 폴더는 다음 출처로 넘어간다.
    """
    return dw_runtime.find_vault(project, require="dir", git_probe=False)


def _graphify_python() -> str | None:
    """graphify 런처 shebang 에서 venv python 절대경로 해석. 없으면 None."""
    launcher = shutil.which("graphify")
    if not launcher:
        return None
    try:
        first = Path(launcher).read_text(encoding="utf-8", errors="ignore").splitlines()[0]
    except (OSError, IndexError):
        return None
    if first.startswith("#!"):
        return first[2:].strip().split()[0]
    return None


def detect(project: Path, graph_opt: str | None):
    """(graphify_python, graph_path) 또는 (None, None). graphify CLI + graph.json 둘 다 필요.
    graph 탐색: 명시 --graph > <project>/graphify-out/graph.json > <vault>/graphify-out/graph.json.
    (vault 에 ingest 한 지식 그래프를 프로젝트별 로컬 그래프가 없을 때 자동 사용한다.)"""
    py = _graphify_python()
    if not py:
        return None, None
    if graph_opt:
        g = Path(graph_opt).expanduser()
        return (py, g.resolve()) if g.is_file() else (None, None)
    local = project / "graphify-out" / "graph.json"
    if local.is_file():
        return py, local.resolve()
    vault = _resolve_vault(project)
    if vault is not None:
        vault_graph = vault / "graphify-out" / "graph.json"
        if vault_graph.is_file():
            return py, vault_graph.resolve()
    return None, None


def merge_mcp_json(project: Path, graphify_py: str, graph: Path) -> dict:
    """기존 .mcp.json 을 읽어 graphify 키만 추가/갱신한 dict 반환(쓰기 없음)."""
    p = project / ".mcp.json"
    data = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    servers["graphify"] = {
        "command": graphify_py,
        "args": ["-m", "graphify.serve", str(graph)],
    }
    data["mcpServers"] = servers
    return data


def _ensure_mcp(graphify_py: str) -> bool:
    """graphify venv 에서 mcp import 가능? 아니면 pipx inject 시도. 성공 여부."""
    if subprocess.run([graphify_py, "-c", "import mcp"], capture_output=True).returncode == 0:
        return True
    if not shutil.which("pipx"):
        print("mcp SDK 없음 + pipx 없음 — 수동: `pipx inject graphifyy mcp` 또는 uv 사용", file=sys.stderr)
        return False
    inj = subprocess.run(["pipx", "inject", "graphifyy", "mcp"], capture_output=True, text=True)
    if inj.returncode != 0:
        print(f"pipx inject 실패:\n{inj.stderr}", file=sys.stderr)
        return False
    return subprocess.run([graphify_py, "-c", "import mcp"], capture_output=True).returncode == 0


_GITIGNORE_LINE = "graphify-out/"

_GRAPHIFYIGNORE = {
    "flutter": "# graphify: 네이티브/벤더 SDK 제외 — god-node 오염 방지\nios/\nandroid/\nbuild/\n.dart_tool/\nnode_modules/\n",
    "node": "# graphify: 벤더/빌드 산출물 제외\nnode_modules/\ndist/\nbuild/\n",
}


def _add_gitignore(project: Path) -> bool:
    """<project>/.gitignore 에 graphify-out/ additive 추가(멱등). 추가했으면 True, 이미 있으면 False."""
    p = project / ".gitignore"
    lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    if any(l.strip().rstrip("/") == "graphify-out" for l in lines):
        return False
    prefix = "" if (not lines or lines[-1] == "") else "\n"
    with p.open("a", encoding="utf-8") as f:
        f.write(f"{prefix}{_GITIGNORE_LINE}\n")
    return True


def _native_mixed(project: Path) -> str | None:
    """네이티브/벤더 혼재 감지 — .graphifyignore 권장 여부. 'flutter'|'node'|None."""
    if (project / "pubspec.yaml").is_file():
        return "flutter"
    if (project / "package.json").is_file():
        return "node"
    return None


def _graphifyignore_scaffold(label: str) -> str:
    """label 별 .graphifyignore 스캐폴드 내용."""
    return _GRAPHIFYIGNORE.get(label, _GRAPHIFYIGNORE["node"])


def _write_graphifyignore(project: Path, content: str) -> bool:
    """.graphifyignore 기록 — 기존 파일 있으면 보존(False), 없을 때만 기록(True)."""
    p = project / ".graphifyignore"
    if p.exists():
        return False
    p.write_text(content, encoding="utf-8")
    return True


# 이 문자열이 멱등 마커다 — 훅 본문에 그대로 들어가며, 재실행 시 「우리 훅인가」 판정에 쓴다.
# (지우면 재실행이 우리 훅을 남의 훅으로 오인해 갱신을 못 한다.)
_HOOK_MARKER = "dw-graphify post-merge hook"

# git pull/merge 후 로컬 코드 그래프를 다시 그리는 post-merge 훅(제네릭 — 프로젝트 종속 금지).
# 설계: 비차단(백그라운드·detached)이라 `git pull` 을 막지 않고, 항상 exit 0 이라 머지를 실패시키지
# 않으며, lock 으로 연속 pull 중복 실행을 막되 stale lock(>60분)은 회수해 크래시 후 영구잠금을 막는다.
_POST_MERGE_HOOK = """#!/bin/sh
# dw-graphify post-merge hook (denver-workflow) — rebuild the local code graph
# after merge/pull so graphify queries stay current. AST-only (no LLM / no API cost).
# Non-blocking: runs detached, logs to graphify-out/.post-merge-graphify.log, and
# NEVER blocks or fails the merge. The comment line above is the idempotency marker.

REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
[ -n "$REPO" ] || exit 0

# graphify usually lives at ~/.local/bin; git hooks may run with a minimal PATH.
GRAPHIFY="$(command -v graphify 2>/dev/null)"
[ -n "$GRAPHIFY" ] || GRAPHIFY="$HOME/.local/bin/graphify"
[ -x "$GRAPHIFY" ] || exit 0

# Only maintain a graph where one already exists (fresh clone / worktree w/o a graph = no-op).
[ -f "$REPO/graphify-out/graph.json" ] || exit 0

LOG="$REPO/graphify-out/.post-merge-graphify.log"
LOCK="$REPO/graphify-out/.post-merge-graphify.lock"

# Reap a stale lock (>60 min) so a crashed run never disables the hook forever.
if [ -d "$LOCK" ] && [ -n "$(find "$LOCK" -maxdepth 0 -mmin +60 2>/dev/null)" ]; then
  rmdir "$LOCK" 2>/dev/null
fi

# Skip if a previous rebuild is still running (avoid pile-ups on rapid pulls).
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "[$(date '+%F %T')] skip: previous graphify update still running" >> "$LOG"
  exit 0
fi

# Detached background rebuild so `git pull` / `git merge` returns immediately.
(
  echo "[$(date '+%F %T')] graphify update start ($REPO)" >> "$LOG"
  "$GRAPHIFY" update "$REPO" >> "$LOG" 2>&1
  echo "[$(date '+%F %T')] graphify update done (exit $?)" >> "$LOG"
  rmdir "$LOCK" 2>/dev/null
) >/dev/null 2>&1 &

exit 0
"""


def _git_out(project: Path, *args: str) -> tuple[int, str]:
    """git 하위명령 실행 → (returncode, stdout.strip())."""
    r = subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def _hooks_dir(project: Path) -> tuple[Path | None, str | None]:
    """(hooks_dir, dead_hookspath). hooks_dir=None → git repo 아님.
    dead_hookspath 는 core.hooksPath 가 설정됐는데 그 경로가 실재하지 않을 때 그 값(경고용)."""
    rc, out = _git_out(project, "rev-parse", "--git-path", "hooks")
    if rc != 0 or not out:
        return None, None
    hd = Path(out)
    if not hd.is_absolute():
        hd = project / hd
    hd = hd.resolve()
    rc2, hp = _git_out(project, "config", "--get", "core.hooksPath")
    dead = hp if (rc2 == 0 and hp and not hd.exists()) else None
    return hd, dead


def _warn_if_inert(project: Path, local_graph: bool) -> None:
    """로컬 그래프가 없으면(vault 폴백) 설치한 훅이 가드로 no-op 임을 알린다.
    설치기는 「설치됨」을 찍지만 훅의 `[ -f graph.json ]` 가 로컬 그래프가 생길 때까지 막는다 —
    이 신호가 없으면 「설치 green」을 「동작함」으로 오독한다(커버리지 0 오독 형태)."""
    if local_graph:
        return
    print("     ⚠️ 단, 이 레포엔 로컬 graphify-out/graph.json 이 없다(그래프는 vault 폴백).")
    print("        훅은 `[ -f graph.json ]` 가드로 로컬 그래프가 생길 때까지 no-op 이다 —")
    print(f"        `graphify update {project}` 로 로컬 그래프를 먼저 빌드해야 동작한다.")


def _install_post_merge_hook(project: Path, do_install: bool, local_graph: bool = True) -> None:
    """post-merge git 훅을 설치(do_install)하거나 제안(미설치)한다. 절대 예외를 던지지 않는다.

    정책(제네릭 도구): core.hooksPath 가 죽은 경로면 **경고+스킵**(남의 config 를 unset 하지 않는다).
    기존 post-merge 가 우리 마커를 가지면 갱신, 남의 훅이면 경고+스킵(덮지 않는다)."""
    hd, dead = _hooks_dir(project)
    if hd is None:
        return  # git repo 아님 — 배선할 게 없다
    if dead is not None:
        print(f"\n[주의] core.hooksPath 가 실재하지 않는 경로를 가리켜 git 훅이 전부 비활성이다: {dead}")
        print("       (post-merge 를 어디에 설치해도 git 이 부르지 않는다) 고치려면:")
        print(f"         git -C {project} config --unset core.hooksPath")
        print("       그 뒤 --post-merge-hook 로 재실행하면 설치된다.")
        return
    hook = hd / "post-merge"
    if hook.exists():
        content = hook.read_text(encoding="utf-8", errors="ignore")
        if _HOOK_MARKER in content:
            if do_install:
                hook.write_text(_POST_MERGE_HOOK, encoding="utf-8")
                hook.chmod(0o755)
                print("  post-merge 훅: 이미 설치됨 — 최신 내용으로 갱신(멱등).")
                _warn_if_inert(project, local_graph)
            else:
                print("  post-merge 훅: 이미 설치됨(멱등).")
            return
        print(f"\n[주의] 기존 post-merge 훅이 있어 건드리지 않는다: {hook}")
        print('       graphify 자동 갱신을 원하면 그 훅에 `graphify update "$(git rev-parse --show-toplevel)"` 를 직접 추가하라.')
        return
    if not do_install:
        print("\n[제안] git pull/merge(원격 변경 내려받기·합치기) 후 로컬 그래프를 자동으로 다시 그리려면")
        print("       post-merge 훅을 설치할 수 있다 — 비차단(git 을 안 막음)·AST 전용(비용 0).")
        print("       설치하려면 --post-merge-hook 로 재실행.")
        return
    hd.mkdir(parents=True, exist_ok=True)
    hook.write_text(_POST_MERGE_HOOK, encoding="utf-8")
    hook.chmod(0o755)
    print(f"  post-merge 훅 설치: {hook}")
    print("     → 앞으로 git pull/merge 후 graphify 그래프가 백그라운드로 자동 갱신된다(비차단).")
    _warn_if_inert(project, local_graph)


def main() -> int:
    ap = argparse.ArgumentParser(description="graphify MCP 서버를 프로젝트 .mcp.json 에 등록")
    ap.add_argument("--project", required=True)
    ap.add_argument("--graph", default="")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--graphifyignore", action="store_true",
                    help="네이티브 혼재 레포에 .graphifyignore 스캐폴드 기록(옵트인)")
    ap.add_argument("--post-merge-hook", action="store_true",
                    help="git pull/merge 후 로컬 그래프를 자동 갱신하는 post-merge 훅 설치(옵트인)")
    args = ap.parse_args()

    project = Path(args.project).expanduser().resolve()
    if not project.is_dir():
        print(f"에러: 프로젝트 폴더 없음 — {project}", file=sys.stderr)
        return 1
    py, graph = detect(project, args.graph or None)
    if py is None:
        print("graphify 미감지(CLI 또는 graph.json 없음) — 등록 스킵.")
        return 0
    print(f"graphify python: {py}\ngraph.json: {graph}\n대상 .mcp.json: {project/'.mcp.json'}")
    # 로컬 그래프가 없으면 detect 가 vault 그래프로 폴백한 것 — 그 경우 훅은 가드로 no-op 이다.
    local_graph = (project / "graphify-out" / "graph.json").is_file()
    # 훅만 설치(--post-merge-hook 단독, --apply 없음): 워크스페이스-레벨 graphify 를 쓰는 레포는
    # per-repo .mcp.json 이 필요 없다(단일 서버 + project_path 라우팅). MCP 등록을 건너뛰고 훅만 건다.
    if args.post_merge_hook and not args.apply:
        _install_post_merge_hook(project, True, local_graph)
        return 0
    if not args.apply:
        print("\n(dry-run — 적용하려면 --apply. post-merge 훅만 설치하려면 --post-merge-hook)")
        return 0
    if not _ensure_mcp(py):
        return 1
    data = merge_mcp_json(project, py, graph)
    (project / ".mcp.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n등록 완료. 새 세션부터 graphify 도구 노출 — 확인: claude mcp list | grep graphify")
    # git 위생: graphify-out/ 산출물 커밋 방지(additive·멱등)
    if _add_gitignore(project):
        print(f".gitignore 에 {_GITIGNORE_LINE} 추가.")
    # post-merge 훅: git pull/merge 후 로컬 그래프 자동 갱신(--post-merge-hook 없으면 제안만)
    _install_post_merge_hook(project, args.post_merge_hook, local_graph)
    # 네이티브 혼재: .graphifyignore 제안(옵트인 기록)
    label = _native_mixed(project)
    if label:
        if args.graphifyignore and _write_graphifyignore(project, _graphifyignore_scaffold(label)):
            print(f".graphifyignore 스캐폴드 기록({label}).")
        elif not args.graphifyignore:
            print(f"\n[제안] {label} 네이티브 혼재 감지 — god-node 오염 방지용 .graphifyignore 권장:")
            print(_graphifyignore_scaffold(label).rstrip())
            print("기록하려면 --graphifyignore 로 재실행.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
