---
name: dev-artifacts
description: Find, open, compare, or export recorded development requirements, designs, approvals, implementation evidence, and test attempts by exact revision. Use for showing existing results without regenerating or approving them.
---

# 산출물 조회

[실행 계약](references/runtime.md)을 읽는다. 이 Skill의 기본 동작은 읽기다. 기존 자료를 보여달라는 요청으로 StageRun·새 revision·승인·검사·소스 snapshot을 만들지 않는다.

## 실행

1. 사용자 표현에서 프로젝트/run/unit·종류·판·승인본·실패 attempt·비교 대상을 찾는다. 공개 `list_artifacts`, `get_artifact`, `workflow_status`, `diff_artifacts` 중 필요한 스키마와 조회만 사용한다.
2. 사용자가 특정 ref를 주면 정확히 그것을 읽는다. 버전이 없으면 유효 accepted 발행본과 승인·적용 여부를 기본으로 보여주고 더 새 후보가 있으면 함께 알린다. 후보가 여전히 여러 개면 구분 가능한 선택지를 보여준다.
3. core로 manifest·payload·MD의 존재/해시를 확인한다. 손상·없음·접근 불가·오래된 원격 링크를 분리한다. 과거 실패를 최신 성공 한 장으로 숨기지 않는다.
4. 짧은 결과 카드에 제목·revision·발행 상태·실제 인간 결정·적용 소스·검사 결과·소비 freshness를 구분해 표시한다. MD/HTML을 바로 열어야 하면 render_artifact로 개인 파생 조회 파일을 만들고 반환된 실제 path를 연결한다. 정확한 JSON·native file/node·로그/trace와 관찰 시각도 제공한다. 파생 파일 생성은 canonical 원장 변경과 다르다.
5. 비교는 두 정확한 버전의 요구/설계/검사 계약 차이·영향·승인 상태를 보여준다. 두 결과를 섞어 새 통과로 만들지 않는다.
6. 내보내기가 요청되면 개인 export 위치로 기존 bytes를 보존해 제공한다. 원본 제품 파일이나 canonical 문서는 바꾸지 않는다. 원본 적용 요청은 `dev-restore`로 인계한다.

## 표현 규칙

자기 manifest hash는 canonical MD에 삽입하지 않고 조회 카드에 표시한다. HTML 인덱스가 필요하면 읽은 자료의 파생 view로 만들며 원장이 아니다. 렌더링이나 링크 재확인은 accepted head·승인을 바꾸지 않는다.

Figma·DB·외부 서비스의 현재 상태는 저장된 이미지나 과거 hash로 증명할 수 없다. 원격 재확인이 요청되거나 필요한 경우 허용된 읽기만 수행하고 새 관찰 시각을 표시한다. 계정·권한·쿼터 오류를 “자료 없음”으로 쓰지 않는다.

결과가 없으면 어디까지 검색했고 무엇이 없는지, 해당 단계 진입점을 안내한다. 없던 설계·승인·테스트를 만들어 요청을 만족한 것처럼 보고하지 않는다.
