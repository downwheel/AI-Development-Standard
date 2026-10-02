# 기본 외부 도구

팀 스킬과 별도로 아래 5개 기능을 기본 구성한다. `scripts/configure_tools.py`는 지정한 호스트에 없는 설정만 추가한다. 기존 같은 이름의 연결은 보존하며 비표준 연결·비활성 상태는 검토 대상으로 보고한다. 개인 설정 전체나 자격 증명을 Git에 복사하지 않는다.

| 기능 | 기본 배포 방식 | 역할 | 사용자별 준비 |
|---|---|---|---|
| Figma | 공식 원격 MCP | 화면 설계, 디자인 정보 조회·연계 | Figma 계정 OAuth 및 파일 권한 |
| Context7 | 고정 버전 npm MCP | 현재 라이브러리 문서·API 근거 조회 | Node.js. 기본은 익명 사용이며 사용량 한도가 적용될 수 있음 |
| Awesome Design | 공통 `awesome-design-md` 스킬과 공개 디자인 참조 74개 | 디자인 규칙과 시안을 구체화 | 계정 불필요 |
| GitHub | 공식 원격 MCP | 저장소·이슈·PR 연계 | `GITHUB_PAT_TOKEN` 환경 변수, 필요한 저장소 권한 |
| Playwright | 고정 버전 npm MCP | 실제 브라우저 기능·화면 검증 | Node.js, Windows Edge 또는 다른 OS Chrome |

정확한 npm 버전과 주소는 `integrations/default-tools.json`이 기준이다. Node.js 20.18.1 이상과 npm의 `npx-cli.js`가 필요하다. Figma·GitHub HTTP 연결과 디자인 스킬은 Node 없이도 설정할 수 있다. Node가 없으면 나머지를 누락 처리하지 않고 미완료로 보고한다.

## 설치와 갱신

해당 호스트의 팀 스킬을 먼저 설치한다. 저장소 루트에서 `--host codex` 또는 `--host claude`를 선택한다.

```powershell
python -B -X utf8 scripts/configure_tools.py --host codex
python -B -X utf8 scripts/configure_tools.py --host codex --apply --prepare-runtime
```

Claude Code는 위 명령의 `codex`를 `claude`로 바꾼다. 비표준 프로필이면 `--home "<실제 프로필 절대경로>"`, 실행 파일 검색이 안 되면 `--codex-bin`, `--node-bin`, `--npx-cli`에 확인한 경로를 전달한다. 값에 사용자 계정·특정 드라이브 경로를 고정하지 않는다.

설정 방식은 다음과 같다.

- Codex: 사용자 `config.toml`에 없는 MCP 테이블만 추가한다. CLI로 기존 구성을 읽고 추가 후 다시 확인한다. 기존 내용은 바이트 그대로 보존한다.
- Claude Code: 사용자 `.claude.json`의 `mcpServers`에 병합한다. 기본 위치는 사용자 홈의 `.claude.json`이며 `CLAUDE_CONFIG_DIR` 또는 별도 프로필을 지정하면 해당 폴더의 `.claude.json`을 사용한다. 기존 JSON 항목은 유지한다. 프로젝트 `.mcp.json`, `.claude/settings.json`, 권한 허용 목록은 변경하지 않는다.
- npm 실행은 확인한 Node와 `npx-cli.js`의 절대 경로를 사용해 Windows shell 인용 문제를 피한다. cache는 Workspace의 `results/tool-runtime/npm-cache`에 둔다.
- Playwright는 격리·headless 모드로 시작하고 산출물은 Workspace의 `results/browser`에 둔다. `--no-sandbox`나 모든 파일 접근 허용을 추가하지 않는다.
- Awesome Design은 팀용 호출 지침과 공식 공개 디자인 문서를 묶은 이식 가능한 스킬이다. Figma 계정이 없어도 로컬 시안을 설계할 수 있다. Codex 마켓플레이스 플러그인을 복제한 패키지는 아니다. 출처 revision과 MIT 고지는 `SOURCE.json`과 `LICENSE`에 유지한다.
- 변경 전 파일은 `<profile>/team-tools-backups`에 백업하고 디자인 스킬 소유권은 `team-tools-receipt.json`으로 관리한다. 개인 수정은 덮어쓰지 않는다. 백업에는 개인 설정이 포함될 수 있으므로 공유하지 않는다.

현재 호스트에서 동일 기능의 활성 플러그인 또는 별도 실행기를 **실제로 확인한 경우에만** `--provided awesome-design`, `--provided playwright` 등을 반복 지정해 중복 구성을 피한다. 플래그는 인증이나 실제 도구 호출 성공의 증거가 아니다. 업데이트 때도 실제 활성 여부를 다시 확인한다. 기존 provider의 버전·전송 방식을 자동 교체하지 않으므로 보고된 비표준 연결은 별도로 점검한다. 비활성 연결은 이 플래그로 정상 처리하지 않는다.

`--prepare-runtime`은 표준 npm 패키지를 내려받아 실행 준비를 확인한다. 브라우저 실행 또는 OAuth 완료를 의미하지 않는다. 실패 또는 필수 실행 환경 누락 시 미완료 항목과 종료 코드 2를 반환한다. 설정된 연결을 일괄 삭제하거나 기존 플러그인을 제거하지 않는다.

## 인증과 실제 사용 확인

**Figma**: Codex에서는 `codex mcp login figma`, Claude Code에서는 새 세션의 `/mcp`에서 Figma 인증을 진행한다. 사용자 동의가 필요한 브라우저 로그인을 AI가 대신 완료했다고 보고하지 않는다. 사용자가 제공한 접근 가능한 파일로 조회를 확인한다. Figma가 없거나 권한이 없으면 기존 디자인 패턴과 로컬 HTML/이미지 시안으로 설계를 진행한다.

**GitHub**: 사용자가 필요한 저장소에 최소 권한을 가진 PAT를 만들어 `GITHUB_PAT_TOKEN` 환경 변수에 저장한다. 토큰을 대화·Git·명령 인자·보고서에 붙이지 않는다. 새 호스트 프로세스가 환경 변수를 상속하도록 다시 연 뒤 읽기 작업으로 연결을 검사한다. 설정에는 Codex의 `bearer_token_env_var`, Claude의 `${GITHUB_PAT_TOKEN}` 참조만 들어간다. MCP가 연결되어도 commit/push·PR 게시·외부 발송 권한은 자동 부여되지 않는다.

**Context7**: 실제 `resolve-library-id`와 문서 조회를 수행해 확인한다. 사용량 제한이면 사용자 계정 정책에 따라 API 키 또는 기존 원격 연결을 설정한다. 익명 사용 가능성과 무제한 사용을 혼동하지 않는다.

**Playwright**: `browser_navigate`로 안전한 로컬 테스트 페이지를 열고 스냅샷을 확인한다. Windows에서는 설치된 Edge를 사용한다. 다른 OS에서는 Chrome 설치 여부를 확인한다. 브라우저가 없으면 브라우저 설치가 미완료임을 보고하고 공식 절차로 준비한다. 제품 검증은 사용자가 지정한 테스트 URL과 실제 변경 반영 여부를 확인한 뒤 수행한다.

**Awesome Design**: 호스트의 스킬 목록에서 인식을 확인한다. 설계할 때 기존 프로젝트 규칙을 우선하고 필요한 참조만 읽는다. 도구를 매번 모두 호출하는 의무 절차를 만들지 않는다.

최종 결과에는 ① 구성 여부 ② 패키지 실행 준비 ③ 인증 ④ 실제 연결·브라우저 호출을 구분한다. 미완료 연결이 있으면 구체적인 다음 행동만 안내한다. 설치 확인용 MCP 조회를 하더라도 제품 DB나 업무 데이터를 임의로 조회하지 않는다.

## 공식 출처

- [Codex MCP 설정](https://developers.openai.com/codex/mcp)
- [Claude Code MCP와 환경 변수](https://code.claude.com/docs/en/mcp)
- [Figma 원격 MCP 설치](https://developers.figma.com/docs/figma-mcp-server/remote-server-installation/): 공식 Figma 플러그인이 이미 있다면 재사용한다. 본 패키지는 양쪽 호스트가 지원하는 직접 MCP 구성을 기본으로 제공한다.
- [Context7](https://github.com/upstash/context7)
- [GitHub MCP](https://github.com/github/github-mcp-server)
- [Playwright MCP](https://github.com/microsoft/playwright-mcp)
- [Awesome Design MD](https://github.com/VoltAgent/awesome-design-md)
