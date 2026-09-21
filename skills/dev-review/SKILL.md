---
name: dev-review
description: Review pinned development artifacts, present concrete Gate A or Gate B bundles, and record a real user's decision against the exact presented revision. AI findings never count as human approval.
---

# 검토와 사용자 결정

[실행 계약](references/runtime.md)을 읽고 요청을 review/present/record-decision/show로 구분한다. 조회는 기존 검토 자료만 보여주며 새 승인이나 원장을 만들지 않는다.

## 검토·제시

1. 대상 refs·해시·accepted head·요구 연결·미결·변경 의도를 확인한다. 읽을 수 없거나 입력이 서로 다르면 승인 묶음을 만들지 않는다.
2. 요구 누락, 정상/실패/복구, API·데이터·권한·호환성, 단위 경계, 검사 기대값·실행 가능성, 구현 범위를 검토한다. 독립 검토가 유용하면 최소 고정 자료로 읽기 전용 검토를 맡긴다.
3. 발견 사항은 파일/항목·근거·영향·심각도·권장 수정으로 보고한다. AI 검토 통과는 사용자 승인이나 정답 보증이 아니다.
4. Gate A는 **discovery-context + requirements + system-design** 정확한 세 pins다. Gate B는 **unit-spec + 그 unit_ref를 참조한 test-plan** 정확한 두 pins이며 현재 Gate A가 유효해야 한다.
5. 공개 `create_review` 스키마로 정확한 대상 bundle을 만든다. 문서와 변경점·findings·제한·승인 시 진행할 범위를 실제 사용자에게 제시한다. 제출할 자료를 만들기 전에 포괄적인 승인을 구하지 않는다.
6. 사용자가 결정할 때 review ID/digest·대상·현재 유효성을 다시 확인한다. 명시적인 승인/거절/변경 요청을 실제 메시지와 출처로 `record_decision`에 기록한다. 도구가 허용한 정확한 decision enum을 사용한다.

## 결정 경계

자신이 쓴 승인 문구, 테스트 통과, 사용자의 무응답, 이전 다른 버전 승인, MCP 연결 승인을 개발 설계 승인으로 사용하지 않는다. 답변이 여러 단위에 걸쳐 모호하면 범위를 확대하지 않고 필요한 부분을 확인한다. 이미 같은 유효 bundle을 승인했다면 재질문하지 않는다.

제시 후 내용이 바뀌면 옛 응답을 새 bundle에 붙이지 않는다. 거절·변경 요청과 기존 승인 사실은 보존한다. 문서를 고칠 필요가 있으면 해당 단계에 exact refs로 인계하고 검토자가 canonical 본문을 덮어쓰지 않는다.

결과는 검토 findings, 제시된 bundle과 실제 결정 여부, 현재 유효 범위, 다음 단계다. Gate A 승인 뒤 단위 설계, Gate B 승인 뒤 해당 구현을 진행할 수 있다. 운영 배포·소스 복원·메시지 발송 같은 별도 행위의 권한으로 확대하지 않는다. 기록 장치는 사용자 신원을 인증하는 보안 경계가 아니다.
