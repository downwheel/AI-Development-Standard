# Figma MCP Server — 연결과 native 산출물

확인일: 2026-09-21. 공식 문서는 remote server와 native canvas 쓰기, 전문 Skill 사용을 안내한다. 연결 가능 client는 공식 MCP Catalog에서 확인한다. 서버별 노출 기능과 계정·파일 권한·사용 한도는 실제 환경에서 확인해야 한다. [Figma 소개](https://developers.figma.com/docs/figma-mcp-server/), [Remote 연결](https://developers.figma.com/docs/figma-mcp-server/remote-server-installation/)

## 개인 연결

1. 현재 호스트의 지원 목록과 remote 연결 가이드를 확인한다.
2. 이미 설치된 Figma 플러그인/MCP가 있으면 이를 사용하고 중복 연결하지 않는다.
3. 공급자의 로그인/권한 화면에서 개인 계정을 연결한다. 토큰을 팀 파일·채팅 보고서에 복사하지 않는다.
4. 필요한 파일을 지정해 읽기 가능한지 확인한다. 쓰기 확인은 사용자가 허용한 파일/범위에서 한다.
5. 호스트에 맞는 Figma 전문 Skill이 있으면 실제 쓰기 동작 전에 읽는다. 계정 연결만으로 편집 기능까지 확인됐다고 보고하지 않는다.

## 기본 적용과 차단

새 UI 작업은 Figma를 먼저 사용하는 preferred가 기본이다. 시스템 설계의 tool_plan에서 적용 unit과 로컬 대체 허용 범위를 Gate A에 제시한다. 편집 가능한 Figma가 명시 요구이면 required, 사용자가 명시적으로 로컬 설계를 선택하면 local_only다. 도구가 없다는 이유만으로 local_only나 not_applicable을 선택하지 않는다.

preferred는 실제 Figma 호출 실패/미노출/권한·쿼터 차단을 기록한 뒤 Gate A에 승인한 HTML/SVG 배치안과 화면 계약으로 대체할 수 있다. required이면 로컬 초안을 제공하더라도 필수 native 결과 완료는 보류한다. 새 계정 사용·권한 확대·결제·다른 서비스로의 이전을 자동 해결책으로 실행하지 않는다.

호출 rate limit, 저장 공간/파일 생성 제한, 파일별 읽기/편집 권한은 서로 다른 관찰이다. 공급자가 반환하지 않은 잔여 용량·호출량은 추정하지 않는다. [공식 권한·한도 안내](https://developers.figma.com/docs/figma-mcp-server/rate-limits-access/)를 현재 실제 결과와 대조한다.

## 작업 연결

시스템 설계는 필요한 구조도, 단위 UI 설계는 frame/component/variant/variables와 상태별 배치, 구현은 승인 노드의 문맥과 실제 코드 대응에 사용한다. 생성 후 구조 조회와 screenshot으로 편집 가능성·배치·주요 상태를 확인한다.

빈 파일·이미지 한 장·존재하지 않는 링크를 native 화면 설계로 표시하지 않는다. 입력/결과 file/node 참조·관찰 시각·실제 도구 결과를 개인 산출물에 보존한다. Figma 필수인데 권한/쿼터로 쓰지 못하면 원인을 알리고 필수 결과의 완료를 보류한다. 원격 링크는 그 이후 편집 상태의 동일성이나 소스 snapshot 복원을 보장하지 않는다.
