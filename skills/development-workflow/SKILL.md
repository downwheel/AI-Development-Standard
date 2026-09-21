---
name: development-workflow
description: Start or resume a development workflow by locating the project and recorded stage, then route to independently callable development skills. Coordinate requested multi-stage work without replacing a named stage or forcing gates on general advice.
---

# 개발 흐름 길잡이

[실행 계약](references/runtime.md)을 읽는다. 사용자의 일반 질문이나 단순 가역 편집에 전체 개발 절차를 강제하지 않는다. 특정 단계 Skill을 요청했다면 해당 단계가 진입점이다.

## 진행

1. 요청이 조회/비교, 신규 개발, 재개, 재작업, 검증 재실행, 소스 복원 중 무엇인지 판단한다.
2. 실제 프로젝트 경로/등록 ID·run/unit을 확인하고 `workflow_status`로 현재 산출물·인간 승인·적용 소스·검사를 구분하여 읽는다. 등록이 필요하면 공개 schema와 현재 사용자 범위를 확인한다. 제품 폴더에 `.git`·`.harness`를 만들지 않는다.
3. 필요한 단계와 정확한 입력 refs를 선택한다. 이전 대화의 마지막 문장보다 현재 원장·현재 소스를 기준으로 한다.
4. 해당 Skill이 설치돼 있으면 그 SKILL.md를 읽고 작업한다. 공통 Skill 자동 실행 API나 특정 호스트 도구 이름을 가정하지 않는다. 없으면 어떤 단계 자료가 필요한지 알리고 설치된 동등 경로를 확인한다.
5. 단일 단계 요청은 그 산출물에서 끝낸다. 사용자가 개발 전체를 요청했다면 허용된 범위의 준비 작업을 이어가고 두 실제 Gate에서 구체적인 문서 묶음을 제시한다. 인간 승인을 생성하거나 생략하지 않는다.

## 단계 지도

| 요청/현재 필요 | 진입점 |
|---|---|
| 현행 소스·환경·DB 조사 | dev-discover |
| 범위·질문·인수 기준 | dev-requirements |
| 전체 구조·영향·분량 | dev-system-design → dev-review Gate A |
| 화면/API/DB/통합 상세 | dev-unit-design |
| 실행 가능한 검사 계획 | dev-test-design → dev-review Gate B |
| 승인 범위 구현·수정 | dev-implement |
| 실제 검사·재검증 | dev-verify |
| AI 검토·구체적 승인 자료·실제 결정 기록 | dev-review |
| 보여주기·판 비교·과거 실패 로그 | dev-artifacts |
| 소스 사본 export·복원 계획/적용 | dev-restore |

Gate A는 조사+요구+시스템 설계 세 pins, Gate B는 단위+그 단위를 참조한 테스트 계획 두 pins다. unit-spec은 test-plan을 역참조하지 않는다.

기존 유효 승인 범위 내 수정은 구현/검사로 연결한다. 요구·계약 변경은 해당 단계에 새 revision으로 인계하며 이전 승인·실패는 보존한다. 호스트 전환 시 이전 writer 종료·lease·미해결 journal·소스 확인 없이 만료 시간만으로 쓰기 소유권을 가져오지 않는다. 조회와 독립적인 준비는 계속한다.

최종 안내는 현재 상태, 이번에 만든/읽은 자료의 정확한 refs, 다음 Skill과 필요한 입력/승인, 실제 차단만 포함한다. 별도 원장이나 두 번째 길잡이를 만들지 않는다.
