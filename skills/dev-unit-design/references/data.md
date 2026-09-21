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

## 2.1 정량 DB 계약

정확한 unit/environment refs로 `db-work-plan`을 만든다. 실제 공개 schema를 먼저 읽고 다음 내용을 채운다.

| 영역 | 승인 자료에 넣을 실제 기준 |
|---|---|
| 대상 | profile/역할 probe, DB 엔진·버전, target ref, schema, 계정/권한 digest |
| 변경 객체 | 전체 schema·종류·이름·action, 실제 기존 정의 hash 또는 expected_absent, 의존/간접 영향 |
| 실행 순서 | migration ID/order, typed operation, generator, SQL와 인자 hash, 예상 DB 차이 |
| 데이터 | 정확한 키/fixture namespace·owner, expected_rows/max_rows, 보존할 불변 조건 |
| 비용/한도 | statement·transaction·lock timeout, batch/관찰 행 수, catalog 수, 재시도 정책 |
| 검증/복구 | case IDs와 독립 oracle, 전후 관찰·commit 후 새 연결 검증, cleanup, transaction 복구와 백업 여부 |

`preview_database`는 지원되는 typed operation에서 승인 전에 SQL preview와 hash를 만든다. 이 preview는 개인 설계 산출물로 보존하고 실제 실행은 고정한 operation/generator/SQL/인자 hash에 일치해야 한다. 사전 구현을 위해 제품 파일을 만들지 않는다. 프로젝트 migration 파일을 생성할 경우 해당 파일/action도 scope에 넣는다.

현재 첫 SQL Server 어댑터의 실행 범위는 **create_table, create_index, 정확한 키를 지정한 fixture insert/update/delete**다. 임의 SQL·dynamic SQL·저장 프로시저/트리거/권한 변경·파괴적 DDL·비트랜잭션 작업까지 지원한다고 설명하지 않는다. 객체 목록에는 의존 객체를 표시할 수 있지만 실행 지원 여부는 실제 validator가 결정한다. 지원되지 않는 계약은 설계에 한계를 표시하고 실행 전 별도 어댑터/검증 설계로 해결한다.

현재 행/배치/관찰 상한, 잠금/시간 한도와 재시도 0 등의 정확한 수치는 공개 schema를 따른다. 성능 기준이 필요하면 측정 방법과 고정 부하를 설계한다. 작은 CRUD에서 별도 부하 시험이 적용되지 않으면 N/A 이유를 남긴다. migration 소요 시간만으로 전체 화면/서비스 처리 성능을 검증했다고 하지 않는다.

DB 객체/action/baseline 목록을 `scope-manifest.db_objects`와 정확히 맞춘다. 사용자에게 예상 객체 수·행 수·실행/보존/cleanup 범위를 보여주고 Gate B에서 같은 계획을 승인받는다. 실행기가 commit 전에 상한과 catalog 차이를 검사하고 실패하면 transaction rollback하며 commit 이후 독립 관찰 실패는 이미 commit된 상태를 숨기지 않는다.

기존 DB와 미제공 DDL을 추측해서 확정하지 않는다. 이 단계에서는 DB 변경이나 운영 데이터 갱신을 수행하지 않는다. 후보 query 실행 근거가 없으면 성능을 검증했다고 쓰지 않는다.

결과를 requirement/case ID와 API/UI 소비 계약에 연결한다. 적용 전후 호환성·실패·제약 위반·경계값·동시성 기대를 테스트 설계에 전달한다. 로컬 source snapshot은 DB 상태 백업/복원이 아니다.
