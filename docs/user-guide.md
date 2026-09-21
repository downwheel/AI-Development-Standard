# 사용자 가이드

사용자는 내부 ID나 파일명을 외우지 않고 목적 또는 필요한 단계를 말할 수 있다. 예를 들어 “기존 웹 프로젝트에 설정 화면을 추가하고 싶어”라고 하면 현재 소스부터 조사하고 요구·설계를 구체화한다. 기존 프로젝트 경로와 중요한 제품 결정은 확인하며, 근거로 알 수 있는 내용은 다시 묻지 않는다.

## 원하는 단계만 호출하기

| 요청 예시 | 수행하는 일 |
|---|---|
| “현재 프로젝트 구조와 변경 영향을 조사해줘.” | dev-discover: 소스/환경/검사 경로/데이터 경계 조사 |
| “개발 범위와 인수 기준을 정리해줘.” | dev-requirements: 요구와 중요한 질문 상세화 |
| “전체 구조와 작업 분량을 설계해줘.” | dev-system-design: 구조·영향·단위·검증 전략 |
| “이 단위의 화면 배치와 상태를 설계해줘.” | dev-unit-design: 승인 시스템 범위의 UI/API/data/integration 계약 |
| “이 설계를 검증할 테스트 계획을 만들어줘.” | dev-test-design: 독립 기대값·fixture·검사 명령 |
| “승인한 단위를 구현해줘.” | dev-implement: 승인·baseline 확인 후 소스/테스트 작성 |
| “테스트를 다시 실행해줘.” | dev-verify: 새 실제 attempt 실행 |
| “설계 검토하고 승인할 자료를 보여줘.” | dev-review: AI findings·정확한 Gate 묶음 제시 |
| “지난 화면 설계와 실패 로그를 보여줘.” | dev-artifacts: 기존 revision/attempt 조회 |
| “이전 소스를 별도 폴더에서 확인하고 싶어.” | dev-restore: 보존 snapshot export·preview |
| “현재 어디까지 했고 다음에 뭘 하면 돼?” | development-workflow: 기록 기반 단계 안내 |

Skill 이름을 직접 지정해도 된다. 한 단계 요청은 그 결과까지 수행한다. 전체 개발을 요청하면 가능한 준비 작업을 이어가되 두 실제 Gate를 건너뛰지 않는다. 일반 기술 질문과 단순한 가역 편집은 전체 절차를 강제하지 않는다.

## 외부 도구가 사용되는 방식

새 UI 개발은 Figma를 먼저 사용하고, 버전 의존 기술 결정에는 Context7 또는 OpenAI Docs를 먼저 확인한다. UI 완성은 실제 브라우저 관찰과 저장된 회귀 runner, DB 저장은 실제 DB 재조회로 확인한다. 각 작업의 적용 여부와 대안은 시스템 설계에서 보여준다. [구체 정책과 예시](v2.2-tools.md)

Figma가 필수라면 quota·편집 권한 문제를 로컬 그림으로 대신해 완료하지 않는다. preferred이면 실제 차단을 기록하고 Gate A에서 승인한 로컬 배치안으로 진행할 수 있다. 사용자가 처음부터 로컬 설계를 명시 선택하면 local_only로 기록한다. Context7이 없거나 정확한 버전을 제공하지 못하면 원인과 공식 문서 대체 근거를 남긴다.

추가 요청 없이도 이 기본 정책을 적용한다. 사용자가 확인하고 싶다면 “이번 설계에서 어떤 MCP를 어떤 단위에 사용했는지, 실제 근거와 사용하지 못한 이유를 보여줘”라고 요청하면 된다. 호출 횟수보다 실제 설계 결정과 검증 결과가 기준이다.

## 승인할 때 받는 자료

Gate A에서는 조사·요구·시스템 설계, 변경 영향과 작업 분량, 도구별 적용 단위·필수 결과·차단 시 대안을 받는다. 승인 후 단위 설계를 진행한다.

Gate B에서는 상세 단위 계약, 정확한 화면·백엔드·설정 파일 및 DB 객체·수량의 scope 표, 필요한 환경·DB 계획, 이 refs를 참조한 테스트 계획을 함께 받는다. UI라면 화면·상태·배치·색상·컴포넌트·키보드/focus·데이터 계약, 도구 계획에 맞는 편집 가능한 Figma 결과 또는 승인한 로컬 배치안과 실제 근거가 포함된다. 버전별 문서·DB 관찰과 브라우저/DB 필수 실행 증거 계획도 함께 확인한다. 승인 후 해당 범위를 구현한다. 테스트 계획을 나눴다고 제3의 설계 승인을 추가하지 않는다. 개인 `.env` 준비와 정량 실행은 [2.1 안내](v2.1-operations.md)를 따른다.

AI는 실제 제시한 review ID와 문서 해시에 사용자의 실제 응답을 연결한다. 자료가 바뀌면 과거 응답이 새 문서까지 승인한 것으로 처리하지 않는다. 설계 승인은 운영 배포·DB 변경·메시지 발송·원본 소스 복원의 허가가 아니다.

## 다시 호출하고 수정하기

- “보여줘/비교해줘”: 기존 자료의 정확한 버전을 읽는다. 파생 MD/HTML 파일이 만들어질 수 있지만 canonical 원장·승인은 변하지 않는다.
- “이어 해줘”: 남아 있는 질문·실패·미완료 실행과 현재 입력을 확인하여 재개한다.
- “이 요구대로 수정해줘”: 새 revision과 변경 의도를 기록한다. 영향을 받는 후속 자료만 재검토한다.
- “테스트 다시”: 이전 로그를 보여주는 대신 새 실행을 한다. 실패·차단·이전 pass를 모두 보존한다.
- “과거 버전으로 복원”: 먼저 실제 snapshot과 현재 차이·충돌·제외 범위를 보여준다. 현재 유효한 구체적 계획 승인 후에만 원본에 적용한다.

초안(candidate), 다음 단계가 사용할 발행본(accepted), 인간 승인, 소스 적용, 테스트 통과는 서로 다른 상태다. accepted 문서가 있어도 Gate를 승인한 것은 아니다.

## CLI로 확인할 때

보통 Skill 또는 `team_harness` MCP로 작업한다. 현재 세션에 MCP가 아직 노출되지 않으면 설치된 해당 Skill 폴더에서 launcher를 사용할 수 있다.

```text
python scripts/harness.py describe project_list
python scripts/harness.py call project_list --input-file empty.json
```

`empty.json`의 내용은 `{}`다. 입력 파일은 개인 staging 위치에 만든다. 설치 후 launcher는 옆의 runtime.json에서 실제 Python·고정 release·개인 state를 읽는다.

공통 실행기를 직접 호출하는 형태는 다음과 같다. 꺾쇠 항목은 실제 설정으로 바꾼다.

```text
python "<release>/team_harness.py" --state-root "<personal-state>" --standard-root "<common-source>" describe project_register
python "<release>/team_harness.py" --state-root "<personal-state>" --standard-root "<common-source>" call project_register --input-file "<personal-input.json>"
```

기존 프로젝트 등록 입력은 다음 키를 사용한다. 실제 절대 경로를 개인 입력 파일에만 넣는다.

```json
{
  "project_root": "<existing-product-absolute-path>",
  "name": "작업할 프로젝트",
  "create_root": false
}
```

반환된 project_id/workspace_id로 run을 만든다. `create_run`에는 project_id, run_id, workspace_id, goal이 필요하다. ID·enum·추가 필드는 반드시 해당 operation의 `describe`를 확인한다. 제품 신규 폴더를 만들려면 사용자의 범위에 맞는 경로와 `create_root:true`를 명시한다.

산출물은 `publish_artifact`로 JSON payload와 MD를 함께 등록한다. 기본은 candidate이며 다음 단계에 사용할 완결된 결과를 `accept_artifact`와 조회한 expected_head로 발행한다. 입력 ref는 artifact_id/revision_id/sha256 세 값이다. 도구가 반환하지 않은 ID/해시를 만들어내지 않는다.

`get_artifact`는 고정 본문을, `render_artifact`는 개인 폴더의 읽기용 MD/HTML 파일을 반환한다. `get_verification`은 실제 시도와 현재 완료 가능 여부를 조회한다. canonical 문서 안에 자기 manifest hash를 넣지 않는다.

## 실제 검사 명령의 주의점

검사는 승인 TestPlan의 argv 배열·상대 cwd·시간 제한으로 실행한다. Windows의 npm.cmd 같은 셸 shim은 직접 실행하지 않는다. 실제 Node 실행 파일과 확인한 npm-cli.js 경로 또는 명시적으로 검토한 실행 스크립트를 계획에 담는다. 프로젝트 명령 안의 외부 쓰기·비밀·Git 조작도 먼저 검토한다.

테스트 결과 형식과 중단된 실행의 복구는 [지원 범위](support-boundaries.md)를 따른다. 연결 실패나 미실행을 기능 실패 또는 pass로 바꿔 기록하지 않는다.

## 연결이 막힌 경우

Figma 필수인데 편집 권한이 없으면 이미지 한 장으로 완료 처리하지 않는다. DB 권한 오류는 “테이블 없음”이 아니다. Context7 문서는 설치된 버전·공식 원문과 대조한다. Playwright MCP 탐색 성공은 저장된 회귀 테스트 통과와 구분한다.

[후속 계정 연결](account-next-steps.md)을 따라 해당 기능만 연결한다. 외부 도구가 막혀도 독립적인 로컬 조사·설계 자료는 먼저 제공할 수 있다.
