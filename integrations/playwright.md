# Microsoft Playwright MCP

확인일: 2026-09-21. Playwright MCP는 브라우저 조작과 구조 관찰을 제공한다. 공식 저장소에는 Node.js 요구사항, 호스트별 연결, 격리/지속 profile 설정이 있다. [공식 저장소](https://github.com/microsoft/playwright-mcp)

## 개인 연결

현재 호스트에 이미 브라우저 제어 도구가 있으면 필요한 기능을 확인한다. 추가 Playwright MCP가 필요하면 공식 client 안내에 따라 설치 버전을 정하고 개인 설정에 등록한다. 공통 원본에 자동 `latest` 실행 설정을 강제하지 않는다.

팀 기본은 검사 전용 격리 환경이다. 공식 `--isolated` 옵션은 session 상태를 메모리에 두며 종료 때 잃는다. 지속 profile을 여러 client가 공유하면 충돌할 수 있다. 기존 로그인 세션 연결은 별도 명시된 선택으로 둔다. cookie/storage-state는 비밀처럼 개인 영역에 관리한다.

허용된 테스트 URL에서 페이지 열기·구조 snapshot·스크린샷 같은 최소 기능을 확인하고 실제 결과를 기록한다. 연결 확인을 제품 기능 테스트 통과로 표시하지 않는다.

## 작업 연결

현재 UI 조사, 테스트 시나리오 탐색, 실패 재현, screenshot/trace 관찰에 사용한다. 반복할 회귀 검사는 해당 프로젝트의 테스트 파일과 runner로 남긴다. MCP 대화에서 한 번 성공한 조작만으로 지속 검증을 완료하지 않는다.

공식 문서에는 CLI+Skills 대안도 있으므로 성능과 context 비용이 중요하면 실제 작업에 맞게 비교한다. MCP 호출 횟수를 성과 지표로 삼지 않는다. 테스트 대상·권한·viewport·fixture·기대값·관찰 시각을 고정하고 운영 쓰기나 개인 세션 변경으로 범위를 넓히지 않는다.
