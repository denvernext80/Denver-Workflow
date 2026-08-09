# 계측·토큰비용 설계 문서 (2026-08-07)

2026-08-07 클라우드 세션이 로컬로 넘긴 **구현 지시 패키지**의 설계 문서다. 원본은 레포 루트의
`_dw-instrumentation/`(untracked)에 있었고, 지시가 전부 소진된 뒤 **왜 그렇게 만들었는지의 근거**만
여기 남겼다. 같이 있던 스크립트 5개는 `_build/` 최신본에 밀린 구버전이라 삭제했다(아래 참조).

> 이 문서들은 **당시의 지시서**다 — 현재 동작의 정본이 아니다. 실제 규율은 vault
> `governance/`(→ `dev-engineering-charter` 스킬)와 `_build/` 코드가 정본이다.

## 문서별 상태

| 문서 | 내용 | 반영 상태 |
| --- | --- | --- |
| `…워크플로우-최적화-구현지시…` | ① 워크플로우 텔레메트리(PostToolUse) ② SSOT 쓰기 가드(PreToolUse) ③ graphify 하드 게이트 | **완료** — `_build/` + `hooks/hooks.json` 배선 |
| `…검증자→결정론-check-전환-batch1-구현지시…` | 검증자 전용 규칙 5개에 grep check 추가(레버 A) | **완료** — vault 규칙의 check 보유 8 → 14개 |
| `…결정론-check-batch1-확정결과-실측…` | 위 패턴의 오탐 0 + non-vacuity 실측 결과 | **완료**(위와 한 쌍) |
| `…검증자-advisor-토큰비용-해결계획-레버-abc…` | 레버 A(check 전환)·B(검증자 relevance-gate)·C(advisor 호출 규율) | A **완료** · B **완료**(2.18.0) · C **미착수** |

## 여기서 남은 일 — 레버 C

`advisor` 호출 규율(확립·검증된 레인엔 advisor 를 건너뛴다)만 아직 guidance 로 승격되지 않았다.
문서가 정한 순서는 "guidance 반영 → 텔레메트리로 2~4주 관측 → 호출 정책 조정" 이다.

## 왜 스크립트를 지웠나

원본 패키지에 있던 5개 중 `dw-workflow-report.py`·`dw_access_log.py` 는 `_build/` 와 동일했고,
`dw-telemetry.py`·`dw-vault-write-guard.py`·`dw-graphify-gate.py` 는 **2.16.0 의 `dw_runtime` vault
해석 통합 이전** 사본이었다(각자 자기 vault 해석 사본을 들고 있던 그 시절 코드). 삭제 전
상위집합 여부를 확인했다 — `dw-vault-write-guard` 의 guidance 안내 문구는 `_build` 에 더 정확하게
남아 있고, `dw-graphify-gate` 의 `_graphify_registered` 는 `_build` 에서 조상 디렉토리까지 훑는
`_mcp_has_graphify` + `_graphify_applicable` 로 확장됐다. 즉 잃은 동작은 없다.
