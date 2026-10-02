# 배포 유지보수

## 원본과 버전

팀이 공유하는 이 Git 저장소를 공통 원본으로 관리한다. 개인의 `CODEX_HOME/skills`와 `CLAUDE_CONFIG_DIR/skills`는 설치된 사본이다. 설치 사본을 먼저 수정했으면 배포 원본과 차이를 검토해 필요한 내용을 원본에 반영한다. 같은 스킬을 여러 저장소에서 각각 갱신하지 않는다.

현재 버전은 `manifest.json`의 `version`이다. 구 실행 엔진에서 스킬 중심 패키지로 전환하면서 새 배포 계열을 3.0.0으로 시작했으며 3.1.0에서 Claude Code와 기본 외부 도구 구성을 추가했다. 3.2.0에서는 호스트 호환성을 위해 스킬 호출 이름을 영문으로 전환했다. 이것은 설치 패키지 버전이며 AI 모델·Codex·외부 도구 버전과 다르다. 같은 공식 버전으로 서로 다른 내용을 게시하지 않는다. 배포할 변경이 있으면 호환성에 맞게 버전을 올리고 Git revision을 함께 기록한다.

`files`는 Codex, `claude_files`는 Claude Code의 설치할 스킬 파일 목록, `package_files`는 하네스·설치 도구·문서까지 포함한 배포 파일 목록이다. 해시는 변경 감지용이며 게시자의 신원 인증을 대신하지 않는다. 팀이 신뢰하는 저장소와 검토된 revision에서 설치한다.

## 변경과 검증

1. 스킬과 필요한 참조·하네스를 함께 수정한다. 실제 호출 이름은 짧은 영문 소문자와 필요한 하이픈으로 정하고 설명은 한국어로 유지하며 기존 27개 스킬의 범위 또는 호출 정책을 바꾸는 결정은 별도 검토한다.
2. `python -B -X utf8 scripts/update_manifest.py`로 검토한 파일의 해시를 갱신한다. 설치 중 오류를 없애려고 검토 없이 해시를 재생성하지 않는다.
3. `python -B -X utf8 scripts/verify_codex.py --package-only`를 실행한다.
4. 외부 Workspace에 임시 Codex 프로필과 별도 Workspace를 만들고 `install_codex.py --codex-home <절대경로> --workspace-root <별도 절대경로>`의 미리보기·적용·반복 적용을 확인한다. 개인 지침과 외부 MCP 보존, 로컬 수정 충돌 시 무변경, 업데이트 후 파일 일치를 검사한다. 테스트 파일과 임시 프로필을 이 저장소에 넣지 않는다.
5. 가능한 환경에서 `verify_codex.py --codex-home <검증 프로필> --native`를 실행해 27개 스킬이 활성 상태로 발견되는지 확인한다. 이 검사는 모델 대화를 시작하지 않으며 Codex 자체 cache는 초기화될 수 있다. Windows 이외의 OS는 실제 시험한 경우에만 검증 완료로 표시한다.
6. Git 체크아웃의 줄바꿈 변환 후에도 파일 검증이 통과하는지 확인한다. `.gitattributes`는 배포 텍스트를 LF로 유지한다. 현재 변경과 관련된 staged·unstaged·untracked 파일을 모두 검토한다.

Python 3.10 이상 표준 라이브러리만으로 설치·파일 검증·ZIP 생성이 가능하다. 각 호스트 프로그램은 실제 스킬 인식 검사에 필요하다. 검증 스크립트는 모델 실행·제품 빌드·외부 MCP 인증을 검사하지 않는다.

## Git 및 ZIP 배포

사용자가 원격 게시를 승인하면 변경을 검토하고 commit/push한다. 팀원이 기존 원격 저장소에서 받을 수 있는 시점은 push 이후다. 로컬 파일 준비를 원격 배포 완료라고 보고하지 않는다.

팀원은 clone 또는 `git pull --ff-only` 후 START-HERE에 따라 설치를 실행한다. Pull 자체로 개인의 설치 사본이 갱신되지는 않는다. 이미 설치한 Workspace는 기본적으로 재사용한다.

ZIP이 필요하면 아래 명령을 사용한다. 출력 파일은 저장소 밖의 새 경로여야 한다.

```powershell
python -B -X utf8 scripts/build_package.py --output "<외부 Workspace의 배포 ZIP 절대경로>"
```

ZIP에는 검증된 배포 파일과 manifest만 들어간다. Git 이력, 개인 설정, 테스트 결과, 백업은 포함하지 않는다. 압축을 풀고 같은 START-HERE를 사용한다. ZIP의 SHA-256과 버전은 생성 결과에서 확인한다.

## 지원 경계

- 배포판: Codex와 Claude Code. 같은 27개 역할과 공통 개발 기준을 호스트별 호출·메타데이터로 제공한다.
- 외부 도구: 기본 구성은 `configure_tools.py`로 제공하며 인증과 회사 정책은 사용자별로 관리한다. 개인 MCP 설정 전체를 팀에 복제하지 않는다.
- 프로젝트: 전역 설치 후 해당 제품에서 `$setup`을 사용할 때 기존 AGENTS.md와 Workspace 연결을 확인한다. 전역 설치가 제품 설정을 완료한 것은 아니다.
- 구 표준: 신규 배포에 자체 Gate 실행기·개인 원장·구 Skills를 포함하지 않는다. 전환은 [MIGRATION.md](MIGRATION.md)를 따른다.
- 배포 구조: 이 루트 AGENTS.md는 저장소 유지보수용이며, 팀원에게 설치하는 규칙은 `adapters/codex/AGENTS.md`, `adapters/claude/CLAUDE.md`의 관리 블록이다.

## Claude Code 및 외부 도구 검사

공통 절차를 바꾸면 양쪽 스킬 원본과 참조 문서를 함께 갱신한다. Codex 전용 메타데이터를 Claude에 복사하지 않으며, Claude의 직접 호출형은 `disable-model-invocation: true`로 유지한다. 단순 치환만으로 새 지침의 호환성을 보장하지 않는다.

격리 프로필에서 `install_claude.py --claude-home <절대경로> --workspace-root <별도 절대경로> --apply`, `verify_claude.py --claude-home <같은 경로> --native`를 실행한다. 실제 개인 프로필에 적용하기 전 최초·반복 설치, 개인 CLAUDE.md 보존, 스킬 로컬 수정 충돌을 확인한다.

`configure_tools.py --host codex|claude --home <프로필>`의 미리보기·적용·반복 실행을 검사한다. 기존 MCP·인증·개인 설정 보존, 누락된 Node의 미완료 보고, 디자인 스킬 충돌을 확인한다. 인증 완료와 실제 도구 호출은 별도 검사한다. npm 버전 변경은 공식 릴리스와 최소 Node 버전을 확인하고 실행 준비 및 브라우저 동작을 재검증한다.

Awesome Design 공개 참조를 갱신할 때는 공식 저장소 revision·LICENSE를 확인해 `SOURCE.json`과 `references/INDEX.md`를 함께 갱신한다. 사용자 plugin cache를 배포 원본으로 복사하지 않는다. 팀용 SKILL.md 지침은 공통 설계 기준과 일치시킨다.
