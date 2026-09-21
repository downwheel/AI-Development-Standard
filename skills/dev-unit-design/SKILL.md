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
3. 승인된 tool_plan의 해당 unit 정책으로 profile 자료를 작성한다. UI는 Figma의 기존 component/token 조사→native 작성→구조·화면 재조회가 우선이다. native 필수 차단은 waiting_tool이며, preferred의 로컬 대안은 Gate A에서 승인된 범위만 사용한다. 버전별 API·SDK·설정은 Context7 또는 OpenAI Docs와 공식 원문/설치 타입을 대조한다. 실제 결과·차단·대안·적용 결정을 unit의 tool_observations로 고정한다.
4. 요구 ID와 case ID를 시스템의 해당 단위와 정확히 연결한다. `environment`와 `database`에 `{required:true}` 또는 `{required:false,reason:...}`를 명시한다. 세부 계약·파일 책임·디자인 참조·실패 정책을 허용 schema에 맞춰 포함한 `unit-spec`을 먼저 발행한다.
5. 환경이 필요하면 해당 unit ref를 `dev-environment`에 전달하고 실제 연결 관찰을 고정한 environment-contract를 받는다. DB 작업은 그 unit/environment refs를 입력으로 `db-work-plan`을 발행한다. 미지원 DB 작업을 임의 SQL로 우회하지 않는다.
6. 구현·검사 파일을 구체화한 뒤 별도 `dev-unit-design` StageRun의 입력을 system+unit+사용한 환경/DB refs로 고정하고 `scope-manifest`를 작성한다. 파일마다 layer·정확한 상대 path·create/modify/delete·이유·requirement/case IDs·required 여부와 baseline을 적는다. create는 `expected_absent:true`, modify/delete는 실제 `before_sha256`이다. 기존 파일명 변경은 삭제+생성 두 행으로 연결한다.
7. scope에는 기준 snapshot digest, 정확한 DB 객체/action/baseline, environment_refs/db_plan_refs를 담는다. 생성물은 generator/version/input hash·출력 root/pattern·action·파일/용량 한도로 제한한다. 빈 변경 범위나 전체 소스 glob은 허용하지 않는다. core가 scope payload에서 만든 Markdown 표를 `render_artifact`로 열어 파일/계층별 분량과 DB 계획이 일치하는지 확인한다.
8. 정확한 unit ref를 `dev-test-design`으로 넘긴다. 테스트 설계가 파일 범위를 추가하면 구현 전에 scope 새 revision으로 반영한다. unit·test·scope·적용 환경/DB pins가 모두 완성되어야 Gate B 묶음을 제공할 수 있다.

## Gate B와 재작업

UnitSpec은 이후 TestPlan·scope·environment를 역참조하지 않는다. 후속 산출물이 이 UnitSpec의 정확한 pin을 참조하고 `dev-review`가 전체 pins를 묶어 Gate B를 만든다. scope 본문에 자기 hash나 review ID를 넣지 않는다. 단위 작성 완료나 AI 검토 통과는 구현 승인이 아니다.

단위 계약을 바꾸면 새 revision과 영향 기록을 남기며 영향받는 TestPlan·승인·구현·검사만 재검토한다. 이전 실패와 승인을 삭제하거나 제품 소스를 복원하지 않는다. 필수 외부 산출물 대기는 `waiting_tool`, 제품 결정 대기는 `waiting_input`으로 기록한다.
