# UI 단위 설계 작성 항목

이 양식은 실제 UnitSpec의 Markdown과 부가 계약을 작성할 때 사용한다. 단위/요구/case ID와 입력 pins를 먼저 고정한다.

## 화면과 흐름

화면 ID·사용자 과업·진입/종료·역할·데이터를 나열하고 주요 흐름과 실패/복구 흐름을 연결한다.

## 배치와 시각 규칙

영역별 우선순위·정렬·크기·간격·스크롤, component/variant, 실제 token/값, viewport별 재배치와 긴 문구·확대 처리 기준을 적는다.

## 상태와 상호작용

상태 | 진입 조건 | 표시/사용 가능한 조작 | 이벤트 | 다음 상태 | 오류/복구 | case ID

필요한 초기/로딩/빈 결과/정상/오류/권한/부분 결과를 채운다. 해당 없는 상태는 이유를 적는다.

## 접근성과 데이터

label·semantic·키보드·tab/focus·알림, 값/단위/precision/시간대·정렬·필터·갱신·취소·stale 응답 규칙을 정한다.

## 디자인 근거

Gate A tool_plan의 ui_design mode(required/preferred/local_only)와 적용 단위를 표시한다. Figma를 먼저 사용하고 preferred의 실제 차단은 승인한 로컬 대안 및 실패 근거와 연결한다. local_only는 실제 사용자의 명시 선택 출처가 필요하다. 실제 file/node refs·구조 확인·스크린샷·관찰 시각 또는 로컬 배치안을 연결한다. mock·native·실제품 결과를 구분한다.

## 구현·검사 인계

변경 파일/계층·재사용 component·연결 API·요구/case별 예상 결과, 환경/DB 적용 여부와 N/A 이유를 적는다. 파일별 정확한 action과 baseline은 후속 scope-manifest에 고정하며 해당 표를 Gate B에서 사용자에게 보여준다. 프런트엔드에는 DB 자격증명을 주입하지 않는다. UnitSpec은 후속 TestPlan·scope·environment hash를 역참조하지 않는다.
