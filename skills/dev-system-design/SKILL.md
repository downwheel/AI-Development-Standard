---
name: dev-system-design
description: Design system responsibilities, data flows, alternatives, impact, work units, and verification strategy from pinned project requirements. Prepare the concrete Gate A review package before unit design.
---

# 시스템 설계

[실행 계약](references/runtime.md)을 읽는다. 입력은 정확한 조사·요구 pins이며 요구가 같은 조사 revision을 참조해야 한다. 소스나 변경 가능한 외부 근거가 오래됐으면 필요한 범위만 재확인한다.

## 실행

1. 조회는 저장된 설계만 보여준다. 새 설계/재설계는 StageRun과 이전 설계 pin, 변경 이유·대상 요구를 고정한다.
2. 사용자 목적·포함/제외·인수 기준·제약을 요약한다. 현행 구조, 실제 소스 없음, 조사하지 못한 영역을 구분한다.
3. 관련 UI·도메인·API·데이터·외부 시스템의 책임과 정상/실패 흐름을 설계한다. 인증/인가·복구·재시도·중복·취소·보존·관측성은 제품에 필요한 범위로 구체화한다.
4. 중요한 구조 선택은 대안·추천 이유·비용·복잡도·호환성·운영 영향을 비교한다. 새 의존성의 역할·버전·대안·필요한 사용자 결정을 적는다. Context7 결과는 설치 버전과 공식 원문에 대조한다.
5. 작업을 안정적인 unit ID와 목적·산출물·선행 관계·영향 파일/계층·규모·단위에서 확정할 결정으로 분해한다. 규모는 추정 근거와 불확실성을 표시한다.
6. 요구→구조→단위→검증 전략을 연결한다. 변경 전 사본·복구 범위와 DB/Figma/배포 같은 외부 상태의 한계를 설명한다.
7. `system-design` payload와 Markdown을 발행한다. 최소 `requirement_ids: [string]`는 입력 요구와 일치해야 한다. 단위 목록·흐름·결정·영향·검증·MCP 계획을 실제 내용으로 채운다.
8. 입력 정합성, 요구 누락, 단위 의존 순환, 필수 미결을 검사한다. 정확한 discovery + requirements + system-design pins를 `dev-review`의 Gate A 준비에 넘긴다.

## 설계 자료와 경계

문서는 제안 구조·현행 대비 변화·대안·작업 분량·개념 화면/API/DB·검증/복구 전략과 승인하면 진행할 범위를 보여준다. 자기 manifest 해시는 canonical 본문에 넣지 않는다.

시스템 도식은 로컬 텍스트/도표가 기본이며 필요하고 허용된 경우 FigJam 구조도를 생성할 수 있다. 실제 노출 도구와 전문 Skill의 선행 조건을 확인한다. 상세 UI frame/component 작성은 `dev-unit-design`에서 한다. 이 단계에서 제품 구현·의존성 설치·DB migration·운영 배포를 수행하지 않는다.

완료는 설계서 작성 완료다. Gate A의 실제 사용자 승인 전에는 단위 설계를 시작하지 않는다. 새 요구를 기존 입력처럼 바꿔 끼우지 말고 새 revision과 영향 기록으로 인계한다.
