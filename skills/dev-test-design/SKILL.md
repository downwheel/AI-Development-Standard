---
name: dev-test-design
description: Define reproducible checks, independent expected results, fixtures, coverage, and evidence requirements for a pinned unit design before Gate B. Use to revise verification plans; do not claim tests have run.
---

# 테스트 설계

[실행 계약](references/runtime.md)과 [검사 설계 기준](references/test-quality.md)을 읽는다. 입력은 정확한 UnitSpec과 그 요구·시스템/유효 Gate A이다. TestPlan은 단위 설계 이후에 만들며 Gate B의 일부다.

## 실행

1. 조회이면 기존 계획을 표시한다. 새 설계/수정은 StageRun을 시작하고 `unit_ref`의 artifact/revision/hash를 고정한다. 이전 계획이 다른 단위를 가리키면 재사용하지 않는다.
2. 요구 case ID마다 정상·실패·경계값·취소·복구·기존 호환성 중 해당하는 관찰을 정의한다. 제품 코드와 독립된 기대값 근거를 적는다.
3. 기존 runner·CI 명령·버전·프로젝트 규칙을 조사한다. 필요한 단위/통합/브라우저/수동 검증을 구분하고 가장 가까운 검사부터 계획한다. 새 도구 도입이 필요하면 비용·대안·변경 범위를 명시한다.
4. 필요한 `environment_ref`와 실행 `role`, fixture·테스트 데이터·격리·정리·시간/출력 한도를 정한다. `runner.kind:project-runner`를 사용하면 service의 명령/로컬 health/build 확인, fixture setup/cleanup의 실제 case IDs, text/JSON evidence의 상대 경로/크기/필수 여부를 계획한다. 실제 지원 schema와 [검사 설계 기준](references/test-quality.md)을 따른다. 운영 변경이나 고객 데이터 사용을 묵시적으로 허용하지 않는다.
5. `test-plan` payload에 정확한 `unit_ref`와 checks를 작성한다. 현재 최소 check 계약은 아래와 같으며 최종 필드는 공개 스키마로 확인한다.
   - `check_id`, `argv: [string]`, 안전한 상대 `cwd`, `timeout_seconds`(1~300), `required`, `expected_exit: 0`, `case_ids: [string]`, `expected`, `oracle`.
   - argv는 셸 명령 문자열이 아닌 실행 파일과 인자 배열이다. 명령 연결·셸 치환·비밀 값·무제한 대기를 넣지 않는다.
   - 기능 사례 검사는 기본 case-results/team-json으로 실제 case ID와 상태를 출력한다. command-exit/exit-code는 명령 완료 자체가 승인 인수 기준일 때 두 필드를 모두 명시한다. 정확한 stdout marker는 검사 설계 기준을 따른다.
6. 해당 unit의 tool_plan을 읽고 tool_checks에 필수 capability와 check_id/evidence_id를 연결한다. UI의 실제 브라우저 과업 관찰과 저장된 회귀 runner를 구분하고, DB 저장은 승인된 독립 재조회로 확인한다. 실제 MCP 응답을 수집할 방법과 필수 text/JSON 증거를 계획한다. 테스트 도구의 버전별 fixture·격리·대기 API는 Context7/공식 문서 근거를 확인한다.
7. Markdown에 요구/case→check→기대값 근거·실행 환경·증거·남은 위험을 표시한다. 아직 없는 테스트 파일은 구현할 대상으로 표시하고 실제 검사 성공으로 쓰지 않는다.
8. 필수 case의 누락·중복·실행 불가능·기대값 순환을 검토한 뒤 발행한다. 추가된 검사/fixture/health 파일은 `dev-unit-design`의 scope에도 반영한다. unit·test·scope·적용 환경/DB 계획 전체 pins를 `dev-review`에 넘겨 Gate B를 준비한다.

계획에 수동 검사나 현재 runner가 표현하지 못하는 검사가 있으면 미지원/후속 실행 방법을 명시한다. 실행하지 않고 pass를 기록하거나 빈 명령을 통과 검사로 넣지 않는다. 필수 검증이 실제로 충족될 방법이 없으면 검증 가능성 문제를 해결한 뒤 승인 대상으로 제시한다.

재호출에서 기대값·필수 검사·허용 범위가 달라지면 새 TestPlan revision과 Gate B 검토가 필요하다. 단순 조회는 새 계획·새 승인·실행을 만들지 않는다. TestPlan 완료는 실행 결과가 아니다.
