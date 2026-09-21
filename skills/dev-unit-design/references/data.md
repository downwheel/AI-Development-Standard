# Data profile

먼저 해당 프로젝트의 DB/파일/캐시 역할과 기존 schema·migration·query·권한을 읽는다. 특정 DB 제품이나 기존 다른 프로젝트 연결을 자동 선택하지 않는다.

## 조사와 설계

DB MCP는 허용된 대상·읽기 계정인지 확인한다. metadata→필요 집계→제한 표본 순으로 좁힌다. 시간·행·반환 크기 상한을 적용하고 행 제한만으로 쿼리 부하가 안전하다고 가정하지 않는다. 관련 없는 DB·테이블을 전수 조사하지 않는다. 비밀과 원문 업무 데이터 대신 schema·마스킹된 집계 근거를 남긴다.

다음 중 필요한 내용을 결정한다.

- entity·키·관계·null·unique·check·외래키·보존/삭제 규칙, 시간/단위/precision 의미.
- 조회/쓰기 경로, index 선택 근거와 예상 부하, pagination·동시성·transaction·잠금 경계.
- 개인정보/tenant 분리·접근 권한·암호화/마스킹·감사 요구.
- 기존 데이터와 호환성, migration 단계·backfill·실패 복구·배포 순서·구버전 공존.
- 검증 데이터·비운영 fixture·성능 확인 범위·schema/data consistency 검사.
- rollback이 실제로 가능한지, 손실/비가역 구간·보완 계획·운영 승인 필요 범위.

기존 DB와 미제공 DDL을 추측해서 확정하지 않는다. 설계에는 ERD/DDL/query 후보를 포함할 수 있으나 실제 DB 변경이나 운영 데이터 갱신은 수행하지 않는다. 후보 query 실행 근거가 없으면 성능을 검증했다고 쓰지 않는다.

결과를 requirement/case ID와 API/UI 소비 계약에 연결한다. 적용 전후 호환성·실패·제약 위반·경계값·동시성 기대를 테스트 설계에 전달한다. 로컬 source snapshot은 DB 상태 백업/복원이 아니다.
