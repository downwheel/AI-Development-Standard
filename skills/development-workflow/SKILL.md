---
name: development-workflow
description: Start or resume a development workflow by locating the project and recorded stage, then route to independently callable development skills. Coordinate requested multi-stage work without replacing a named stage or forcing gates on general advice.
---

# 개발 흐름 길잡이

[실행 계약](references/runtime.md)을 읽는다. 사용자의 일반 질문이나 단순 가역 편집에 전체 개발 절차를 강제하지 않는다. 특정 단계 Skill을 요청했다면 해당 단계가 진입점이다.

## 진행

1. 요청이 조회/비교, 신규 개발, 재개, 재작업, 검증 재실행, 소스 복원 중 무엇인지 판단한다.
2. 실제 프로젝트 경로/등록 ID·run/unit을 확인하고 `workflow_status`로 현재 산출물·인간 승인·적용 소스·검사를 구분하여 읽는다. 등록이 필요하면 공개 schema와 현재 사용자 범위를 확인한다. 제품 폴더에 `.git`·`.harness`를 만들지 않는다. DB·서비스 인증을 먼저 준비할 필요가 있으면 프로젝트 등록 없이 `dev-environment`를 호출할 수 있다.
3. `next_actions`가 반환한 단계·required_refs·blockers·pending_decisions와 현재 소스를 확인한다. 이전 대화의 마지막 문장만으로 승인이나 다음 단계를 추정하지 않는다.
4. 해당 Skill이 설치돼 있으면 그 SKILL.md를 읽고 작업한다. 공통 Skill 자동 실행 API나 특정 호스트 도구 이름을 가정하지 않는다. 없으면 어떤 단계 자료가 필요한지 알리고 설치된 동등 경로를 확인한다.
5. 신규 run에서는 외부 도구 정책 버전을 확인하고 UI/Figma·버전 문서/Context7·브라우저·DB의 적용 단위와 실제 호스트 준비도를 조사 단계로 연결한다. 시스템 설계에서 사용 계획·필수 결과·대안을 Gate A에 고정한다. 기존 run은 고정 release/정책을 유지한다.
6. 단일 단계 요청은 그 산출물에서 끝낸다. 사용자가 개발 전체를 요청했다면 허용된 범위의 준비 작업을 이어가고 두 실제 Gate에서 구체적인 문서 묶음을 제시한다. 인간 승인을 생성하거나 생략하지 않는다.

## 단계 지도

| 요청/현재 필요 | 진입점 |
|---|---|
| 현행 소스·환경·DB 조사 | dev-discover |
| 사용자별 .env·역할별 연결 준비/관찰 | dev-environment |
| 범위·질문·인수 기준 | dev-requirements |
| 전체 구조·영향·분량 | dev-system-design → dev-review Gate A |
| 화면/API/DB/통합 상세 | dev-unit-design |
| 실행 가능한 검사 계획 | dev-test-design → dev-review Gate B |
| 승인 범위 구현·수정 | dev-implement |
| 실제 검사·재검증 | dev-verify |
| AI 검토·구체적 승인 자료·실제 결정 기록 | dev-review |
| 보여주기·판 비교·과거 실패 로그 | dev-artifacts |
| 소스 사본 export·복원 계획/적용 | dev-restore |

Gate A는 조사+요구+시스템 설계 세 pins다. 2.1 신규 run의 Gate B는 단위+그 단위를 참조한 테스트 계획+정확한 scope-manifest와 적용되는 환경/DB 계획 전체 pins다. 사용자가 자동 생성된 파일별 create/modify/delete와 DB 객체·행 수·실행 한계를 확인한 뒤 구현을 승인한다. unit-spec은 후속 산출물을 역참조하지 않는다.

기존 유효 승인 범위 내 수정은 구현/검사로 연결한다. 요구·계약 변경은 해당 단계에 새 revision으로 인계하며 이전 승인·실패는 보존한다. 호스트 전환 시 이전 writer 종료·lease·미해결 journal·소스 확인 없이 만료 시간만으로 쓰기 소유권을 가져오지 않는다. 조회와 독립적인 준비는 계속한다.

개발 전체 완료를 보고하기 전 `evaluate_completion`으로 모든 required 단위/case와 현재 소스 기준 검증을 확인한다. 최종 안내는 현재 상태, 이번에 만든/읽은 자료의 정확한 refs, 다음 Skill과 필요한 입력/승인, 실제 차단만 포함한다. 별도 원장이나 두 번째 길잡이를 만들지 않는다.
