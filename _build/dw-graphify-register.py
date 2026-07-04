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
import argparse, json, os, shutil, subprocess, sys
from pathlib import Path


def _expand(p: str) -> str:
    """런처 규약과 동일하게 리터럴 ~/ · $HOME/ 접두 확장."""
    p = p.strip()
    if p.startswith("~/"):
        return str(Path.home() / p[2:])
    if p.startswith("$HOME/"):
        return str(Path.home() / p[6:])
    return p


def _resolve_vault(project: Path) -> Path:
    """vault 루트 해석 — dw-config.json vault_root > DW_VAULT_DIR env > 규약 ~/denver-workflow-vault
    (dw-mcp-launch.sh 와 동일 순서)."""
    cfg = project / ".claude" / "dw-config.json"
    if cfg.exists():
        try:
            vr = json.loads(cfg.read_text(encoding="utf-8")).get("vault_root")
            if vr:
                return Path(_expand(vr))
        except (OSError, json.JSONDecodeError):
            pass
    env = os.environ.get("DW_VAULT_DIR")
    if env:
        return Path(_expand(env))
    return Path.home() / "denver-workflow-vault"


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
    vault_graph = _resolve_vault(project) / "graphify-out" / "graph.json"
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


def main() -> int:
    ap = argparse.ArgumentParser(description="graphify MCP 서버를 프로젝트 .mcp.json 에 등록")
    ap.add_argument("--project", required=True)
    ap.add_argument("--graph", default="")
    ap.add_argument("--apply", action="store_true")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
