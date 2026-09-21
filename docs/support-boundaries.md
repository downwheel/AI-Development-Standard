# 지원 범위와 실제 한계

이 문서는 현재 로컬 실행기를 기준으로 한다. 제안 문서의 향후 기능, 파일 설치, 실제 실행 검증을 구분한다. 공개 operation과 입력 schema는 실행기의 `describe`, artifact payload는 같은 고정 release의 `contracts/artifact-payloads.json`이 권위다.

## 기록과 승인

지원: 프로젝트 외부 registry, 개인 bare Git 원장, 불변 artifact revision/pin, candidate/accepted 발행, 두 Gate의 사용자 결정 기록, 변경 의도와 freshness 검사, CLI/STDIO MCP의 공통 core.

한계: 같은 OS 계정의 셸/파일 도구를 격리하거나 사용자의 신원을 암호학적으로 인증하지 않는다. 실제 사용자 메시지 출처를 기록하는 협조적 절차다. 자연어 Skill을 무시한 외부 편집까지 막는 보안 제품이 아니다. 실제 사용자 응답 없이 AI가 승인을 만들면 안 된다.

문서 작성 완료·accepted 발행·인간 승인·소스 적용·검사 통과는 별도다. 후보가 있다는 이유만으로 기존 승인을 전부 지우지 않는다. 승인 대상이 바뀌면 옛 승인을 새 문서에 복사하지 않는다.

## 제품 Git과 개인 history Git

제품 파일은 정상 개발 시 바뀔 수 있다. 따라서 Git status/diff가 달라지는 것은 예상된다. Harness의 기록 기능은 제품에서 add/commit/stash/reset/checkout/restore/worktree를 실행하거나 index/refs/config/hooks를 바꾸는 방식이 아니다.

개인 history Git은 제품 Git과 다른 위치의 bare 저장소다. 내부 commit은 설계/승인/증거와 소스 bytes의 개인 이력을 보존한다. 기본 remote/push와 자동 prune은 없다. 제품의 staged/unstaged 조합, branch 이동, 원격 저장소 상태를 복원하는 기능은 제공하지 않는다.

외부 스크립트나 사용자가 Git을 바꿀 수 있으므로 실행 전후 관찰과 충돌 확인이 필요하다. 관찰이 모든 외부 변경을 막는 것은 아니다.

## 소스 snapshot

일반 파일과 디렉터리의 bytes·상대경로·hash를 보관한다. tracked/untracked 구분 없이 수집 정책에 맞는 파일을 읽는다. 두 관찰 결과의 일치를 확인하는 observed-stable이며 모든 외부 writer에 대한 단일 시점의 원자적 snapshot이 아니다.

현재 기본 상한은 파일당 8 MiB, 합계 64 MiB, 파일 10,000개이며 디렉터리 수도 제한한다. 실제 capture가 실패하면 보호 사본을 확보했다고 표시하지 않는다. 공개 capture operation이 정책 변경 입력을 제공하지 않으면 임의 옵션으로 한도를 늘리지 않는다.

기본 제외에는 .git, 가상환경·node_modules·캐시·빌드 결과·coverage·logs, 실제 .env 계열과 자격증명 파일/키 인증서 등이 포함된다. 비밀 없는 .env.example/.env.sample/.env.template은 대상이 될 수 있지만 내용 검사도 통과해야 한다. 자세한 현재 규칙은 고정 release의 history.py와 snapshot manifest의 exclusions/policy를 확인한다.

파일 내용의 비밀 탐지는 한계가 있으며 완전한 DLP가 아니다. 민감 자료가 들어가지 않도록 프로젝트 정책으로 사전에 분리한다. 제외한 파일을 마스킹해 바꾼 사본을 원본 복원용으로 표시하지 않는다.

링크·junction/reparse point·특수 파일·일부 이름·대소문자 충돌·불안정 읽기는 지원 범위에서 거부한다. 파일 권한/ACL·timestamp·hardlink 관계·DB/Figma/SaaS 상태·운영 데이터·자격증명까지 보존/복원하는 시스템이 아니다. 파일 사본과 데이터베이스 백업은 별개다.

## 복원

기본은 제품 밖의 새 빈 폴더 export와 bytes 검증이다. 원본 적용은 target snapshot·현재 baseline·실제 경로/작업 목록이 고정된 RestorePlan과 명시적 사용자 결정을 요구한다.

직전 사본·write-ahead journal·충돌 확인 뒤 허용 범위만 적용한다. 여러 파일을 한 번에 원자적으로 되돌리는 기능이 아니므로 중단/부분 적용을 기록한다. 복원 journal이 미해결이면 새 관리 쓰기를 막고 `reconcile_recovery`의 실제 지원 action과 계획을 확인한다. 기존 사용자 변경을 자동 rollback으로 덮어쓰지 않는다.

복원 완료는 전체 제품 검사 통과가 아니다. 현재 소스와 승인 계획을 다시 확인해 새 검사 근거를 남긴다.

## 검사 실행

승인된 argv 배열·상대 cwd·1~300초 시간 제한으로 실제 프로세스를 실행하고 attempt별 출력을 보존한다. Windows .cmd/.bat shim과 직접 Git 명령은 차단한다. 검사 안에서 실행되는 외부 side effect까지 완전 격리하는 sandbox는 아니다.

검사 전에 실행 파일/스크립트·환경·권한·비용·출력의 민감 정보 가능성을 확인한다. 현재 환경 전달/출력 redaction은 제한된 규칙이며 모든 비밀 유출을 보장해서 막지 않는다. 원문 업무 데이터를 로그에 넣지 않는다.

반환 코드, 실제 case 결과, 소스·승인·환경 변경 여부를 함께 판정해야 한다. 미실행·timeout·인증/쿼터 차단·drift는 pass가 아니다. 테스트를 다시 요청하면 새 실제 실행으로 기록하고 이전 실패도 남긴다. 지원 parser와 중단 실행 정리 절차는 아래 공개 계약 확인 절차를 따른다.

```text
python scripts/harness.py describe run_checks
python scripts/harness.py describe get_verification
python scripts/harness.py describe
```

검사 결과를 직접 publish_artifact로 만들어 통과시키지 않는다. 구현 receipt와 verification-report는 실행기의 실제 실행 경로가 생성한다. 추가 parser·case 결과 형식·중단 복구 operation이 변경되면 같은 release의 schema를 먼저 확인한다.

### 실제 case 결과 형식

현재 check 기본값은 evidence_mode=case-results, parser=team-json이다. stdout에 아래 형식의 marker 한 줄이 정확히 한 번 있어야 한다.

```text
HARNESS_CASE_RESULTS={"cases":[{"case_id":"case-example","status":"passed"}]}
```

각 status는 passed/failed/skipped 중 하나다. declared case_ids와 결과의 case_id 집합이 정확히 같아야 하며 중복·추가·누락·0건·skip은 전체 완료의 근거로 쓰지 않는다. JSON이 유효해도 case 결과나 명령/소스 조건이 맞지 않으면 pass가 아니다.

build/lint/typecheck처럼 **명령 완료 자체가 승인된 인수 기준**인 검사는 evidence_mode=command-exit와 parser=exit-code를 둘 다 명시한다. 이 모드는 종료 코드를 근거로 하므로 일반 기능 사례를 명령 성공만으로 검증한 것처럼 만들지 않는다. 현재 JUnit/unittest parser와 case_map 자동 매핑은 지원하지 않는다. 기존 runner는 승인된 adapter로 실제 사례 결과를 위 형식에 맞춰 출력하거나 필요한 지원을 별도 설계한다.

### 중단된 관리 실행

reconcile_execution은 kind(implementation/verification), **원래 실행의 request_id**, owner, action(status/reconcile)을 받는다. implementation을 reconcile할 때는 외부 편집 작업을 실제로 중지한 뒤 external_writers_stopped=true를 명시해야 한다. CLI controller 종료만으로 Codex/Claude·편집기 종료가 증명되지 않기 때문이다. status는 조회다. reconcile은 기록된 controller와 관리 child의 OS 종료가 확인된 경우에만 중단 상태로 정리하고 협조적 lease를 해제한다. 프로세스가 살아 있거나 식별이 불명확하면 복구 변이를 거부한다. lease 시간 만료만으로 새 실행이 쓰기 소유권을 가져오지 않는다.

실행 정리는 제품 파일의 자동 rollback이나 테스트 재실행이 아니다. 상태를 확인하고 필요한 소스 검토·새 구현/검증을 따로 수행한다. 외부 편집기나 원격 서비스 프로세스까지 통제하지 않는다.

현재 source snapshot은 workspace 전체가 기준이다. 다른 단위가 소스를 바꾸면 이전 단위 receipt도 source_changed로 현재 적용성을 잃을 수 있다. 이전 단위를 현재 workspace에서 변경 없는 구현 receipt로 다시 관찰하고 모든 필수 검사를 재실행해야 완료 상태를 갱신할 수 있다. 새 소스에 대한 자동 부분 검사 결과 승계는 지원하지 않는다.

검사 요청 전체의 실행 예산은 900초이며 각 check는 1~300초다. 종료 처리와 증거 저장 I/O까지 포함한 API 응답 시간이 항상 900초 이하라는 보증은 아니다. 실행 환경 관찰은 executable/argv의 기존 파일, 제품 루트의 node_modules/.venv/venv bytes, 필터된 상속 환경 hash를 사용한다. 관찰 한도는 50,000개 파일/512 MiB이며 초과나 링크는 차단한다. 외부 서비스와 전역 시스템 라이브러리 전체를 snapshot 하는 것은 아니다.

Windows의 관리 child는 Job Object를 사용해 controller 종료 시 함께 종료하도록 관리한다. POSIX에서는 controller 강제 종료 뒤 관리 child가 살아 있으면 OS 종료 확인 전 reconcile을 차단한다. 정상 종료/timeout/cancel은 관리 프로세스 그룹 정리 절차를 수행하지만 외부 서비스나 사용자 편집기를 종료했다는 뜻은 아니다.

## 호스트와 외부 도구

Codex 파일 설치 뒤에는 재시작/새 세션의 실제 Skill/MCP 노출 확인이 필요하다. Claude용 개인 설정 생성과 Claude native discovery 성공은 다르다. Claude CLI가 없는 호스트에서는 native discovery/MCP 실행을 미검증으로 남긴다.

기존 외부 MCP는 보존 대상이다. Figma·Context7·DB·Playwright는 실제 노출·로그인·대상 권한·쿼터를 단계에 맞게 확인한다. Figma 이미지 한 장은 native 편집 설계가 아니며, Playwright MCP 탐색 한 번은 지속 회귀 검사 체계를 대신하지 않는다.

Team Git 접근 및 외부 계정 연결은 각 팀원의 환경에서 별도로 확인한다. [연결 작업 목록](account-next-steps.md)
