---
name: dev-restore
description: Export preserved source snapshots, prepare a concrete restore preview, and apply only a currently approved restore plan with conflict checks and recovery evidence. Use for explicit source recovery, not document revision or Git rollback.
---

# 소스 복원

[실행 계약](references/runtime.md)을 읽는다. 기본은 개인 snapshot의 export와 preview다. “과거 결과 보여줘”는 `dev-artifacts`로 처리한다. Gate A/B나 일반 설계 승인은 원본 파일 덮어쓰기 승인이 아니다.

## 실행

1. 실제 project/workspace와 snapshot ID·manifest·보존 정책·완전성·제외 범위를 확인한다. hash만 있고 bytes가 없으면 복원 가능하다고 말하지 않는다.
2. 공개 snapshot/export/restore operation을 describe한다. 실제 구현이 제공하지 않는 옵션·복원 종류를 추측하지 않는다.
3. `export_snapshot` 또는 동등한 공개 기능으로 제품 밖의 새 빈 폴더에 재현하고 bytes/파일 목록/hash를 검증한다. 기존 폴더를 덮어쓰지 않는다.
4. `plan_restore`로 현재 source와 target snapshot을 비교한다. 실제 대상 루트, 추가/수정/삭제 경로, before/target hash, 제외·충돌·한계, 직전 사본·실패 복구 계획을 확인한다.
5. 이 구체적 계획과 diff를 사용자에게 보여준다. 같은 계획에 현재 유효한 명시적 승인이 있으면 반복해서 묻지 않는다. 없으면 원본 적용에 필요한 결정을 받는다.
6. `record_restore_decision`의 실제 schema에 review 대상·사용자 메시지/출처를 맞춰 기록한다. 적용 직전 현재 소스·경로·정책·writer·미해결 journal을 다시 확인한다. 달라졌으면 새 계획이 필요하다.
7. `apply_restore`로 승인 경로만 적용한다. 직전 사본과 write-ahead journal 확보를 우회하지 않는다. 현재 변경과 충돌하면 멈춘다. 제품 Git index/refs/config를 복원 대상에 넣지 않는다.
8. 적용 결과·post source·파일별 실패·새 receipt·검증 필요 범위를 기록한다. `dev-verify`에 현재 소스 기준으로 인계한다.

## 실패·재호출

부분 적용은 실제 변경 목록과 복구 근거를 보여주고 추가 관리 쓰기를 멈춘다. `reconcile_recovery`는 실제 공개 기능·현재 journal 상태·기존 허용 범위를 확인하여 사용한다. 불분명한 사용자 변경을 자동 rollback으로 덮어쓰지 않는다.

DB의 불확실한 commit 결과는 소스 복원과 분리한다. controller 종료를 확인한 뒤 `plan_database_recovery`의 읽기 관찰 자료를 사용자에게 보여 주고 실제 응답만 `record_database_recovery`로 기록한다. 수락은 원래 결과·변경 요청을 보존하고 새 설계·승인으로 연결한다. 이 기능은 DB 백업 복원이나 SQL 자동 재시도가 아니다.

동일 request ID 재전달은 기존 operation 결과를 조회하며 삭제/적용을 중복 실행하지 않는다. baseline 변경은 옛 plan의 계속 적용 사유가 아니다. snapshot 조회·export 성공과 원본 적용 성공, 복원 후 제품 테스트 통과를 따로 보고한다.

DB·Figma·SaaS·운영 서버·비밀·제외된 파일은 소스 snapshot으로 복원되지 않는다. 개인 history tip과 과거 승인·attempt를 되감지 않는다. 제품 Git reset/revert/checkout/stash/restore를 복원 실행기로 쓰지 않는다.
