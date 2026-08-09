# 레버 A batch-1 — 결정론 check 확정 결과 (실측 완료)

balipick / balipick-app 실코드에 직접 grep + 합성 non-vacuity 로 검증. **오탐 0 + 위반 포착**을
통과한 것만 확정. 통과분을 해당 규칙 frontmatter 에 추가 → `make build` 로 dw-checks.json 컴파일하면
검증자 없이 공짜로 강제되고, 그 규칙은 검증자 인지부하에서 빠진다.

## ✅ 통과 5건 (규칙 frontmatter 에 추가)

### #1 Pretendard 한 벌만 (design-pretendard-only.md)
검증: 현재 fontFamily 4곳 전부 'Pretendard'(클린). Python-re lookahead 로 Roboto/SF Pro 는 deny,
Pretendard 는 통과 확인. ⚠️ lookahead 는 **Python-re 검사기(dw-lint)** 에서만 — 리터럴 grep 아님.
```yaml
check-deny: ['fontFamily\s*:\s*['']"](?!Pretendard)']
check-glob: ['lib/**/*.dart']
check-hint: 'fontFamily 는 Pretendard 만 (app_theme _textTheme 경유)'
```
> YAML 주의: 위 char-class 는 작은따옴표 이스케이프가 까다롭다. 안전형(둘째따옴표만):
> `check-deny: ["fontFamily\\s*:\\s*[\"'](?!Pretendard)"]`

### #2 색 사각지대 (색-토큰-검사-사각지대-봉쇄--…-deny.md)
검증: 현재 매치 1건 = 규칙이 문서화한 예외(weather_node_map 알파-캐리어). 경로 제외 시 오탐 0.
합성: Colors.white·Color.fromARGB 매치, Colors.transparent·BalipickColors 미매치.
```yaml
check-deny: ['Colors\.(white|black)\b', 'Color\.from(RGBO|ARGB)\(']
check-glob: ['lib/**/*.dart']
check-exclude: ['lib/core/theme/balipick_colors.dart', 'lib/features/weather/presentation/widgets/weather_node_map.dart']
check-hint: 'BalipickColors 토큰만. transparent 허용. 알파-캐리어 예외는 weather_node_map 제외'
```

### #3 GA4 예약어 source 금지 (…-ga4-예약어-…-금지-….md) — 규칙에 이미 명시된 정규식 재확인
검증: 현재 트리 **0건**(오탐 없음). 합성 `bpTrack('spot_rate',{…source:'x'})` 매치, 비트래킹
`useDayPlanDrag({source:…})` 미매치. ⚠️ multiline/DOTALL 필요(규칙 명기) — dw-checks 컴파일 시 플래그 확인.
```yaml
check-deny: ['(?:bpTrack|track)\s*\(\s*['']"][a-z0-9_]+['']"]\s*,\s*\{(?:[^{}]|\{[^{}]*\})*?[\s,{]source\s*:']
check-glob: ['*.ts', '*.tsx', '*.js', '*.phtml']
check-exclude: ['node_modules/*', 'vendor/*', 'public/new-app/*', '*__tests__*']
```

### #4 docker 프로젝트명 balipick 고정 (…-compose-프로젝트명-balipick-고정.md)
검증: dev-up.sh:17 `export COMPOSE_PROJECT_NAME=balipick` 존재(require 충족=클린). 없어지면 위반.
```yaml
check-require: ['COMPOSE_PROJECT_NAME\s*=\s*balipick']
check-glob: ['infra/scripts/dev-up.sh']
check-hint: 'dev-up.sh 는 COMPOSE_PROJECT_NAME=balipick 고정 (워크트리명 사용 금지)'
```
> 부분 커버: dev-up.sh 불변식만. "워크트리별 오버라이드 스택 신설 금지"는 여전히 리뷰 판단.

### #6 토큰은 보안 스토리지에만 (mobile-secure-token-storage.md)
검증: lib/core/storage 는 FlutterSecureStorage 만, SharedPreferences 0건(클린). 토큰 저장 경로 봉쇄.
```yaml
check-deny: ['SharedPreferences']
check-glob: ['lib/core/storage/*.dart']
check-hint: '토큰 저장 계층에 SharedPreferences 금지 — FlutterSecureStorage/TokenStore 만'
```
> 좁은 가드(정본 파일 봉쇄). 다른 위치의 신규 토큰-in-prefs 는 security-qa 가 계속 커버.

---

## ❌ 탈락 2건 (검증자 유지 — grep 으로 안전 전환 불가)

### #7 빈 콜백 삼킴 — **주석 오탐**
현재 4매치 중 **3건이 주석**(팀이 안티패턴을 문서로 설명 — `// \`?? () {}\` 는…`). grep 은 코드/주석
구분 불가 → 오탐 3건, "오탐 0" 기준 미달. 실제 **코드 위반 1건**: `spot_reviews.dart:200
onTap: _loading ? () {} : _loadMore` (수정 대상). → **code-review 유지**(또는 AST 검사 필요).

### #5 인증 쿠키 플래그 — **의미 규칙**
플래그가 `$opts` 변수에 담겨 setcookie 라인엔 안 나타남. 인증 쿠키(bp_at/bp_rt) 발급부를 단순 grep
으로 특정 불가(cookieOpts 미검출). 플래그 존재·경로·중앙화는 문맥 판단. → **security-qa 유지**.

---

## 발견된 실위반 (별도 수정)
- `spot_reviews.dart:200` — `onTap: _loading ? () {} : _loadMore` (#7 실코드 위반 1건).
- `weather_node_map.dart:593` — `Color.fromRGBO(0,0,0,…)` (#2 문서화된 허용 예외 — 제외 처리).

## 적용
1. 위 5개 블록을 각 규칙 frontmatter 에 추가(worktree/브랜치).
2. `make build` → dw-checks.json 재컴파일 → `make dry-run`·`make doctor`.
3. dw-ratifier 가 check-vs-기존코드 대조: #1~#4·#6 은 0매치(클린) → 자동 stable 유지.
4. #7 실위반 1건 수정은 별도 태스크(senior-mobile).
