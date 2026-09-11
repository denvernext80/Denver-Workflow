#!/usr/bin/env bash
# /etc/resolv.conf 를 로컬 unbound(127.0.0.1)로 재지정 — OrbStack 재생성에 대한 «재무장».
#
# 왜: OrbStack 게스트는 /etc/resolv.conf 를 읽기전용 심링크
#     (→ /opt/orbstack-guest/etc/resolv.conf, `nameserver 0.250.250.200`)로 관리하고 **VM 부팅마다
#     재생성**한다. serve-stale 리졸버(unbound)를 배선해도 부팅 후 심링크가 프록시로 되돌아가면
#     CI 가 다시 프록시 직결이 된다. 이 스크립트가 부팅 시(systemd oneshot) + 배선 시(wire 스크립트)
#     멱등 재지정한다.
#
# 안전(비타협): 127.0.0.1 뒤에 **0.250.250.200 을 폴백 nameserver 로 남긴다**. unbound 가 죽어
#     127.0.0.1:53 이 ECONNREFUSED 면 glibc resolver 가 다음 서버(프록시)로 폴백한다 — 최악의
#     경우에도 DNS 는 종전(프록시) 동작으로 degrade 될 뿐 «전면 중단»되지 않는다. 블립 때는
#     unbound 가 살아 serve-stale 하므로 폴백이 발동하지 않는다(폴백은 unbound 자체가 죽은
#     경우에만).
#
# 멱등: 목표 내용과 현재가 같고 심링크가 아니면 no-op(SKIP). 다르면 원자적 교체(mktemp+mv 동일 fs).
set -u

RESOLV=/etc/resolv.conf

# 목표 내용을 함수로 두 곳(비교·쓰기)에서 동일 소스로 방출한다 — search/options 는 종전
# OrbStack 값 보존(실측: `options edns0`, `search .`). 함수+`$()` 로 «쓰기와 비교가 같은
# 텍스트»를 보장(하드코딩 문자열/heredoc 이중관리로 인한 스퓨리어스 미스매치 방지).
emit_target() {
  cat <<'EOF'
# Managed by denver-workflow wire-ci-runners (serve-stale resolver re-arm). Do not edit.
nameserver 127.0.0.1
nameserver 0.250.250.200
options edns0
search .
EOF
}

log() { printf '[dw-resolv-repoint] %s\n' "$*"; }

# 이미 정확하고 심링크가 아니면 아무 것도 안 한다. `$()` 는 양쪽 후행개행을 대칭 제거하므로
# 멱등 비교가 성립한다(쓰기는 아래에서 emit_target 그대로 → 다음 실행에서 SKIP).
if [ ! -L "$RESOLV" ] && [ -f "$RESOLV" ] && [ "$(cat "$RESOLV" 2>/dev/null)" = "$(emit_target)" ]; then
  log "SKIP — 이미 127.0.0.1 로 지정됨"
  exit 0
fi

tmp="$(mktemp /etc/.resolv.dw.XXXXXX)" || { log "mktemp 실패"; exit 1; }
emit_target > "$tmp"
chmod 644 "$tmp"
# 심링크 제거 후 원자적 교체(같은 /etc fs 이므로 mv 는 rename = atomic).
rm -f "$RESOLV"
mv "$tmp" "$RESOLV"
log "재지정 완료 — nameserver 127.0.0.1 (폴백 0.250.250.200)"
exit 0
