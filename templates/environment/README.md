# 개인 환경 프로필

이 폴더에는 실제 서버 주소·계정·암호가 없는 공통 템플릿만 둔다. `sqlserver.profile.json`은 `environment_plan`의 `profile`에 전달할 값이다. `environment_apply`는 선택한 개인 기록 루트의 `environments/<profile-id>/secrets/.env`에 빈 항목만 생성한다. 기존 파일은 그대로 보존한다.

사용자는 생성된 개인 `.env`를 로컬 편집기로 입력한다. 채팅, MCP 인자, Git, 소스 스냅샷, 일반 보고서로 실제 값을 복사하지 않는다. MCP에는 프로필 ID·revision·역할만 전달한다. `.env` 파서는 UTF-8의 단일 줄 `KEY=value`와 일치하는 따옴표만 지원하며 변수 확장·명령 실행·`export`·여러 줄 값은 거부한다. 선언하지 않은 키와 중복 키도 거부한다.

SQL Server의 역할은 `inspect`, `application`, `migration`, `fixture`이다. 각 역할의 별도 계정이 같은 실행 변수 `MSSQL_USER`, `MSSQL_PASSWORD`로 매핑되므로 애플리케이션 프로세스에 마이그레이션 암호를 전달하지 않는다. `MSSQL_AUTH=integrated`이면 현재 OS 계정을 사용하고 암호는 필요하지 않다. DB 주소·DB명·스키마·인증 방식은 target revision에 포함된다. 서버 인증서 검증을 사용하려면 `MSSQL_ENCRYPT=true`, `MSSQL_TRUST_SERVER_CERTIFICATE=false`로 입력한다. 해당 설정이 실제 서버에서 지원되는지 연결 관찰로 확인한다.

`environment_inspect`는 필수 항목의 존재 여부와 형식만 보여준다. `environment_probe`는 역할별 연결·대상·권한 관찰을 개인 receipt에 남긴다. 현재 SQL Server 어댑터와 ODBC 드라이버가 없거나 입력이 비어 있으면 차단 상태이며 연결 성공으로 보고하지 않는다. OAuth와 Codex·Claude·Git 로그인은 해당 서비스의 기본 계정 저장소에서 별도로 연결한다.

프로필 변경 또는 다른 대상 연결은 승인된 환경 계약을 갱신해야 한다. 같은 대상·권한 구성의 암호 교체는 새 연결 관찰로 검증한다. 개인 keyed HMAC 상태는 같은 폴더의 `secret-state.json`에만 남고 외부에는 무작위 revision ID만 제공한다. 앱 자체의 `.env` 로더가 주입값을 덮어쓰는지는 해당 프로젝트의 준비·실행 검증에서 확인해야 한다. 이 기능은 같은 OS 계정의 임의 프로그램 접근을 차단하는 보안 격리 장치가 아니다.
