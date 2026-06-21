---
type: guidance
scope: engineering
status: stable
compiles-to: skill
title: PR·머지 규율
---
PR 본문은 **무엇/왜 → 변경 → 검증(증거: 테스트 수·analyze·스크린샷·red-green) → 후속/문의** 순서로
쓰고, 마감 매트릭스가 있으면 표로 정리한다. 머지: mergeable 확인 → `--squash` → 원격 브랜치 삭제 →
로컬 main ff → 워크트리 제거(squash 후 워크트리 커밋 폐기는 main 반영 확인 후에만). `--admin` 금지.
main 직접 push 금지(docs-only 도 PR), 운영 SSH 직접 패치 금지. migration·운영 secret·admin authz·데이터
손실 가능 변경은 머지 보류 + 사용자 동의를 요청한다. 커밋/PR/대화는 한국어, conventional commit(`feat(scope):`).
