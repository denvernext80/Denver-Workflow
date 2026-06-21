#!/bin/sh
# ssot-vault MCP 자가 부트스트랩 런처 (플러그인 설치 환경용).
# 플러그인은 GitHub 에서 설치돼 .venv 가 없으므로(gitignored), 첫 실행 시 venv 를 만들고
# pyyaml·mcp 를 설치한 뒤 서버를 exec 한다. 이후 실행은 기존 venv 재사용(멱등).
# 도구(.venv·서버 스크립트)는 플러그인 루트(ROOT)에 산다.
# vault 콘텐츠 위치 해석 순서: DENVER_VAULT_DIR(env) > ~/denver-agent-vault(규약 경로) > 에러.
#   - 기본(규약): ~/denver-agent-vault. 'make scaffold-vault' 로 생성. 별도 env 설정 불요.
#   - 커스텀 위치: DENVER_VAULT_DIR 를 원하는 절대경로로 설정. 공백 포함 경로 안전(따옴표).
#     예: export DENVER_VAULT_DIR="$HOME/My Vaults/denver"
#   - vault 폴더 자체가 없으면 런처는 exit 1 (플러그인 루트 폴백 없음).
set -e
ROOT="${CLAUDE_PLUGIN_ROOT:-$(CDPATH= cd "$(dirname "$0")/.." && pwd)}"
# vault 해석: 명시 env > 고정 규약 경로 > 에러 (cache ROOT 폴백 제거 — vault 필수)
CONV="$HOME/denver-agent-vault"
if [ -n "$DENVER_VAULT_DIR" ] && [ -d "$DENVER_VAULT_DIR" ]; then
  VAULT="$DENVER_VAULT_DIR"
else
  [ -n "$DENVER_VAULT_DIR" ] && echo "denver-agent: DENVER_VAULT_DIR='$DENVER_VAULT_DIR' 폴더 없음 — 규약 경로 시도" >&2
  if [ -d "$CONV" ]; then
    VAULT="$CONV"
  else
    echo "denver-agent: vault 없음 ($CONV). 'make scaffold-vault' 로 생성하거나 DENVER_VAULT_DIR 설정." >&2
    exit 1
  fi
fi
VENV="$ROOT/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV" >&2
  "$VENV/bin/pip" install --quiet --upgrade pip >&2
  "$VENV/bin/pip" install --quiet pyyaml mcp >&2
fi
exec "$VENV/bin/python" "$ROOT/_build/ssot-mcp-server.py" --vault "$VAULT"
