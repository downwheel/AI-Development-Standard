# Team Development Standard

자연어 개발 요청을 조사·요구사항·시스템 설계·단위 설계·테스트 설계·구현·실제 검증으로 연결하는 로컬 개발 표준이다. 11개 Skill이 독립적으로 동작하고, Team Harness의 동일 core를 CLI와 STDIO MCP로 사용한다.

프로젝트별 산출물과 소스 사본은 **별도 개인 이력**에 보존한다. 이 공통 원본은 팀의 Skill·실행기·계약·양식·시험·가이드만 배포한다. 제품 Git이나 운영 환경을 자동 관리하는 도구가 아니다.

## 사용 시작

1. [배포 저장소](https://github.com/downwheel/AI-Development-Standard)의 접근 권한을 받은 뒤 [Sourcetree 배포 가이드](docs/git-distribution.md)에 따라 공통 원본을 clone한다.
2. Codex 또는 Claude Code에 **[START-HERE.md](START-HERE.md)를 읽고 초기 설정을 진행해 달라고 요청한다.** AI가 개인 경로·기존 설정을 조사하고 설치·진단·개인 보고서 작성을 진행한다. 직접 설치하려면 [팀원 온보딩](docs/team-onboarding.md)을 따른다.
3. [사용자 가이드](docs/user-guide.md)의 자연어 예시로 원하는 단계를 요청한다.
4. 필요한 외부 서비스만 [계정 연결 후속 작업](docs/account-next-steps.md)에 따라 연결한다.
5. [지원 범위와 한계](docs/support-boundaries.md)를 확인한다. 실제 실행과 문서상 계획은 구분된다.

사용자별 `.env`, 정량 DB 작업, 파일·DB 객체별 필수 범위 승인의 **추가 구현 설계**는 [2.1 보완 계약](docs/designs/development-contract-v2.1.md)에 있다. 현재 2.0.0에 이 기능이 이미 구현됐다는 뜻은 아니다. 스타터도 실제 도구와 schema로 지원 여부를 확인한다.

## 단계와 승인

`dev-discover → dev-requirements → dev-system-design → Gate A → dev-unit-design → dev-test-design → Gate B → dev-implement → dev-verify`

Gate A는 조사·요구·시스템 설계의 정확한 버전 세 개, Gate B는 단위 설계·그 단위를 참조한 테스트 계획 두 개를 사용자에게 제시한다. AI 검토나 문서 작성 완료는 인간 승인이 아니다. 이미 승인된 같은 범위를 수정·검증할 때는 불필요하게 재승인을 요구하지 않는다.

보조 Skill은 `dev-review`(검토/실제 결정 기록), `dev-artifacts`(조회/비교), `dev-restore`(소스 복원)다. `development-workflow`는 현재 단계를 찾아 주는 선택적 길잡이다. “보여줘”는 자료를 새로 만들거나 승인하지 않는다.

## 세 저장 영역

| 영역 | 보관하는 것 |
|---|---|
| 공통 원본과 개인 고정 release | Skill·core·schema·template·테스트·가이드 |
| 개인 state/history/evidence | 프로젝트 등록·설계 revision·승인 근거·검사 attempt·제한된 소스 snapshot |
| 제품 폴더 | 실제 소스·프로젝트 테스트·lockfile·프로젝트 문서 |

제품의 정상 편집으로 working-tree diff는 생긴다. Harness 기록을 위해 제품 Git의 index/refs/config/hooks를 바꾸거나 commit/push하지 않는다. 개인 history Git은 별개의 bare 저장소이며 기본 remote가 없다.

## 실행과 검증

Python 3.10+와 Git을 사용한다. 공개 입력은 `team_harness.py describe <operation>`과 `contracts/artifact-payloads.json`이 정의한다. 설치된 Skill의 `scripts/harness.py`는 개인 runtime 설정으로 같은 실행기를 호출한다. [실행 예시](docs/user-guide.md#cli로-확인할-때)

공통 테스트는 공통 원본에서 다음과 같이 실행한다. 테스트 fixture에서만 합성 승인과 임시 제품 Git을 사용하며 실제 사용자 승인으로 취급하지 않는다.

```text
python -B -X utf8 -m unittest discover -s tests -v
```

개인 JSON 시험 기록은 scripts/validate_standard.py --output "<personal-test-report.json>"으로 남긴다. 설치된 호스트 진단은 scripts/doctor.py를 사용하며 [온보딩의 진단 명령](docs/team-onboarding.md#진단과-공통-시험)을 따른다.

단계별 실제 CLI 연결·승인 차단·조회 불변 확인은 [웹 설정 화면 forward-test](docs/skill-forward-test-report.md)에 기록한다. 이 시험은 브라우저·Figma·외부 계정의 통합 검증을 뜻하지 않는다.

## 후속 연결

공통 Git을 clone해도 개인 호스트 설치나 서비스 로그인이 자동으로 완료되지는 않는다. 팀원은 자신의 GitHub 계정으로 저장소에 접근하고, Codex 또는 Claude Code와 필요한 Figma·Context7·DB·브라우저 MCP를 자신의 환경에 연결한다. 계정·토큰·개인 기록은 공유하지 않는다. Claude CLI가 없는 호스트에서는 파일 준비와 native Skill discovery/MCP 실행 확인을 구분한다.
