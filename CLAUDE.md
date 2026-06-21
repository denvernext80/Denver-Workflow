# denver-workflow 워크스페이스 — 멀티레포 오케스트레이터 + denver-agent 플러그인·빌드 도구

이 디렉토리는 **단일 세션 멀티레포 오케스트레이터**이자 **denver-agent 플러그인·빌드 도구 본체**다.
여기서 세션을 띄워 여러 레포를 가로질러 작업한다. **vault(SSOT) 콘텐츠는 분리돼
`~/denver-agent-vault`(고정 규약 경로)에 산다** — MCP 런처가 그 규약 경로를 자동 해석한다
(`DENVER_VAULT_DIR` env > `~/denver-agent-vault` > 에러; Makefile `VAULT_DIR` 기본도 규약 경로).
도구(`.venv`·`_build`·`hooks`)만 이 워크스페이스에 잔류.

> 단일 세션이 자동화 불가하던 레포별 분리 작업을 대체한다. 지식 공유는 vault(`ssot-vault` MCP,
> 플러그인 `plugin.json` 제공 `plugin:denver-agent:ssot-vault` — root 무관, 모든 세션 자동 노출)로,
> 작업 분배는 repo-pinned 서브에이전트 디스패치로 푼다.

## 세션 기본 에이전트 = `ssot-orchestrator`

실질 작업은 **분류 → 대상 레포 do-er 에게 repo-pinned Task 디스패치 → 대상 레포 checks 로
게이트**한다. 직접 깊게 파지 말고 위임하되, 완료 게이트 책임은 오케스트레이터에 있다.
(단일 레포 단독 세션은 각 레포의 `ssot-governed` 를 쓴다 — 이 워크스페이스는 멀티레포 전용.)

## 레포 맵

레포·절대경로·do-er·스택·checks 는 **세션 digest 의 "## 레포 맵 (라우팅)"**(vault `project/repo-map.md`
정본)을 따른다. 여기 복제하지 않는다(단일 출처).

## 불변식 (디스패치·게이트)

1. **repo-pinned 디스패치** — Task 는 re-root 불가. do-er 프롬프트에 대상 레포 **절대경로** +
   "그 레포의 `<repo>/.claude/ssot-checks.json` 로 검사하라" 를 명시한다.
2. **게이트는 대상 레포 checks** — 워크스페이스 union checks 가 아니라 **대상 레포의**
   ssot-checks.json + `enforced-by` 검증자로 완료를 재검증. green 전 완료 선언 금지.
3. **교차레포 계약 = vault `contracts/` 단일 SSOT** — `ssot_read` → 합의 → 공급·소비측 순차
   디스패치 → `ssot_write_contract`. 계약 요청 전 상대 레포 현 코드 직접 실측.
4. **레포별 워크플로우 분기** — git/PR/deploy 규율이 레포마다 다르다. do-er 에게 해당 레포
   규율을 따르게 하고, 머지·배포 게이트(마이그레이션·시크릿·authz·데이터 손실)는 사용자 동의.

## vault(SSOT) — 이 repo 자체

- 규칙·가이던스: 컴파일된 union 스킬 + SessionStart 다이제스트(자동 주입).
- 계약·메모리·스펙(LIVE): `ssot-vault` MCP 8 도구(`ssot_search`/`ssot_read`/`ssot_write_*`).
- vault 저작·빌드: `make build`·`make install-orchestrator`. 산출물(`.claude/skills`·`agents`)
  **직접 편집 금지** — vault 소스를 고친 뒤 재빌드. 설계·운영은 `README.md`·`BOOTSTRAP.md`.

## 세부 규율

각 레포의 상세 규칙은 do-er 가 자기 레포의 컴파일된 스킬 + 다이제스트로 적용한다. 이 문서는
**라우팅·게이트만** 담는다(거대 per-repo CLAUDE.md 를 여기 복제하지 않는다 — 토큰 규율).
