#!/usr/bin/env bash
# GitHub Actions self-hosted 러너의 job-completed 훅 — 잡 종료마다 누수된 익명 docker 볼륨을 회수한다.
#
# 왜: CI 의 `services:` 컨테이너(예: postgres·redis)는 VOLUME 을 선언한다. self-hosted 러너는
#     잡 종료 시 컨테이너를 `docker rm`(WITHOUT -v)만 하고 익명 볼륨은 남긴다 → 매 잡마다 누수.
#     실측(2026-09): 한 self-hosted 러너 VM 의 docker-in-docker 에 미사용 익명 볼륨 4,652개 =
#     362.7GB 누적, 그 결과 디스크 이미지가 394G→46G 로 폭증했다.
#
# 배선: 러너 `.env` 의 `ACTIONS_RUNNER_HOOK_JOB_COMPLETED=<이 스크립트 절대경로>` 로 지정된다.
#       러너는 각 잡이 끝난 뒤 이 스크립트를 실행하고, 다음 잡을 받기 전에 완료를 기다린다.
#       (설치 배선: 플러그인 `_build/dw-wire-ci-runners.py` — `/dw-install` 과 별도의 명시적 실행.)
#
# 안전성(비타협):
#   - `docker volume prune -f` 는 **어느 컨테이너에도 붙어있지 않은** 익명 볼륨만 지운다.
#     동시 실행 중인 다른 잡의 활성 서비스 볼륨은 살아있는 컨테이너에 붙어 있으므로 건드리지 않는다.
#     (docker server 29.x 실측 — v23+ 에서 `volume prune` 은 dangling 익명 볼륨만 대상.
#      🔴 구버전(<23) daemon 은 미사용 «네이밍» 볼륨까지 지우니, daemon 강등 시 재검토하라.)
#   - `--volumes`/`-a` 전삭제는 **절대 하지 않는다**. 볼륨만, dangling 만.
#   - **비차단**: 잡 결과에 영향 주지 않는다. docker 부재·prune 실패·행(hang) 어느 경우든 `exit 0`.
#   - `timeout` 으로 감싼다 — 러너는 이 훅이 끝나야 다음 잡을 받으므로, docker daemon 이 행하면
#     이 가드가 없으면 러너 자체가 멈춘다.
set -u

log() { printf '[dw-prune-hook] %s\n' "$*"; }

# docker 없으면 조용히(성공) 종료 — 이 러너는 docker 를 안 쓰는 것이다(예: 모바일 빌드 러너).
if ! command -v docker >/dev/null 2>&1; then
  log "docker 없음 — 정리 건너뜀"
  exit 0
fi

# 익명(dangling) 볼륨 회수. timeout 으로 행 방지, 실패해도 잡 결과 불변.
log "docker volume prune -f (익명 볼륨만; 활성 서비스 볼륨은 안전)"
if timeout 120 docker volume prune -f 2>&1; then
  :
else
  log "prune 비정상 종료(무시) — 잡 결과에 영향 없음"
fi

# 선택: dangling 이미지 회수(untagged 레이어만). 기본 OFF — DW_PRUNE_IMAGES=1 일 때만.
# 이유: 394G→46G 폭증의 주동인은 볼륨이었다. 이미지 prune 은 별개 축이라 옵트인으로 둔다.
if [ "${DW_PRUNE_IMAGES:-0}" = "1" ]; then
  log "docker image prune -f (dangling 이미지만; DW_PRUNE_IMAGES=1)"
  timeout 120 docker image prune -f 2>&1 || log "image prune 비정상 종료(무시)"
fi

exit 0
