---
name: dev-discover
description: Investigate an existing or planned software project and record its source, environment, data boundaries, verification commands, and unknowns before requirements or design work. Use for scoped reinvestigation; do not implement or install dependencies.
---

# 프로젝트 조사

현재 프로젝트의 사실과 미확인을 기록하여 요구 상세화에 넘긴다. 일반 질문에 전체 개발 절차를 강제하지 않는다.

먼저 [실행 계약](references/runtime.md)을 읽고 요청이 조회·재개·새 조사인지 구분한다. 조회는 기존 산출물을 반환하며 실행이나 발행을 만들지 않는다.

## 실행

1. 실제 사용자 목적과 프로젝트 등록 정보, 제품 경로, run을 확인한다. 대상이 여러 개이거나 경로가 미정이면 필요한 질문과 독립적인 준비를 먼저 한다. 사용자가 신규 개발과 대상 폴더를 지정한 범위에서 폴더가 없으면 project_register의 create_root=true로 빈 폴더를 등록할 수 있다. 제품 코드·.git·.harness는 만들지 않는다. 기존 프로젝트나 읽기 조사만 요청된 범위에서는 폴더를 임의 생성하지 않는다.
2. 공개 스키마를 조회하고 `dev-discover` StageRun을 시작한다. 재조사는 기존 discovery pin과 사실 확인 항목을 고정한다. 시작 전 소스 사본이 없으면 관찰 범위와 한계를 기록한다.
3. 적용 지침, README, 솔루션·패키지·lockfile, 런타임, CI, 관련 모듈·호출부·기존 검사·미커밋 변경을 좁은 범위부터 조사한다. 선언 버전과 실제 확인한 버전을 구분한다.
4. 빌드·타입·lint·테스트 명령을 **읽어서 추출**한다. 검사·설치 스크립트를 환경 조사라는 이유로 실행하지 않는다. 기존 재사용 기능과 영향 후보를 찾는다.
5. 데이터가 관련되면 DTO·API·schema·migration을 읽는다. DB MCP는 등록된 대상과 읽기 전용 권한으로 metadata→제한 집계→필요 표본 순서로 사용한다. 실제 비밀 값이나 업무 원문을 보고서에 복사하지 않는다.
6. 사실·추론·미확인, 근거와 관찰 시각, 조사한 범위·제외·도구 차단을 구분하여 `discovery-context` JSON payload와 Markdown을 발행한다. 필수 자료가 없으면 완료로 속이지 말고 대기/실패와 다음 해소 동작을 기록한다.
7. 받은 정확한 output ref로 단계를 종료하고 `dev-requirements` 인계 자료를 제시한다. 다음 단계를 자동 승인하지 않는다.

## 산출물과 종료

Markdown은 목적·프로젝트 지도·기존 동작·버전·검사 명령/미실행·데이터 경계·영향 후보·미확인 항목·다음 행동을 담는다. JSON은 facts, constraints, verification_candidates, impact_candidates, unknowns, tool_observations의 의미를 유지하되 실제 허용 필드는 공개 스키마를 따른다.

기존 제품의 Git 관리 정보는 바꾸지 않는다. 외부 MCP가 막혀도 독립적인 소스 조사는 계속하고 필수 근거의 차단은 남긴다. 자료가 바뀌면 새 revision을 만들며 이전 관찰을 덮어쓰지 않는다. 추가 사실 조사는 항목·범위·종료 조건을 고정하고 같은 쟁점은 기본 2회 왕복 후 미해결 이유와 선택지를 사용자에게 제시한다.
