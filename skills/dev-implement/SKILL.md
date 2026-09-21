---
name: dev-implement
description: Implement a currently approved unit and its test plan with source snapshots, bounded ownership, implementation evidence, and preserved user changes. Use for authorized implementation and fixes within the approved contract.
---

# 승인된 단위 구현

[실행 계약](references/runtime.md)을 읽는다. 정확한 UnitSpec·TestPlan, 현재 유효 Gate A/B와 실제 제품 경로를 확인한다. 미승인 범위를 제품 코드로 먼저 만들지 않는다.

## 실행

1. `workflow_status`와 해당 공개 스키마로 현재 변경 의도·승인·미결·writer 상태를 확인한다. UnitSpec과 TestPlan이 서로 다른 revision을 기준으로 하면 진행하지 않는다.
2. `begin_implementation`으로 승인된 unit/test/scope/environment/DB pins와 pre-snapshot을 확보한다. 실제 변경은 `mode:change`이며 빈 scope로 우회하지 않는다. 현재 소스에 대한 검사 재관찰만 필요하면 `mode:observe`를 사용하고 파일·DB를 바꾸지 않는다.
3. 현재 사용자 변경을 읽고 보존한다. 협조적 lease와 실제 소스 기준을 확인한다. 미해결 복원 journal이나 이전 writer가 있으면 조회·준비까지만 진행한다.
4. 편집 묶음마다 `check_edit_scope`에 정확한 상대 path와 action을 전달하고 통과한 범위를 구현한다. 관련 호출부·타입·설정 예시·문서·회귀 테스트 파일도 승인 목록에 있어야 한다. native 편집기를 OS 수준으로 가로채는 기능은 아니므로 종료 시 전체 diff를 다시 비교한다. 범위 밖 수정이 필요하면 먼저 해당 scope를 새 revision으로 재승인받는다.
   DB 적용은 승인된 typed 계획이 지원되는 경우에만 `execute_database`로 실행한다. 실제 target/권한·schema baseline·SQL/인자 hash·행 수/시간 상한과 transaction 결과 receipt를 확인한다. 임의 SQL 클라이언트 실행을 자동 추적한 것으로 주장하지 않는다. DB 백업은 소스 snapshot과 별개다.
   commit 결과가 불확실하면 자동 재시도하지 않는다. 실행 controller의 종료를 확인하고 실패 종료 또는 `reconcile_execution` 후 `plan_database_recovery`의 실제 관찰 자료를 사용자에게 제시한다. 실제 사용자 응답으로만 `record_database_recovery`를 호출한다. 수락해도 새로운 기준의 영향 단위 설계·Gate B가 필요하며 SQL 재실행·DB 복원을 의미하지 않는다.
5. 승인된 tool_plan과 해당 단위의 tool_observations를 읽는다. UI는 승인한 Figma native 참조 또는 허용된 로컬 배치안을 구현 직전에 확인한다. SDK/API·설정의 새 버전 쟁점은 Context7/OpenAI Docs 우선으로 공식 문서·설치 타입을 대조하며, 유효한 설계 근거는 재사용한다. 필수 native 차단이나 계약 변경을 몰래 fallback하지 않는다. 필요한 전문 Skill을 읽고 실제 노출 MCP를 사용하며 구현 중 새 사실이 승인 계약을 바꾸면 설계로 인계한다.
6. 가까운 검사부터 실행한다. 최종 검사 증거는 실행기의 실제 check operation으로 남긴다. 직접 실행한 개발 중 검사는 대상·명령·결과를 구분하여 기록하며 최종 통과로 자동 승격하지 않는다.
7. 변경 범위·소스 drift·계약 변경 여부를 검토한다. 계약을 바꿔야 하면 변경 이유와 정확한 설계 pins로 해당 단계에 인계한다. 테스트를 약화하거나 기대값을 현재 코드에 맞춰 바꾸지 않는다.
8. `finish_implementation`으로 post-snapshot과 구현 receipt를 확정한다. 승인 대비 실제 파일/action·필수 변경 누락·DB 계획 대비 실제 객체/행 수·환경 currentness를 확인한다. `needs_reconciliation`을 완료로 바꾸거나 사용자 변경을 자동 rollback하지 않는다. 정확한 receipt와 pins를 `dev-verify`에 넘긴다.

## 경계와 종료

제품의 정상 working-tree 편집은 허용 범위지만 제품 Git의 add/commit/stash/reset/checkout/restore/worktree, index/refs/config/hooks 변경은 이 Skill의 기록 방식이 아니다. 개인 소스 사본은 등록된 개인 history에 보존한다.

기존 승인 범위 내 수정은 불필요하게 재승인받지 않는다. 실제 계약·검사 기대·새 의존성·외부 변경 범위가 달라지면 해당 결정을 해결한다. 제품 배포·운영 DB 변경·계정 연결·원본 복원 권한은 설계 승인과 별개다.

중단이나 실패 시 바뀐 파일과 확보된 snapshot·실제 검사 결과를 보존한다. 자동 rollback으로 사용자 변경을 덮어쓰지 않는다. 코드 작성 완료, 적용 receipt, 검증 통과를 따로 보고한다.
