# 실행 인터페이스 계약 — 2.0.0

CLI와 STDIO MCP는 같은 core를 호출한다. 실제 입력은 해당 고정 release의 `describe <operation>`, 산출물별 payload는 `contracts/artifact-payloads.json`을 따른다. 없는 필드·도구·성공 receipt를 만들어 전송하지 않는다.

## 실행과 release

```text
python "<release>/team_harness.py" --state-root "<personal-state>" --standard-root "<common-source>" describe <operation>
python "<release>/team_harness.py" --state-root "<personal-state>" --standard-root "<common-source>" call <operation> --input-file "<personal-input.json>"
python "<release>/team_harness.py" --state-root "<personal-state>" --standard-root "<common-source>" serve
```

설치 Skill의 scripts/harness.py는 runtime.json의 python/entrypoint/state_root/source_root를 읽는다. entrypoint는 개인 immutable release, source_root는 공통 원본 경계다. 수정 가능한 원본은 working-source이며 immutable release의 manifest와 혼동하지 않는다.

신규 run은 실제 실행 release에 고정한다. 다른 release로 이전 run을 변경하려 하면 release_mismatch로 차단될 수 있으며 조회는 가능하다. 같은 개인 state와 공통 source_root를 사용하여 이전 release 실행기로 재개한다. 새 release가 과거 승인/검사를 자동 승계하지 않는다.

## 공개 기능군

| 목적 | operation |
|---|---|
| 등록/진단 | info, project_list, project_register, import_legacy |
| 단계 | create_run, start_stage, finish_stage, resume_stage |
| 산출물 | publish_artifact, accept_artifact, get_artifact, list_artifacts, diff_artifacts, render_artifact |
| 검토/변경 | create_review, record_decision, record_change, resolve_change, workflow_status |
| 협조적 소유권 | acquire_lease, release_lease |
| 구현/검사 | begin_implementation, finish_implementation, list_implementations, run_checks, get_verification, cancel_verification, reconcile_execution |
| 사본/복원 | capture_snapshot, snapshot_list, export_snapshot, plan_restore, record_restore_decision, apply_restore, reconcile_recovery, journal_check |

MCP에서는 실제 tools/list의 이름·schema를 사용한다. 호스트 접두어나 자동 Skill 호출 API를 추측하지 않는다.

## 프로젝트와 산출물

project_register는 제품 절대 경로와 name을 받는다. 기존 폴더는 create_root=false, 명시된 신규 개발 범위의 빈 폴더 생성은 create_root=true다. 제품에 .git/.harness가 필요하지 않으며 제품·개인 state·공통 원본 루트는 겹치지 않아야 한다.

프로젝트 operation은 project_id를 받는다. create_run은 run_id/workspace_id/goal, start_stage는 run_id/skill/owner/input_refs와 필요 unit_id를 고정한다. finish_stage 입력 outcome과 조회용 stage_run_status를 구분한다. succeeded는 completed로 표시되며 대기/취소도 실제 schema enum을 사용한다.

artifact ref는 `{artifact_id, revision_id, sha256}`다. publish_artifact에는 StageRun과 정확히 같은 input_refs 배열, kind·payload·Markdown report가 필요하다. 기본은 candidate이며 accept_artifact 또는 accept=true와 조회한 expected_head로 accepted head를 CAS 발행한다. accepted는 인간 승인이 아니다.

manifest는 payload/report의 bytes/hash를 연결하고 자기 hash는 외부 ref에만 둔다. render_artifact는 개인 MD/HTML 조회 파일을 만들며 canonical 원장과 승인을 바꾸지 않는다.

최소 payload는 requirements의 id/description/case_ids, system-design의 requirement_ids, unit-spec의 requirement_ids/case_ids, test-plan의 정확한 unit_ref/checks다. 구현 범위를 제한할 때 UnitSpec에 allowed_paths를 명시한다. 상세 계약·실패 정책·근거는 각 Skill/profile을 따른다. 구현 receipt와 verification-report는 실제 실행 경로가 생성하며 일반 artifact 발행으로 꾸며 제출하지 않는다.

## 두 Gate와 구현

Gate A는 discovery-context + requirements + system-design 세 refs, Gate B는 unit-spec + 그 단위를 참조한 test-plan 두 refs와 유효 Gate A다. create_review가 만든 구체적 bundle에 실제 사용자 응답/source를 record_decision으로 연결한다.

begin_implementation은 현재 Gate·ChangeIntent·소스·lease를 확인하고 baseline을 확보한다. finish_implementation은 실제 변경과 post-snapshot을 기록한다. snapshot은 workspace 전체 기준이므로 다른 단위 변경 뒤 옛 receipt가 source_changed가 될 수 있다. 현재 workspace의 새 관찰 receipt와 모든 required check를 재실행해야 적용성을 갱신한다.

## 검사 parser와 중단 복구

check는 check_id, argv 배열, 안전 상대 cwd, timeout_seconds(1~300), required, expected_exit=0, case_ids, expected, oracle을 갖는다. evidence_mode/parser 생략 기본은 case-results/team-json이다.

```text
HARNESS_CASE_RESULTS={"cases":[{"case_id":"case-example","status":"passed"}]}
```

stdout에 정확히 한 marker가 있어야 하고 declared case ID와 결과 집합이 같아야 한다. 상태는 passed/failed/skipped다. 중복·누락·추가·0건·skip을 완료 근거로 쓰지 않는다. 명령 자체가 승인 인수 기준이면 command-exit/exit-code를 둘 다 명시한다. 현재 JUnit/unittest parser와 case_map 자동 매핑은 지원하지 않는다.

run_checks는 implementation_id/owner/request_id로 실제 실행한다. 같은 요청의 전송 재시도는 같은 ID, 새 재검증은 새 ID다. 이전 실패를 보존하고 source/plan/environment drift·증거 누락·timeout·외부 차단을 pass로 표시하지 않는다. get_verification의 실제 최신 결과와 eligible_complete를 함께 본다.

reconcile_execution은 kind, 원래 request_id, owner, action(status/reconcile)을 받는다. status는 조회다. controller/관리 child 종료가 확인돼야 중단 기록과 lease를 정리한다. implementation은 external_writers_stopped=true의 실제 외부 편집 중지 확인도 필요하다. 프로세스가 불명확하거나 TTL만 만료됐다고 소유권을 가져오지 않는다. 소스 rollback이나 검사 재실행과 별개다.

## 보존과 경계

개인 bare history Git에 사건·참조·원본 blobs를 보존하며 제품 Git 명령을 기록 수단으로 쓰지 않는다. 소스 정책·제외 파일·용량·링크·외부 서비스·비밀 탐지의 한계는 [지원 범위](support-boundaries.md)를 따른다.

복원은 export→구체적 plan→실제 결정→직전 사본/journal→충돌 확인→적용/사후 검증 순서다. reconcile_recovery는 source 복원 journal의 status/resume/rollback이며 관리 실행 정리인 reconcile_execution과 다르다.

이 실행기는 협조적 로컬 절차다. 같은 OS 계정의 외부 셸·편집기·서비스를 격리하거나 사용자 신원을 인증하지 않는다. Team Git 원격·외부 계정·운영 배포는 자동 구성하지 않는다.
