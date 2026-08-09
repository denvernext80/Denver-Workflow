# 구현 지시: 검증자→결정론 check 전환 batch-1 (규칙 5개)

> 로컬 Claude Code 에서 실행. 대상은 **vault 레포**(`~/Documents/denver-workflow-vault`) 의 규칙
> frontmatter. 목적: 검증자 전용이던 5개 규칙에 grep 결정론 check 를 추가해 검증자 인지부하·토큰을
> 줄인다. 아래 패턴은 balipick/balipick-app 실코드로 **오탐 0 + non-vacuity 검증 완료**(2026-08-06).

## 규율
- vault 레포에 **worktree + 브랜치**(main 직행 금지). 편집 후 컴파일·검증 green 이어야 완료.
- 마감에 학습을 `dw_write_memory` draft 기록.

## 0단계 — worktree
```bash
cd ~/Documents/denver-workflow-vault
git worktree add -b dw/checks-batch1 .worktrees/checks-batch1 main   # (레포 관례 경로에 맞게 조정)
cd .worktrees/checks-batch1
```

## 1단계 — 5개 규칙 frontmatter 에 check 추가
각 파일의 **frontmatter(--- 블록) 안에** 아래 줄들을 추가한다(기존 필드 유지, `enforced-by` 도 유지 —
검증자는 백스톱으로 남고 grep 이 1차 포착). 경로는 `governance/rules/`.

### #1 `design-pretendard-only.md`
```yaml
check-deny: ["fontFamily\\s*:\\s*[\"'](?!Pretendard)"]
check-glob: ['lib/**/*.dart']
check-hint: 'fontFamily 는 Pretendard 만 (app_theme _textTheme 경유)'
```
⚠️ 음성 lookahead `(?!…)` — 검사기가 **Python-re**(dw-lint)여야 동작. 리터럴 grep 이면 미동작.

### #2 `색-토큰-검사-사각지대-봉쇄--colorswhite-blackfromrgbo-fromargb-도-deny.md`
```yaml
check-deny: ['Colors\.(white|black)\b', 'Color\.from(RGBO|ARGB)\(']
check-glob: ['lib/**/*.dart']
check-exclude: ['lib/core/theme/balipick_colors.dart', 'lib/features/weather/presentation/widgets/weather_node_map.dart']
check-hint: 'BalipickColors 토큰만. transparent 허용. 알파-캐리어 예외는 weather_node_map 제외'
```

### #3 `분석-이벤트-파라미터에-ga4-예약어-source-medium-campaign-금지--event_source.md`
```yaml
check-deny: ["(?:bpTrack|track)\\s*\\(\\s*[\"'][a-z0-9_]+[\"']\\s*,\\s*\\{(?:[^{}]|\\{[^{}]*\\})*?[\\s,{]source\\s*:"]
check-glob: ['*.ts', '*.tsx', '*.js', '*.phtml']
check-exclude: ['node_modules/*', 'vendor/*', 'public/new-app/*', '*__tests__*']
```
⚠️ 객체리터럴을 줄넘어 매치 — 검사기가 **파일 전체 re.DOTALL** 로 적용해야 함(라인단위면 미동작).
2단계 검증에서 회귀 테스트로 확인.

### #4 `로컬-개발-docker-는-단일-환경--compose-프로젝트명-balipick-고정.md`
```yaml
check-require: ['COMPOSE_PROJECT_NAME\s*=\s*balipick']
check-glob: ['infra/scripts/dev-up.sh']
check-hint: 'dev-up.sh 는 COMPOSE_PROJECT_NAME=balipick 고정 (워크트리명 사용 금지)'
```

### #6 `mobile-secure-token-storage.md`
```yaml
check-deny: ['SharedPreferences']
check-glob: ['lib/core/storage/*.dart']
check-hint: '토큰 저장 계층에 SharedPreferences 금지 — FlutterSecureStorage/TokenStore 만'
```

## 2단계 — 컴파일 + 재설치 + 검증
```bash
make build && make dry-run && make doctor         # 스키마·컴파일 green
/dw-install                                       # 또는 make install-project P=~/Repository/balipick ; P=~/Repository/balipick-app
```
**dw-checks.json 반영 확인 + 현재 트리 무위반 회귀 검증**(오탐 0 재확인):
```bash
# balipick-app: #1 Pretendard, #2 색, #6 토큰
grep -q 'fontFamily' ~/Repository/balipick-app/.claude/dw-checks.json && echo "#1 반영"
# 현재 트리 검사(0 위반 기대 — #6 storage, #2 색: weather 제외 후 0)
rg -n 'Colors\.(white|black)\b|Color\.from(RGBO|ARGB)\(' ~/Repository/balipick-app/lib -g '*.dart' -g '!**/balipick_colors.dart' -g '!**/weather_node_map.dart' | wc -l   # 0 기대
rg -n 'SharedPreferences' ~/Repository/balipick-app/lib/core/storage -g '*.dart' | wc -l   # 0 기대
# balipick: #3 GA4(0 기대), #4 docker(require 충족)
```
- #3 은 현재 0매치라 "미동작"과 구분 안 됨 → 검사기 DOTALL 확인용으로 **버그 트리 회귀**:
  `git -C ~/Repository/balipick stash; git worktree add /tmp/ga4bug e592d9ce` 후 검사 실행 → **6건**
  잡히면 유효(끝나면 worktree 제거). 여의치 않으면 합성 라인으로 dw-lint 직접 호출해 확인.
- 어떤 검사든 **현재 트리 위반 0** 이어야 함. 0 아니면 그 매치가 진짜 위반인지 확인 후, 예외면
  check-exclude 보강.

## 3단계 — 커밋
```bash
git add -A && git commit -m "feat(rules): batch-1 결정론 check 추가(pretendard·색사각지대·ga4·docker·토큰) — 검증자 부하↓"
gh pr create --fill    # 또는 vault 레포 flow
```

## 넣지 않는 것 (검증자 유지 — 실측 탈락)
- **#7 빈 콜백**: 현재 매치 4건 중 3건이 주석 → grep 오탐. code-review 유지. (별도) 실코드 위반 1건
  `~/Repository/balipick-app/lib/features/spots/presentation/detail/widgets/spot_reviews.dart:200`
  `onTap: _loading ? () {} : _loadMore` 수정은 senior-mobile 태스크로.
- **#5 쿠키 플래그**: 플래그가 변수에 담겨 grep 특정 불가. security-qa 유지.

## 마감 기록
- `dw_write_memory`: "검증자→check 전환은 실코드 grep+합성 non-vacuity 로 오탐0 확인 후에만. #7(주석 오탐)·#5(변수 의미규칙)은 grep 부적합 → 검증자 유지."
