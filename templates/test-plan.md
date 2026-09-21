# 테스트 계획 작성 항목

정확한 UnitSpec pin과 관련 요구/case ID를 기준으로 한다. 작성된 계획과 실제 실행 결과를 구분한다.

## 범위와 독립 기대값

각 case의 입력/상황·행동·예상 결과·정답 근거·위험을 기록한다. 제품 함수로 expected를 생성하지 않는다.

## 실행 목록

check ID | case IDs | argv 배열 | 상대 cwd | timeout | 필수 여부 | expected | oracle

공개 schema의 required/expected_exit 및 모든 필드를 지킨다. 외부 계정·비운영 fixture·버전·정리 절차·격리 조건을 명시한다.

필요한 check에는 environment_ref/role과 project-runner의 services/fixture/evidence를 명시한다. 각 service의 로컬 health/build/run 확인, fixture setup/cleanup의 case marker, 소유 namespace, text/JSON evidence 경로·최대 크기·필수 여부를 고정한다. 준비·cleanup·필수 증거 실패는 전체 성공으로 처리하지 않는다.

## 외부 도구 필수 검사

승인된 system.tool_plan과 unit.tool_observations를 확인한다. browser/database 적용 단위는 tool_checks의 capability·check_id·evidence_id를 실제 required project-runner JSON evidence에 연결한다. 브라우저는 실제 과업 관찰과 지속 회귀 runner를 별도로 준비한다. DB는 소유 fixture와 독립 재조회 결과·정리 검사를 함께 계획한다. 정확한 envelope는 같은 release의 schema와 [정책 안내](../docs/v2.2-tools.md)를 따른다. 실제 응답 없이 증거 JSON을 채우지 않는다.

## 추적과 증거

요구→case→check→예정 테스트 파일→증거 종류를 연결한다. 아직 구현 안 된 검사와 수동/미지원 검사는 실행됐다고 쓰지 않는다.

## 실패와 재실행

제품 실패·연결/권한/쿼터·timeout·drift·부분 결과의 판정과 재실행 조건·한도를 적는다. 필수 결과가 없으면 pass로 만들지 않는다.

## Gate B 자료

UnitSpec·TestPlan·scope와 적용되는 환경/DB 계획의 정확한 pins를 같은 review bundle에 묶는다. 계획에서 추가한 검사·fixture·health 파일도 scope에 반영한다. 계획 작성은 제3의 사용자 승인 단계나 검사 통과가 아니다.
