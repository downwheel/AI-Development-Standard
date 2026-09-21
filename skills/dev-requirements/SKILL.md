---
name: dev-requirements
description: Turn a development request and recorded project investigation into scope, user behavior, constraints, questions, and measurable acceptance criteria. Use to refine or revise requirements without implementing the product.
---

# 요구사항 상세화

[실행 계약](references/runtime.md)을 읽는다. 입력은 실제 사용자 요청/답변과 정확한 `discovery-context` pin이다. 기록이 없거나 다른 프로젝트면 조사 단계로 인계한다. 이미 해결된 결정을 다시 묻지 않는다.

## 실행

1. 요청이 조회이면 현재 accepted 요구와 승인/초안 구분을 보여주고 끝낸다. 실제 요구 변경이면 변경 의도와 영향을 기록하여 옛 계약으로 계속 완료되는 것을 막는다.
2. 스키마를 확인하고 고정된 조사 ref로 StageRun을 시작한다. 사용자·사용 상황·문제·원하는 결과를 설명한다.
3. 포함/제외 범위, 정상 흐름과 필요한 실패·취소·재시도·중복·권한 경계를 정한다. 계산 의미·시간·단위·저장·보존처럼 결과를 바꾸는 결정은 모호하게 남기지 않는다.
4. 소스에서 답을 얻을 사실은 조사 요청으로, 제품 의도·비용·호환성 선택은 사용자 질문으로 분리한다. 중요한 질문을 이유·권장안·영향과 함께 최대 5개씩 묶는다. 필수 답이 없으면 `waiting_input`이며 무응답을 승인으로 보지 않는다.
5. 안정적인 requirement ID마다 관찰 가능한 인수 기준과 case ID를 만든다. 사례는 입력/행동/예상 결과와 실패·경계값을 포함한다. 기존 동작 유지와 변경 동작을 분리한다.
6. 요구 JSON과 사람이 읽는 Markdown을 같은 revision으로 발행한다. 최소 기계 계약은 `requirements: [{id, description, case_ids: [string]}]`이며 부가 필드는 실제 공개 스키마를 따른다. 구현 방법이나 현재 출력으로 기대값을 대체하지 않는다.
7. 필수 제품 의미·포함/제외·인수 기준 연결을 확인하고 완료한다. 정확한 요구 pin과 그것이 참조한 조사 pin을 `dev-system-design`에 전달한다.

## 사용자 자료

문서에 목적·시나리오·범위·요구/인수 기준 표·제약·기존 영향·실제 질문과 답변 출처·가정·이전판 대비 변경을 담는다. 가정은 사용자가 결정한 사실로 표현하지 않는다. 중요한 불확실성은 해소 담당과 시점을 남긴다.

이 단계의 완료나 accepted 발행은 인간 승인이 아니다. Gate A는 이후 시스템 설계를 포함한 정확한 세 문서 묶음을 검토한다. 요구 변경은 새 revision으로 기록하며 이미 만든 설계·제품·소스 이력을 자동 되돌리지 않는다. 조사 보완은 필요한 항목만 요청하고 같은 쟁점의 기본 왕복 한도 2회를 넘으면 사용자 결정으로 넘긴다.
