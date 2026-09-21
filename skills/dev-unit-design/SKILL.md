---
name: dev-unit-design
description: Specify one approved work unit as implementable UI, API, data, or integration contracts, including native design artifacts when required. Use after Gate A and for scoped unit redesign; do not implement product code.
---

# 단위 설계

[실행 계약](references/runtime.md)을 읽는다. 유효한 Gate A의 시스템 설계와 해당 unit ID, 요구·조사 pins, 기존 단위가 있으면 이전 pin을 받는다. 인간 승인이 없으면 구체적 Gate A 검토 자료로 인계한다.

## Profile 선택

단위 목적에 필요한 자료만 읽는다. 여러 계층에 걸치면 profile을 조합하고 하나의 인터페이스로 연결한다.

- 화면·상태·컴포넌트: [UI 설계](references/ui.md)
- endpoint·메시지·인가: [API 설계](references/api.md)
- schema·조회·migration: [데이터 설계](references/data.md)
- 외부 서비스·비동기 경계: [통합 설계](references/integration.md)

## 실행

1. 보여달라는 요청은 기존 revision을 열고 끝낸다. 새 단위 설계는 StageRun을 시작하고 시스템/요구 ref와 해당 승인, 기준 소스·외부 근거를 확인한다.
2. unit의 책임, 변경 파일/계층, 공개 계약, 호출부, 입력/출력·상태·실패·복구와 의존 단위를 실제 구현 가능한 수준으로 정한다. 숫자·시간·순서·빈 값 등 결과에 영향을 주는 정책을 예시로 고정한다.
3. profile별 자료를 작성한다. MCP는 로컬 근거를 보완하는 실제 기능에 사용한다. Figma 필수 산출물은 native 구조를 확인하고, 계정·권한·쿼터 차단을 그림 파일로 감추지 않는다.
4. 요구 ID와 관찰할 case ID를 연결한다. 최소 payload는 `requirement_ids: [string]`, `case_ids: [string]`이다. 세부 계약·파일 책임·디자인 참조·실패 정책을 허용 schema에 맞춰 포함한다.
5. `unit-spec` JSON과 Markdown, 필요한 계약/디자인 증거를 같은 revision으로 발행한다. 구현 경계·MCP 입력 범위·결과·검증 방법·남은 한계를 사람이 검토할 수 있게 한다.
6. 요구 누락과 인터페이스 모순, 미정 정책을 확인하여 완료하고 정확한 unit ref를 `dev-test-design`으로 넘긴다.

## Gate B와 재작업

UnitSpec은 TestPlan의 해시를 역참조하지 않는다. TestPlan이 이 UnitSpec의 정확한 pin을 참조하고, `dev-review`가 두 pins를 묶어 Gate B를 만든다. 단위 작성 완료나 AI 검토 통과는 구현 승인이 아니다.

단위 계약을 바꾸면 새 revision과 영향 기록을 남기며 영향받는 TestPlan·승인·구현·검사만 재검토한다. 이전 실패와 승인을 삭제하거나 제품 소스를 복원하지 않는다. 필수 외부 산출물 대기는 `waiting_tool`, 제품 결정 대기는 `waiting_input`으로 기록한다.
