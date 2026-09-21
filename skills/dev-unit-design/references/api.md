# API profile

고정된 시스템/요구 pins와 현재 공개 API·DTO·인가 규칙을 먼저 읽는다. 완결된 endpoint 또는 메시지별 계약을 작성한다.

- 경로/메서드 또는 이벤트 이름, 호출자, 인증 수단과 리소스/tenant별 인가, 입력 source와 validation.
- 필수/선택/nullable·길이/형식/범위·enum·default·날짜/숫자 표현·content type.
- 정상 응답과 실패 code/status/body, 사용자 공개 메시지와 내부 진단 분리.
- pagination/filter/sort와 안정적인 순서, timeout/cancellation, 필요한 idempotency·재시도·중복·동시성 정책.
- 하위 호환성과 versioning, 기존 호출부/타입/schema/generated client 영향.
- 관측 가능한 correlation ID·지연/오류와 비밀/개인정보 제외.
- validation·권한·외부 의존성 실패에 대한 요청/응답 예시와 독립 expected result.

OpenAPI/JSON Schema 등 기존 프로젝트 계약 형식을 우선한다. 공개 스키마는 실행 중 입력 검증과 어떻게 연결되는지 적는다. TypeScript 타입만으로 런타임 외부 입력 검증을 대신하지 않는다.

실제 SDK와 설치 버전을 확인하고 공식 문서로 메서드/옵션을 검증한다. mock은 계약 예시임을 표시한다. 서비스가 없는데 endpoint가 이미 실행되는 것처럼 쓰지 않는다.

인계에는 requirement/case ID, schema·오류 표·호출부 영향·필요 fixture·권한 실패·경계값과 실행할 검사의 의도를 담는다. 설계 단계에서 운영 endpoint를 변경하거나 계정을 생성하지 않는다.
