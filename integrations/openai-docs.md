# OpenAI Docs MCP — OpenAI

OpenAI 제품/API·Codex 관련 기술 선택은 OpenAI Docs를 우선 사용한다. 이 서버는 공식 개발자 문서의 검색·조회 근거를 제공하며 프로젝트 실행이나 계정 설정 변경을 대신하지 않는다. [OpenAI 공식 Docs MCP 안내](https://developers.openai.com/learn/docs-mcp)

## 개인 호스트 준비

현재 호스트에 설치된 OpenAI Docs 관련 Skill과 실제 문서 조회 도구를 확인한다. Codex와 Claude Code에서 노출되는 이름이 같다고 가정하지 않는다. 기존 공식 연결이 있으면 재사용하고, 없으면 공식 안내의 현재 endpoint/지원 client 절차를 확인한다. 다른 서버의 토큰이나 설정 파일을 복사하지 않는다.

작은 공개 문서 질의로 검색·조회 기능을 확인한다. 문서 조회가 가능하다는 사실은 API key나 모델 호출이 준비됐다는 뜻이 아니다. 읽기 연결을 위해 제품 모델 호출·유료 개발 시험을 자동 실행하지 않는다.

## 사용과 기록

설계에서 필요한 정확한 제품/API/SDK 버전과 질문을 정하고 공식 원문을 조회한다. 프로젝트의 설치된 SDK·타입·공식 API 계약을 대조해 선택 근거를 system/unit의 library_docs 관찰에 남긴다. 문서 서비스가 unavailable이면 원인과 공식 웹 문서 대안을 함께 기록한다. 공식 문서가 설명하지 않는 기능을 추정해 구현하지 않는다. 도구명·입력 schema·source refs는 실제 응답에서 확인한다.
