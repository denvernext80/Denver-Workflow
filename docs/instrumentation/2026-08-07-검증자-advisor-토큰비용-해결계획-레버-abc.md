# 검증자·advisor 디스패치 토큰 비용 — 해결 계획

## 비용 모델 (측정 기반)
- 활성 규칙 55개 중 **grep 결정론 검사(check-deny/require) 보유는 8개(15%)**. 나머지 47개는
  검증자 서브에이전트로만 강제 — enforced-by: code-review 38 · design-review 12 · security-qa 7.
- 검증자는 무거운 서브에이전트다(diff 통째 추론 + 규칙 로드). **관련 없어도 판단으로 디스패치**됨.
- 여기에 **advisor** role(요구사항 `brainstorming+advisor`, 블로커 에스컬레이션)까지 겹쳐 작업당
  서브에이전트 토큰이 커진다.

핵심: 토큰은 **① 관련 없는 검증자 디스패치**, **② 검증자당 큰 규칙 로드**, **③ advisor 상시 호출**
에서 샌다. 세 레버로 각각 친다.

---

## 레버 B — 검증자 relevance-gate (즉시·안전, 구현 완료)
바뀐 파일이 그 검증자 도메인에 **없으면 아예 안 부른다.** 어떤 규칙도 약화하지 않는다(리뷰할 게
0인 검증자를 스킵할 뿐). `_build/dw-verifier-scope.py` (검증됨):
- 백엔드만(php/migration) → design-review **스킵**
- 순수 UI(dart/home-frontend/css) → security-qa **스킵**
- 문서/설정만(*.md, docs, lock, 이미지) → **전부 스킵**
- 보안-민감 파일명(*auth*·*token*·*sql*·*session* …)일 때만 security-qa

**기대 절감**: 백엔드-집중/프론트-집중/문서 작업에서 검증자 1~3개를 제거 → 검증자 디스패치의
상당 비율 컷(enforcement 손실 0).

### 배선
오케스트레이터/dw-governed 의 "검증자 호출(step 4)" 직전에 실행하고, **반환된 검증자만** 디스패치:
```bash
python _build/dw-verifier-scope.py --repo <repo> --base <base>   # 또는 --files -
# dispatch: [...] 에 있는 것만 Agent 로 호출. skip 은 부르지 않는다.
```
guidance 로 못박을 것(초안): "완료 게이트에서 enforced-by 검증자는 `dw-verifier-scope` 가 반환한
집합으로 한정한다. 반환 밖 검증자는 디스패치 금지(리뷰 대상 0)."
※ dispatcher 가 이 스크립트를 부르도록 guidance 로 강제 — 조언 무시가 걱정되면 completion-gate
스크립트(dw-checks 흐름)에 포함해 결정론화.

---

## 레버 A — grep 가능 규칙을 결정론 check 로 전환 (검증자 부하 축소)
검증자당 규칙 수를 줄이고(프롬프트↓) 단순 위반을 공짜로 잡는다. 각 전환은 **non-vacuity 테스트
필수**(사용자님 규칙: "0건을 성공으로 보고 금지" — known-positive 매치 + 오탐 0 실측 후 stable).

**전환 후보(batch 1, 고신뢰 — 각 패턴은 balipick/balipick-app 로 테스트 후 확정):**
| 규칙 | 검사 유형 | 패턴(초안) |
|---|---|---|
| Pretendard 한 벌만 | deny | `fontFamily:\s*['\"](?!Pretendard)` (dart/css) |
| 색 토큰 사각지대(Colors.white/black·fromRGBO/fromARGB 금지) | deny | `Colors\.(white|black)|Color\.froma?RGBO?\(` |
| GA4 예약어 파라미터 금지 | deny | `['\"](source|medium|campaign)['\"]\s*=>` (분석 emit) |
| docker compose 프로젝트명 balipick 고정 | require | `name:\s*balipick` (docker-compose.yml) |
| 인증 쿠키 플래그 | require | `HttpOnly` & `Secure` & `SameSite` (setcookie 근처) |
| 토큰은 보안 스토리지에만 | deny | `SharedPreferences[^;]*token` (dart) |
| 빈 콜백 삼킴 금지(()=>null) | deny | `=>\s*null\b` (콜백 컨텍스트) |

**검증자로 남길 것(구조적 — grep 불가):** 계층 경계, 계약 additive/envelope, 공유서비스 재구현,
사용자 데이터 스코핑, 테스트 약화 탐지, mounted 가드(문맥 의존), CI-green·머지 규율(프로세스).

---

## 레버 C — advisor 호출 규율 (상시 호출 억제)
advisor 는 파일-글롭 대상이 아니다(role). 레버는 **호출 시점 축소**다. 사용자님은 이미 시작했다 —
"ad-hoc 앱 배포는 advisor 확인 없이 진행" 규칙. 이를 일반 원칙으로 승격:

guidance 초안: "advisor 는 (a) 요구사항이 실제로 모호하거나, (b) 확립된 레인이 없는 새 문제, (c)
비가역·고위험 결정에서만 호출한다. **확립·검증된 레인·자명한 작업엔 advisor 를 건너뛴다.**"
→ 그리고 ① 텔레메트리에 advisor 디스패치를 기록해 **호출 빈도 대비 결정 변경률**을 관측, 월세 안
내는 호출을 데이터로 잘라낸다.

---

## 실행 순서
1. **레버 B 먼저**(안전·즉효, enforcement 무손실) — dw-verifier-scope 배선 + guidance.
2. **레버 A batch 1**(고신뢰 7개) 패턴을 balipick/balipick-app 로 non-vacuity 테스트 후 규칙
   frontmatter 에 추가 → `make build` 로 dw-checks 컴파일.
3. **레버 C** guidance + 텔레메트리 advisor 기록 → 2~4주 관측 후 호출 정책 조정.
4. ① 텔레메트리로 검증자·advisor 디스패치 빈도를 **전후 비교**해 절감 실측.
