# 팀 개발 표준 시작하기

이 파일을 Codex에 읽히면 AI가 현재 사용자의 환경을 확인하고 팀 개발 스킬을 설치·검증한다. 이 안내의 배포 대상은 Codex이며, 영문 이름·한국어 설명의 27개 스킬과 공통 하네스를 설치한다. 별도 하네스 서버나 승인 원장을 설치하지 않는다.

## 팀원이 시작하는 방법

1. 팀에서 안내한 Git 저장소를 clone하거나 기존 사본에서 Pull한다. 소스 변경이 있으면 먼저 보존한다.
2. Codex에서 받은 저장소를 열고 아래와 같이 요청한다.

```text
START-HERE-CODEX.md를 읽고 이 팀 개발 표준을 내 Codex에 설치해 줘.
기존 개인 지침과 외부 MCP·플러그인은 보존하고, 기존 Workspace가 있으면 재사용해 줘.
기존 팀 개발 표준이 연결되어 있으면 이 문서의 전환 안내에 따라 백업 후 교체해 줘.
설치와 실제 스킬 인식을 검증하고 남은 사항만 알려줘.
```

Git Pull과 설치는 별개다. 업데이트할 때도 같은 요청을 사용한다. 설치된 파일에 개인 수정이 있으면 덮어쓰지 않고 차이를 먼저 확인한다.

## AI 실행 지침

### 1. 패키지와 실제 경로 확인

- 이 저장소의 `README.md`, `docs/ADAPTATIONS.md`를 읽는다. 이 작업은 환경 설치이며 제품 개발용 설계·이슈·인터뷰를 새로 만들지 않는다.
- 실제 저장소 루트, Git 상태와 revision, Python 3.10 이상 실행 파일, Codex 실행 환경을 확인한다. 아직 clone하지 않은 상태면 사용자가 지정한 저장소를 받는다. 기존 미커밋 변경을 reset하거나 자동으로 stash하지 않는다.
- Codex 설정 위치는 현재 실행 환경의 `CODEX_HOME`을 우선한다. 지정하지 않은 기본 위치는 사용자 홈의 `.codex`다. 다른 계정·WSL·원격 환경에서 실행하고 있다면 실제로 사용할 Codex와 같은 파일 위치인지 확인한다.
- `<codex-home>/team-skills.json`에 `workspace_root`가 있으면 재사용한다. 없으면 프로젝트 또는 구 표준의 기존 Workspace를 먼저 확인한다. 아무 지정도 없으면 현재 사용자 홈의 `AI-Workspace`를 기본값으로 사용하고 실제 경로를 알린다. D 드라이브의 특정 사용자 경로를 필수로 요구하지 않는다.
- Workspace는 제품 소스, 배포 저장소, Codex 설정 폴더와 분리한다. Codex 설정 폴더·배포 원본·Workspace에 링크나 reparse가 있으면 설치기가 차단할 수 있다. 검사를 우회하지 않고 실제 경로를 정한다.
- Python 또는 Codex가 없다면 필요한 프로그램과 공식 설치 경로만 안내한다. 이미 설치한 프로그램, 외부 플러그인, 프로젝트 의존성을 불필요하게 재설치하지 않는다. 프로그램 설치나 계정 로그인이 필요하면 사용자에게 필요한 선택만 요청하고 가능한 패키지 검사는 진행한다.

### 2. 배포 파일 검사와 구 표준 확인

아래 명령은 저장소 루트에서 실행한다. `python`이 실제 Python 3.10 이상을 가리키지 않으면 확인한 실행 파일의 절대 경로로 대체한다. PowerShell에서는 공백이 있는 실행 파일 앞에 `&`를 사용한다.

```powershell
python -B -X utf8 scripts/verify_codex.py --package-only
```

파일 목록·해시·스킬 이름·호출 정책·LICENSE를 검사한다. 불일치는 해당 원본을 확인하고 해결하며, 설치를 통과시키기 위해 `update_manifest.py`를 임의 실행하지 않는다.

기존 `development-workflow`, 구 `dev-*` 스킬, 구 관리 지침 또는 `team_harness`/`development_workflow` MCP가 연결되어 있으면 [전환 안내](docs/MIGRATION.md)를 따른다. 구 표준 연결은 자동 덮어쓰기 대상이 아니다. 최초 사용자와 이미 현재 팀 스킬을 사용하는 사용자는 이 전환을 건너뛴다.

### 3. 설치 계획 확인 후 적용

기본 위치가 맞는 경우 다음 명령으로 계획만 확인한다.

```powershell
python -B -X utf8 scripts/install_codex.py
```

사용자가 다른 Workspace를 지정했거나 Codex가 별도 프로필을 사용하면 실제 절대 경로를 전달한다. 아래 자리표시자를 그대로 실행하지 않는다.

```powershell
python -B -X utf8 scripts/install_codex.py --codex-home "<실제 Codex 설정 폴더>" --workspace-root "<개인 Workspace 기본 폴더>"
```

결과의 배포 버전, 설치 위치, Workspace, 변경 파일 수와 퇴역 스킬·참조 파일 수를 확인한다. 요청한 설치 범위와 일치하면 같은 인자에 `--apply`를 붙여 진행한다. 설치 요청을 받은 뒤 파일마다 또는 검사마다 재승인을 요구하지 않는다. 예상 밖의 소유권 충돌·개인 수정·대상 환경 불일치가 있으면 그 차이만 확인한다.

```powershell
python -B -X utf8 scripts/install_codex.py --apply
```

설치기는 다음을 처리한다.

- `<codex-home>/skills`에 27개 스킬 배치
- `<codex-home>/AGENTS.md`의 팀 관리 블록만 병합
- `<codex-home>/team-skills.json`에 배포 원본과 개인 Workspace 연결
- `<codex-home>/team-skills-receipt.json`에 실제 설치 파일과 버전 기록
- 교체 전 파일을 `<codex-home>/team-skills-backups`에 보존

`config.toml`, 인증 정보, 외부 MCP·플러그인, Claude 설정, 제품 프로젝트와 기존 작업 기록은 일반 설치가 변경하지 않는다. 과거 영수증이 소유한 스킬의 이름 변경은 백업 후 교체하며 알 수 없는 파일은 덮어쓰지 않는다. 시스템 스킬과 다른 개인 스킬을 통째로 교체하지 않는다.

### 4. 파일과 실제 인식 검증

설치에 별도 `--codex-home`을 사용했다면 아래 검사에도 같은 값을 전달한다.

```powershell
python -B -X utf8 scripts/verify_codex.py
python -B -X utf8 scripts/verify_codex.py --native
python -B -X utf8 scripts/install_codex.py
```

- 첫 검사는 설치 파일·관리 블록·receipt·버전·Workspace 일치를 확인한다.
- 두 번째 검사는 실제 Codex 실행 파일의 `skills/list`로 27개 스킬의 활성 인식을 확인한다. 모델 대화와 제품 개발을 시작하지 않는다. Codex 자체 cache는 초기화될 수 있다.
- 마지막 계획의 `changed_files`, `retired_skills`, `retired_files`가 0이고 `receipt_changed`가 false인지 확인한다. 비표준 프로필이면 같은 경로 인자를 유지한다.

Codex가 PATH에 없으면 `--codex-bin "<Codex 실행 파일 절대경로>"`를 사용한다. CLI 접근이 불가능한 앱 환경에서는 새 대화의 실제 스킬 선택 목록에서 확인하고 검사 방식과 한계를 구분한다. 현재 대화에 오래된 목록이 남으면 새 대화에서 확인하고 필요할 때 앱을 다시 시작한다. 파일 검사 성공을 실제 인식·외부 연결 성공으로 확대하지 않는다.

공식 프로토콜 참고: [Codex App Server Skills](https://learn.chatgpt.com/docs/app-server#skills).

### 5. 기본 외부 도구 구성

[기본 외부 도구](docs/INTEGRATIONS.md)를 읽고 Figma·Context7·Awesome Design·GitHub·Playwright의 기존 연결과 활성 플러그인을 확인한다. 요청한 환경 설치에는 이 기본 구성이 포함된다. 실제로 제공되는 동일 기능은 재사용하며 사용자가 지정한 제외 항목이 있으면 따른다.

```powershell
python -B -X utf8 scripts/configure_tools.py --host codex
python -B -X utf8 scripts/configure_tools.py --host codex --apply --prepare-runtime
```

별도 프로필은 `--home`에 전달한다. 현재 활성 Awesome Design 플러그인을 실제 확인했다면 두 명령에 `--provided awesome-design`을 추가한다. Node가 검색되지 않으면 설치 경로를 확인해 `--node-bin`과 `--npx-cli`를 전달한다. 기존 연결 충돌은 자동 덮어쓰지 않으며 보고된 항목을 확인한다. Figma OAuth·GitHub PAT는 사용자별 인증이므로 미완료이면 다음 행동을 안내한다. 계정 없는 디자인은 로컬 시안으로 진행한다. 인증을 위해 제품 DB나 업무 데이터를 조회하지 않는다.

설정 후 실제 호스트에서 도구 목록과 안전한 읽기·브라우저 동작을 확인한다. 패키지 설치, 연결 구성, 인증, 실제 실행을 구분하고 미검증 상태를 성공으로 보고하지 않는다. 자세한 확인 방법은 위 문서에 있다.

### 6. 사용 안내와 결과 보고

기본 진입점은 `$hi`다. 제품 프로젝트에서 다음처럼 요청할 수 있다.

```text
$hi 이 프로젝트의 기존 구조를 확인하고 요청한 기능의 요구사항과 설계를 정리해 줘.
```

특정 단계에는 `$design`, `$implement`, `$code-review`, `$retro` 등을 직접 선택한다. 신규 기능·주요 변경은 필요한 화면·처리·DB·검증 설계를 제시하고 승인 후 구현하며, 이미 승인한 내용을 반복 승인받지 않는다.

최초 전역 설치에서 모든 제품을 등록하거나 업무 DB를 조회하지 않는다. 제품별 설정이 필요할 때 해당 프로젝트에서 `$setup`을 사용한다. 새 AI 테스트는 Workspace의 `tests`, 명세와 중간 산출물은 `artifacts`, 검사 결과와 cache는 `results`에 보관한다. 기존 제품 테스트와 문서를 자동으로 이동하지 않는다.

설치 결과는 버전·실제 경로·27개 스킬 파일 검사·Codex 인식·기존 설정 보존·미완료 항목으로 간단히 보고한다. 파일 보고서가 필요하면 외부 Workspace에 저장한다. 외부 도구는 회사 정책과 사용자 계정에 맞게 인증하고 검증한다. Claude Code는 START-HERE-CLAUDE.md를 별도로 실행하며 한 호스트 설치가 다른 호스트까지 변경하지 않는다. commit/push는 별도 요청 범위다.

배포 원본의 유지보수와 ZIP 생성은 [배포 유지보수](docs/MAINTENANCE.md)를 따른다.
