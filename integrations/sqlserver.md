# SQL Server 정량 작업 어댑터

구현: `harness/database.py` / 계약: `DB_WORK_PLAN_SCHEMA` / generator: `team-sqlserver-2.1`.

이 어댑터는 사용자별 환경 profile과 승인한 DB 작업 계획을 연결한다. 기존 `maritime_sql`의 접속 정보나 다른 프로젝트의 `.env`를 자동으로 사용하지 않는다. 개인 profile에 선택한 개발·시험 DB를 설정하고 실제 연결 확인을 수행해야 한다.

## 지원 범위

| 동작 | 실행 조건과 관찰 |
|---|---|
| DB 조사 | 지정 schema의 정확한 테이블 목록, 객체 정의·primary key·행수·내용 hash. 업무 행 원문은 반환하지 않음 |
| 테이블 생성 | 명시적 컬럼·길이·NULL 여부·primary key. 생성 후 실제 정의 비교 |
| 인덱스 생성 | 명시적 컬럼 순서·unique 여부. 부모 테이블 baseline과 인덱스 부재 확인 |
| 행 삽입 | 모든 컬럼을 명시한 행, 기존 key와 충돌하지 않는 primary key |
| 행 수정·삭제 | 관찰한 primary key 전체를 지정한 정확한 key 목록. 임의 WHERE 식은 허용하지 않음 |
| fixture 정리 | 해당 실행이 새로 삽입한 행의 primary key·owner namespace만 삭제. 기존 행 내용과 별도 연결에서 정리 결과 확인 |
| 재관찰 | 완료 receipt의 실제 catalog·행 내용과 현재 DB를 별도 연결로 비교 |

지원 타입은 `int`, `bigint`, `smallint`, `tinyint`, `bit`, `nvarchar`, `varchar`, `uniqueidentifier`이다. 문자열은 명시적 길이, `bit`는 JSON boolean, UUID는 소문자 표준 형식이다. 코드 페이지에 따라 달라지는 손실 변환을 피하기 위해 `varchar`에는 ASCII 문자열만 허용한다. Unicode 데이터에는 `nvarchar`를 사용한다.

실행 계획 하나는 최대 100개의 순서가 고정된 migration을 가진다. 한 단위에서 같은 target에 여러 독립 계획을 실행하면 먼저 실행한 결과의 현재성이 달라지므로, 같은 target의 작업은 하나의 계획 안에 순서대로 구성한다.

## 승인과 실행 순서

1. `dev-environment`에서 개인 profile을 만들고, 사용자가 개인 `secrets/.env`의 실제 값을 입력한다. 비밀 값은 대화에 붙여 넣지 않는다.
2. migration 또는 fixture 역할로 연결을 확인하고, `inspect_database`로 지정 테이블의 실제 target·engine version·권한·객체·행 baseline을 얻는다.
3. 단위 설계에서 `db-work-plan`을 작성한다. 요구·검사 ID, environment/unit refs, 객체 action, baseline, 예상·최대 행수, 시간·lock·batch 한도, 보존·복구·정리 조건을 포함한다.
4. `preview_database`가 만드는 SQL 문자열과 SHA-256을 계획에 고정한다. `source_path`는 앞으로 생성·수정할 제품 SQL 파일의 상대 경로이며 scope에도 같은 파일이 있어야 한다. SQL은 UTF-8, BOM 없음, LF 개행 및 마지막 개행 한 개를 포함한 **반환 문자열 그대로** 저장한다. 매개변수는 SQL에 문자열로 삽입하지 않고 고정된 구조화 계획에서 별도 전달한다.
5. `render_plan`으로 만든 범위표에는 SQL, 매개변수 hash, 정확한 행·key·fixture 내용, 실행 한도가 모두 표시된다. 사용자 Gate B가 동일 refs를 승인한 뒤에만 제품 SQL 파일을 생성한다.
6. 실행 경계는 제품 SQL 파일 hash, 승인 scope와 DB 계획, 환경 revision을 대조한다. 어댑터는 실제 target·principal digest·권한·engine version과 baseline을 다시 검사한다.
7. transaction 및 application lock 안에서 typed operation을 실행한다. 실제 객체 diff와 행수·key·내용·기존 행 보존을 commit 전에 검사한다. 초과나 불일치가 있으면 rollback한다.
8. commit 뒤 새 연결에서 영속 결과를 관찰한다. fixture 정리는 별도 transaction과 새 연결로 확인한다. 소스 파일 복원은 DB 복구를 대신하지 않는다.

원문 SQL을 받는 실행 도구는 제공하지 않는다. 계획에는 생성한 SQL 및 구조화 매개변수의 별도 hash가 있고, SQL 파일을 편집했거나 입력 값이 바뀌면 같은 승인으로 실행되지 않는다.

## 실행 한도와 실패 기록

- 최대 관찰 행수는 테이블당 1,000행이다. `max_observed_rows`는 실제 전체 테이블 기준이며 일부 행만 보고 전체 보존을 검증했다고 하지 않는다. 큰 업무 테이블에 같은 방식을 억지로 적용하지 않는다.
- 최대 catalog 객체 수는 5,000개, 한 batch의 최대 변경 행수는 1,000행이다. 실제 계획은 이 상한 이하에서 더 작은 값을 명시한다.
- statement timeout 최대 300초, 전체 DB 작업 budget 최대 900초, lock 대기 최대 30초이다. 지원 ODBC 드라이버의 query timeout과 단계 사이 경과 시간 검사를 함께 적용한다. 이는 별도 OS 프로세스를 강제 종료하는 격리 장치가 아니다.
- 자동 retry는 0회이다. commit 응답을 받지 못하면 결과가 `unknown`일 수 있으며, “변경 없음”으로 바꾸거나 같은 쓰기를 자동 재시도하지 않는다. 새 조사와 복구 판단이 필요하다.
- `committed`, `commit_outcome`, `rollback`, `cleanup`은 각각 별도 기록이다. commit 이후 관찰 실패도 실제 반영 사실을 보존한다.
- performance의 실행 지원 지표는 전체 작업 경과 시간이다. 동시성·부하·백분위 latency 등 제품 성능 시험은 별도의 승인된 test-plan에서 실행한다. 작은 CRUD는 사유를 적은 N/A가 가능하다.
- inspector와 실행기 모두 실제 비밀·연결 문자열·원문 드라이버 오류를 반환하지 않는다. 객체명·설계한 fixture 값은 사용자 검토 자료에 들어가므로 민감한 업무 데이터나 인증 값을 fixture로 사용하지 않는다.

## 별도 어댑터 검토가 필요한 작업

임의 SQL, 동적 SQL, procedure/view/trigger 변경, FK·constraint 추가/변경, role/grant, 기존 객체 alter/drop, identity/default/computed/temporal/memory-optimized/filetable, CDC·복제·암호화·마스킹·행 수준 보안, 활성 trigger 또는 cascading FK가 있는 테이블의 DML, 대규모 데이터 작업은 현재 실행 subset에 포함되지 않는다. 필요하면 해당 개발 범위를 중단 표시하고 실제 영향과 복구를 검증할 수 있는 별도 adapter를 설계한다. 지원 여부를 정규식으로 추측하여 통과시키지 않는다.

완전한 catalog 관찰에는 선택한 DB의 `VIEW DEFINITION`이 필요하다. 실제 쓰기 권한은 승인한 schema·object와 동작에 한정한다. `db_owner` 또는 전체 DB 쓰기 권한을 기본 요구하지 않는다. application 역할에 migration 자격증명을 넣지 않는다. 같은 OS 사용자나 DB 외부 writer 전체를 통제하는 보안 경계는 아니다.

## 런타임과 검증 구분

Python 런타임에 `pyodbc`와 Microsoft ODBC Driver 17 또는 18 for SQL Server가 필요하다. 없으면 설치 필요 상태를 반환하며 함수가 임의 설치를 진행하지 않는다. 연결 방식은 SQL 비밀번호 인증 또는 Windows 통합 인증이다. 통합 인증에는 불필요한 비밀번호를 요구하지 않는다. 기본 암호화는 켜고 서버 인증서 신뢰 우회는 끈다.

`python -m unittest tests.test_database -v`는 격리된 가짜 DB adapter 및 DB-API 경계를 검사한다. 이 시험의 성공은 실제 SQL Server의 DDL·권한·연결·transaction 동작 검증 성공을 뜻하지 않는다. 실제 DB 프로필을 연결한 뒤 승인된 개발·시험 DB에서 별도 통합 검증을 기록한다.

구현에서 확인한 1차 자료:

- [Microsoft: sp_getapplock](https://learn.microsoft.com/en-us/sql/relational-databases/system-stored-procedures/sp-getapplock-transact-sql): transaction 소유 application lock과 반환 코드.
- [Microsoft: SET XACT_ABORT](https://learn.microsoft.com/en-us/sql/t-sql/statements/set-xact-abort-transact-sql): transaction 오류 처리.
- [pyodbc: cursor 구현](https://github.com/mkleehammer/pyodbc/blob/master/src/cursor.cpp), [cursor timeout 변경 논의](https://github.com/mkleehammer/pyodbc/issues/1217): query timeout은 cursor 생성 시 적용하므로 남은 budget에 따라 cursor를 새로 만든다.
