# 테스트 계획 작성 항목

정확한 UnitSpec pin과 관련 요구/case ID를 기준으로 한다. 작성된 계획과 실제 실행 결과를 구분한다.

## 범위와 독립 기대값

각 case의 입력/상황·행동·예상 결과·정답 근거·위험을 기록한다. 제품 함수로 expected를 생성하지 않는다.

## 실행 목록

check ID | case IDs | argv 배열 | 상대 cwd | timeout | 필수 여부 | expected | oracle

공개 schema의 required/expected_exit 및 모든 필드를 지킨다. 외부 계정·비운영 fixture·버전·정리 절차·격리 조건을 명시한다.

## 추적과 증거

요구→case→check→예정 테스트 파일→증거 종류를 연결한다. 아직 구현 안 된 검사와 수동/미지원 검사는 실행됐다고 쓰지 않는다.

## 실패와 재실행

제품 실패·연결/권한/쿼터·timeout·drift·부분 결과의 판정과 재실행 조건·한도를 적는다. 필수 결과가 없으면 pass로 만들지 않는다.

## Gate B 자료

UnitSpec과 TestPlan은 정확한 두 pins로 review bundle에 묶는다. 계획 작성은 제3의 사용자 승인 단계나 검사 통과가 아니다.
