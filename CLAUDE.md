# denver-workflow — 팀 공용 Claude Code 워크플로우 플러그인 (개발 프로젝트)

이 디렉토리는 **denver-workflow 플러그인의 소스·빌드 도구 본체**다. 팀원은 이 레포를
플러그인으로 설치해 쓰고, 여기서는 플러그인 자체를 개발·빌드·배포한다.

- **vault(팀 지식 폴더) 콘텐츠는 이 레포에 없다** — 각 사용자의 `~/denver-workflow-vault`
  (규약 경로, `DW_VAULT_DIR` env 로 오버라이드)에 산다. `_seed/` 는 그 초기 구조(범용)만 담는다.
- **네이밍 규칙: `dw-*`** — 에이전트(dw-governed·dw-orchestrator·dw-ratifier), 커맨드(/dw-setup·
  /dw-build·/dw-install·/dw-ratify·/dw-review·/dw-scope), MCP 서버(dw-vault)·도구(dw_*), 산출물
  (.claude/dw-checks.json 등). 새 이름을 만들 때도 `dw-` 접두를 따른다.
- **특정 프로젝트 종속 금지** — 스킬·에이전트·스크립트·문서 어디에도 특정 서비스/프로젝트
  키워드를 넣지 않는다(범용 seed 원칙).
- **사용자 문구 원칙** — 사용자 노출 문구는 전문용어(짧은 쉬운 설명) 병기. 비개발직군이 대상.
- 산출물(`.claude/skills`·`agents` 등) **직접 편집 금지** — `_seed/` 또는 vault 소스를 고친 뒤
  재빌드(`make build`, `/dw-build`). 설계·운영 상세는 `README.md`·`BOOTSTRAP.md`.
- 검증: `make dry-run`(strict 컴파일)·`make seed-check`·`make doctor`. pytest 없음 — grep·
  dry-run·스크립트 직접 실행으로 검증한다.
