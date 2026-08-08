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


def main() -> int:
    ap = argparse.ArgumentParser(description="graphify MCP 서버를 프로젝트 .mcp.json 에 등록")
    ap.add_argument("--project", required=True)
    ap.add_argument("--graph", default="")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--graphifyignore", action="store_true",
                    help="네이티브 혼재 레포에 .graphifyignore 스캐폴드 기록(옵트인)")
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
    if not args.apply:
        print("\n(dry-run — 적용하려면 --apply)")
        return 0
    if not _ensure_mcp(py):
        return 1
    data = merge_mcp_json(project, py, graph)
    (project / ".mcp.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n등록 완료. 새 세션부터 graphify 도구 노출 — 확인: claude mcp list | grep graphify")
    # git 위생: graphify-out/ 산출물 커밋 방지(additive·멱등)
    if _add_gitignore(project):
        print(f".gitignore 에 {_GITIGNORE_LINE} 추가.")
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
