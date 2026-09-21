---
name: dev-implement
description: Implement a currently approved unit and its test plan with source snapshots, bounded ownership, implementation evidence, and preserved user changes. Use for authorized implementation and fixes within the approved contract.
---

# 승인된 단위 구현

[실행 계약](references/runtime.md)을 읽는다. 정확한 UnitSpec·TestPlan, 현재 유효 Gate A/B와 실제 제품 경로를 확인한다. 미승인 범위를 제품 코드로 먼저 만들지 않는다.

## 실행

1. `workflow_status`와 해당 공개 스키마로 현재 변경 의도·승인·미결·writer 상태를 확인한다. UnitSpec과 TestPlan이 서로 다른 revision을 기준으로 하면 진행하지 않는다.
2. 구현 시작 operation의 실제 이름·입력을 describe로 확인한다. `begin_implementation`이 공개돼 있다면 사용해 승인 근거와 pre-snapshot을 확보한다. 없으면 동등 기능을 임의로 기록하지 않고 실행기 부족을 알린다.
3. 현재 사용자 변경을 읽고 보존한다. 협조적 lease와 실제 소스 기준을 확인한다. 미해결 복원 journal이나 이전 writer가 있으면 조회·준비까지만 진행한다.
4. 승인된 변경 파일/책임·계약에 맞춰 제품 코드와 관련 호출부·타입·설정 예시·문서를 완결된 변경으로 구현한다. TestPlan의 case를 지속 실행 가능한 테스트 파일에 연결한다.
5. UI는 승인 당시 Figma native 참조와 계약을 확인하고, SDK/API는 설치 버전·공식 문서를 확인한다. 도구가 실패하면 존재하지 않는 기능으로 대체하지 않는다. 필요한 전문 Skill이 있으면 읽고 해당 실제 MCP를 사용한다.
6. 가까운 검사부터 실행한다. 최종 검사 증거는 실행기의 실제 check operation으로 남긴다. 직접 실행한 개발 중 검사는 대상·명령·결과를 구분하여 기록하며 최종 통과로 자동 승격하지 않는다.
7. 변경 범위·소스 drift·계약 변경 여부를 검토한다. 계약을 바꿔야 하면 변경 이유와 정확한 설계 pins로 해당 단계에 인계한다. 테스트를 약화하거나 기대값을 현재 코드에 맞춰 바꾸지 않는다.
8. 공개된 `finish_implementation` 또는 동등한 실제 operation으로 post-snapshot과 구현 receipt를 확정한다. 변경 파일·요구→구현/검사 연결·실행/미실행·남은 위험을 보고하고 `dev-verify`에 정확한 입력을 넘긴다.

## 경계와 종료

제품의 정상 working-tree 편집은 허용 범위지만 제품 Git의 add/commit/stash/reset/checkout/restore/worktree, index/refs/config/hooks 변경은 이 Skill의 기록 방식이 아니다. 개인 소스 사본은 등록된 개인 history에 보존한다.

기존 승인 범위 내 수정은 불필요하게 재승인받지 않는다. 실제 계약·검사 기대·새 의존성·외부 변경 범위가 달라지면 해당 결정을 해결한다. 제품 배포·운영 DB 변경·계정 연결·원본 복원 권한은 설계 승인과 별개다.

중단이나 실패 시 바뀐 파일과 확보된 snapshot·실제 검사 결과를 보존한다. 자동 rollback으로 사용자 변경을 덮어쓰지 않는다. 코드 작성 완료, 적용 receipt, 검증 통과를 따로 보고한다.
