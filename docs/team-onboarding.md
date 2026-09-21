# 팀원 온보딩

공통 표준을 팀에 배포할 때 제품과 개인 기록을 분리하고, 각 개발자의 호스트 설정만 생성한다. 먼저 [Sourcetree 배포 가이드](git-distribution.md)에 따라 자신의 GitHub 계정으로 원본을 clone한다. 외부 서비스 계정 연결은 각 호스트에서 별도로 진행한다.

AI가 초기 설정을 직접 진행하도록 맡기려면 [START-HERE.md](../START-HERE.md)의 Codex 또는 Claude Code 요청문을 사용한다. 설치된 Skill이 없어도 시작할 수 있다. 아래 문서는 실제 설치 계약과 수동 실행 안내이며, 추가 보완 기능의 구현 완료를 의미하지 않는다.

## 준비

- 지원되는 Python 3.10+와 Git 실행 파일.
- 공통 표준 원본 폴더, 그 폴더와 겹치지 않는 개인 state 폴더, 작업할 제품 폴더.
- 사용할 호스트의 개인 profile. Codex/Claude 설정에 기존 내용이 있으면 유지해야 한다.
- 조직의 개인 소스 사본 보관·비밀 제외·백업 정책.

소스 사본에는 일반 소스와 테스트/lockfile 등이 포함될 수 있다. [지원 범위](support-boundaries.md)의 기본 제외·용량·복원 한계를 먼저 확인한다. 공유/개인/제품 루트가 포함 관계이거나 링크 경로이면 지원 범위에서 차단될 수 있다.

Windows에서는 `python --version`과 `git --version`을 확인한다. `<python-executable>`에는 Python 3.10 이상 실제 실행 파일의 절대 경로를 넣고, `<personal-profile>`에는 사용할 도구의 사용자 홈을 넣는다. `<personal-state>`는 공통 clone과 제품 밖의 별도 로컬 폴더다. 앱별로 리디렉션될 수 있는 AppData 자동 기본값에 의존하지 말고, 두 도구에서 같은 물리 경로로 접근할 수 있는 위치를 명시한다. 공통 clone 안에는 개인 JSON, 검사 출력, 가상환경, 의존성, 소스 사본을 만들지 않는다.

## 미리보기와 설치

공통 원본에서 현재 설치 스키마와 변경 계획을 확인한다.

```text
python -B -X utf8 install.py plan --profile "<personal-profile>" --state-root "<personal-state>" --python "<python-executable>"
```

계획에는 고정 release, release manifest에 선언한 12개 Skill과 runtime/launcher, 관리 라우팅 구간, MCP 항목, 개인 설정이 표시된다. 검토된 범위에 설치한다.

```text
python -B -X utf8 install.py install --profile "<personal-profile>" --state-root "<personal-state>" --python "<python-executable>"
```

이 명령 예시는 실행 안내이며 문서를 읽는 행위가 설치 실행은 아니다. 실제 경로는 각 사용자의 로컬 설정에만 남는다.

설치기는 공통 내용을 개인 releases 아래 content hash 기반 release로 보존하고 호스트 Skill마다 references를 함께 배치한다. Codex UI metadata는 호스트에만 생성하고 공통 SKILL.md에는 Codex 고유 권한 문법을 넣지 않는다. Claude용 파일 배치는 Claude에서 실제 discovery·MCP 실행을 확인했다는 뜻이 아니다.

## 기존 설정 보존

관리 라우팅 구간과 `team_harness` MCP 항목을 갱신하며 기존 비관련 MCP와 사용자 규칙을 보존해야 한다. 구 v1 `development_workflow` 서버는 중복 기록을 막기 위해 비활성화할 수 있지만 기존 기록을 삭제하지 않는다.

설치 전 bytes와 변경 대상 hash는 개인 `installation-backups`의 receipt에 보존한다. 다른 프로세스가 바꾼 파일이나 이름이 충돌한 비관리 Skill은 임의 덮어쓰기 대신 확인 대상이다. 설치 완료 receipt와 실제 호스트 동작은 별도로 검증한다.

## 호스트에서 확인

1. 사용할 Codex 또는 Claude Code를 설치·인증하고 새 세션을 연다. 이미 실행 중인 세션의 도구 목록은 설정 변경만으로 갱신됐다고 가정하지 않는다.
2. 해당 도구에서 manifest의 12개 Skill이 보이는지 확인하고 `dev-artifacts` 또는 길잡이를 호출한다. 설치 파일 수와 실제 도구의 Skill 인식은 별도로 확인한다.
3. `team_harness`의 `info`/`describe`로 고정 release와 개인 state 경계를 확인한다. 필요하면 해당 Skill launcher로 같은 조회를 수행한다. CLI 대안 성공만으로 호스트의 native MCP 연결까지 성공했다고 표시하지 않는다.
4. [연결 가이드](../integrations/connection-guide.md)의 호스트별 준비표로 Figma·Context7/OpenAI Docs·브라우저·DB의 기존 MCP를 실제 확인한다. 설정 존재/현재 도구 노출/인증/대상 읽기/쓰기 권한을 분리한다. 기존 플러그인이나 MCP가 있으면 중복 등록하지 않는다. 로그인이 필요한 서비스는 개인 보고서의 후속 작업으로 남긴다.
5. Claude CLI가 없는 호스트에서는 파일 준비까지 확인하고 native 실행은 미검증으로 남긴다. 호스트 인증·모델 호출·로컬 MCP·각 외부 MCP는 서로 다른 확인 항목이다.

읽기만 하는 첫 요청 예시: “development-workflow를 사용해서 현재 연결된 Team Harness의 release와 개인 기록 경로를 확인해 줘. 프로젝트를 새로 등록하거나 개발을 시작하지는 마.” 이 확인이 끝난 뒤 원하는 제품 경로와 개발 목적을 전달한다.

## 외부 도구 활용 기본값

2.2는 core 계약 2.1과 외부 도구 정책 1을 함께 사용한다. 새 run의 UI는 Figma 우선이며 편집 native 필수와 승인된 로컬 대안을 구분한다. 버전 의존 결정은 Context7, OpenAI 관련 결정은 OpenAI Docs를 우선 사용한다. UI의 실제 브라우저 관찰과 지속 회귀 runner는 별도 결과다. DB의 실제 관찰·정량 적용·재조회는 기존 계약을 유지한다. [정책·실패 판정](v2.2-tools.md)을 읽는다.

공통 설치가 외부 서비스 계정이나 특정 제품 DB를 연결하는 것은 아니다. 첫 설정에서는 개인 연결 준비까지 진행하고 실제 인증은 사용자에게 안내한다. Figma 파일 생성·업무 DB 조회·외부 쓰기 시험은 해당 대상과 범위가 허용된 시점에 한다. Codex의 연결을 Claude의 성공으로 복사하지 않는다.

## 프로젝트 등록과 첫 실행

2.1의 개인 `.env`와 역할별 DB 연결은 `dev-environment`로 준비한다. 생성 파일의 경로를 안내하고 실제 값은 사용자가 로컬에서 입력한다. 빈 파일·드라이버 설치·실제 역할 probe·제품 DB 시험은 별도 상태다. [2.1 실행 계약](v2.1-operations.md)에 파일·DB 범위 승인과 서비스/fixture/증거 계약을 설명한다.

기존 제품을 `project_register`로 개인 registry에 등록한다. 제품 안에 .git/.harness/포인터 파일을 만들 필요가 없다. 신규 제품 폴더 생성은 지정한 범위에서 명시적으로 선택한다.

`development-workflow`에 개발 목적과 프로젝트를 알려 주거나 원하는 개별 Skill을 호출한다. 제품 Git의 commit/push 정책은 기존대로 유지한다. 개인 history Git의 자동 내부 기록과 혼동하지 않는다.

## 업데이트·돌리기

Sourcetree의 fetch/pull은 공통 원본만 갱신한다. 호스트의 설치된 Skill과 고정 release는 자동으로 바뀌지 않는다. 공통 원본의 미커밋 변경과 배포 revision을 확인한 뒤 새 공통 버전에서 다시 plan→검토→install한다. 기존 run의 승인/소스/검사 기록을 새 버전의 성공으로 바꾸지 않는다. 중단된 writer·복원 journal이 있으면 먼저 해소한다.

run은 실행을 시작한 release와 도구 정책 버전에 고정된다. 정책 1이 없는 이전 run을 새 필수 근거 검사로 조용히 변환하지 않는다. 새 Skill launcher가 새 release를 가리켜도 이전 run의 쓰기는 release_mismatch로 차단될 수 있다. 이때 개인 이력과 이전 release를 지우지 말고, 이전 release의 team_harness.py에 **같은 개인 state와 같은 공통 source_root**를 전달하여 재개한다. 새 run은 현재 release에서 시작할 수 있다. 이전 run을 새 release로 묵시적으로 재승인하거나 입력을 바꿔 끼우지 않는다.

설치 자체를 되돌릴 때는 자신의 설치 receipt로 먼저 preview한다.

```text
python -B -X utf8 install.py rollback --receipt "<installation-receipt.json>" --profile "<personal-profile>" --state-root "<personal-state>"
```

검토 후 적용이 필요하면 같은 명령에 `--apply`를 사용한다. 설치 후 별도 수정이 생긴 파일은 충돌을 해결해야 한다. 개인 history와 고정 release는 보존되며 이 rollback은 제품 소스 복원이 아니다.

공통 Git revision 선택, 설치 rollback, 개인 제품 소스 복원은 서로 다른 작업이다. [Git 배포와 업데이트](git-distribution.md)의 구분을 따른다. 외부 계정·권한 연결은 [후속 작업](account-next-steps.md)에서 확인한다.

## 진단과 공통 시험

설치 후 다음 진단은 설치 파일과 CLI/STDIO MCP, 선택한 Codex native discovery를 읽기 위주로 확인한다. 업무 DB를 조회하거나 모델 개발 작업을 시작하지 않는다. 결과 파일에는 개인 경로가 포함될 수 있으므로 공통 원본 밖에 저장한다.

```text
python -B -X utf8 scripts/doctor.py --profile "<personal-profile>" --state-root "<personal-state>" --codex --output "<personal-report.json>"
python -B -X utf8 scripts/validate_standard.py --output "<personal-test-report.json>"
```

doctor의 파일 존재/CLI/MCP 확인과 Claude native 실행 여부는 별도 결과다. validate_standard는 격리 fixture에서 표준의 테스트를 실행한다. 위 명령을 안내했다는 사실만으로 현재 설치를 검증했다고 판단하지 않는다.
