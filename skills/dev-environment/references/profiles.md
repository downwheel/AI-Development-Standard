# 환경 프로필 연결 계약

## 값과 실행 역할

공통 템플릿에는 키와 형식만 있고 실제 값은 `<state>/environments/<profile-id>/secrets/.env`에 둔다. `profile.json`은 허용된 키·target 키·역할 매핑을 정의한다. `secret-state.json`은 개인 keyed HMAC 변경 감지 자료이며 발행·export 대상이 아니다.

SQL Server 템플릿의 역할은 `inspect`, `application`, `migration`, `fixture`이다. 각각 별도 사용자/암호 입력 키를 동일한 실행 변수 `MSSQL_USER`/`MSSQL_PASSWORD`에 매핑한다. 애플리케이션 역할이 마이그레이션 자격증명을 상속하지 않는다. `MSSQL_AUTH=integrated`는 현재 OS 신원을 사용하고 사용자/암호 매핑을 주입하지 않는다. 실제 권한은 probe로 확인한다.

`MSSQL_SERVER`, `MSSQL_DATABASE`, `MSSQL_SCHEMA`, `MSSQL_AUTH`는 대상 변경 감지에 포함된다. 드라이버는 실제 설치된 `MSSQL_DRIVER` 이름을 사용한다. `MSSQL_ENCRYPT=true`, `MSSQL_TRUST_SERVER_CERTIFICATE=false`는 서버 인증서 검증을 전제로 한다. 연결 시간은 `MSSQL_CONNECTION_TIMEOUT`의 지원 범위로 제한한다. 필수 항목이 비었으면 성공 상태로 진행하지 않는다.

프로필의 우선순위는 `profile-over-explicit-inheritance`다. OS 필수 변수와 명시적으로 허용한 비인증 변수만 상속한다. 키 이름에 따른 제외 목록만 믿고 전체 환경을 전달하지 않는다. 프런트엔드 역할이나 `VITE_*`, `NEXT_PUBLIC_*` 등 공개 변수에 secret을 매핑하면 거부한다. 앱의 자체 `.env` 로더가 이후 값을 덮어쓰지 않는지는 실제 실행/연결 대상 검증으로 확인한다.

## 파서와 기록

선택한 한 파일만 읽는다. UTF-8, 한 줄의 `KEY=value`, 주석 줄과 단일/이중 따옴표로 감싼 문자 값만 지원한다. 변수 확장, 셸 치환, `export`, 중복 키, 미선언 키, 여러 줄 값은 지원하지 않는다. 오류에는 키 이름·행 번호·오류 종류만 남긴다.

CLI/MCP의 입력과 공개 결과에는 ID와 revision, 키 존재/형식, 역할별 연결 관찰만 사용한다. 내부 resolver 결과와 원문 값은 일반 JSON으로 직렬화하지 않는다. 알려진 주입 값은 실행 로그와 text/JSON 증거 저장 전에 마스킹한다. 바이너리 screenshot/trace는 현재 첨부 어댑터가 보장하지 않으므로 별도의 검토 없이 안전한 증거라고 선언하지 않는다.

SQL Server probe의 실제 대상과 권한 관찰은 개인 receipt에 보관한다. 대상·역할 구성이 바뀌면 새 승인 계약이 필요하며, 비밀만 교체하면 현재 역할에 대한 새 성공 probe가 필요하다. 여러 역할을 사용하는 계약은 역할마다 receipt를 고정한다.

같은 OS 계정에서 실행되는 임의 프로그램·외부 SQL 클라이언트까지 차단하는 기능은 아니다. 호스트 OAuth, Codex/Claude 로그인, Git 계정 연결을 이 `.env`에 복사하지 않는다. 계정 연결이 미뤄져도 공개 문서/소스 조사·빈 프로필 준비 등 독립 작업은 계속한다.
