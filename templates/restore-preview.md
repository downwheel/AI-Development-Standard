# 소스 복원 미리보기 항목

snapshot의 원본 bytes가 실제 보존돼 있는지 확인하고 공개 restore plan의 내용을 사용한다. 이 문서만으로 적용 승인을 만들지 않는다.

## 목표와 현재 상태

실제 snapshot ID·manifest hash·정책/완전성·제외, 현재 제품 루트·baseline·보존된 사용자 변경을 표시한다.

## 변경 계획

경로 | 작업(추가/수정/삭제) | before/target hash | 충돌 | 영향

별도 빈 폴더 export·검증 결과, 실제 계획 ID/digest, 사전 사본·journal·적용 후 검증·부분 실패 복구를 설명한다.

## 결정 범위와 한계

구체적 계획에 대한 실제 사용자 승인 여부를 확인한다. 제품 Git 관리 정보·DB/Figma/SaaS·비밀·제외 데이터는 복원 범위가 아니다. 적용 후 소스가 바뀌면 기존 plan을 그대로 쓰지 않는다.

## 결과

preview/export/apply/partial을 구분하고 실제 바뀐 파일·receipt·복구 필요·다음 검증을 표시한다.
