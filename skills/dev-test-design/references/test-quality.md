# 검사 설계와 판정 품질

## 정답 근거

검사 case는 사용자 요구·승인 계약의 관찰 가능한 동작을 판정한다. production 함수를 호출해 expected 값을 만들거나 현재 출력/screenshot을 검토 없이 golden으로 채택하지 않는다. 작은 고정 사례, 독립 계산, 명시된 표준·수식·계약 fixture를 사용하고 oracle의 근거를 기록한다.

모든 요구를 같은 수의 테스트로 맞추지 않는다. 정상·잘못된 입력·경계값·권한·의존 장애·timeout/cancel·중복·이전 동작 중 위험에 맞는 조합을 고른다. 동작과 계약이 없는 구현 구조만 반복하는 검사는 피한다.

## 실행 계약

현재 공개 TestPlan check는 check_id, argv 배열, 안전 상대 cwd, 1~300초 timeout, required, expected_exit=0, case_ids, expected, oracle을 가진다. 실제 describe를 읽어 형식과 허용 범위를 확인한다.

- 프로젝트 공식 runner와 CI 명령을 우선하고 package/lockfile 버전과 맞춘다.
- check ID는 의미가 같은 검사에서 안정적으로 유지한다. 의미·expected·필수 여부가 바뀌면 새 계획 revision으로 기록한다.
- 실패가 예상되는 사례도 runner가 그 실패를 assertion으로 확인한 뒤 정상 종료하는 방식으로 작성한다.
- 외부 서비스·계정·비용·운영 쓰기는 계획에 분리한다. 대체 mock의 한계를 명시한다.
- fixture·DB·port·browser profile은 검사 간 충돌과 기존 사용자 세션 영향을 피하도록 격리한다.
- 필수 수동 검사나 미지원 검사 형식은 실행기가 지원한다고 꾸미지 않는다. 실행 가능한 대응과 남은 조건을 명시한다.

## UI와 회귀 검사

Playwright MCP는 탐색·재현·접근성 구조·screenshot·trace 조사에 사용한다. 지속 회귀 요구는 실제 프로젝트 테스트 파일/runner로 남긴다. 버튼 위치 한 장보다 키보드·focus·오류 복구·기다림·데이터/권한 상태 등 사용자 결과를 확인한다. screenshot golden 변경은 요구/디자인 변화와 검토 근거를 가져야 한다.

## 결과 해석

반환 코드만으로 모든 요구가 충족됐다고 말하지 않는다. assertion·대상 케이스·필수 증거와 실행 당시 source/계획/환경을 확인한다. source drift, 미실행, timeout, 인증/쿼터 차단, 제품 실패를 구분한다.

실패 로그·부분 결과·각 attempt는 보존한다. flaky 검사를 통과할 때까지 무제한 재실행하지 않는다. 재시도 사유와 한도를 정하고 마지막 pass가 앞 실패를 삭제하지 않게 한다. 새 테스트 요청은 실제로 새 실행한다. 검증 Skill은 제품 코드/테스트 의미를 바꾸지 않고 수정 단계에 실패 근거를 인계한다.

## 실제 parser 계약

기본은 evidence_mode=case-results, parser=team-json이다. stdout에 정확히 한 줄의 marker가 있어야 한다.

```text
HARNESS_CASE_RESULTS={"cases":[{"case_id":"case-example","status":"passed"}]}
```

status는 passed/failed/skipped 중 하나다. declared case_ids와 결과 case_id 집합이 정확히 같아야 하며 중복/누락/추가/0건/skip은 정상 완료로 판정하지 않는다. 기존 runner 결과를 adapter로 변환할 때 실제 실행한 case와 상태만 출력한다. 명령이 0으로 끝났다고 case 결과를 만들어 채우지 않는다.

build/lint/typecheck처럼 명령 완료 자체가 승인 인수 기준인 경우 evidence_mode=command-exit와 parser=exit-code를 둘 다 명시한다. 일반 기능 검증을 이 모드로 낮추지 않는다. 현재 JUnit/unittest parser와 case_map 자동 매핑은 지원하지 않는다.

## 준비와 첨부 계약

외부 서비스와 fixture가 필요하면 check의 `runner.kind`를 `project-runner`로 선언한다. 프로젝트의 기존 runner를 사용하며 공통 실행기는 시작/관찰/정리와 기록을 맡는다. runner와 health/fixture 구현 파일도 Gate B의 정확한 scope에 포함한다.

- `services`: service_id, argv, 상대 cwd, 사용할 role, 로컬 HTTP health_url, readiness_seconds. health는 `{build_id,run_id}`를 반환하고 값은 주입된 `HARNESS_BUILD_ID`/`HARNESS_RUN_ID`와 일치해야 한다. 점유된 포트는 기존 서버를 재사용하거나 종료하지 않고 차단한다.
- `fixture`: namespace와 setup/cleanup 각각의 argv/cwd/timeout/role/case_ids. setup과 cleanup에도 실제 team-json case marker가 필요하다. 소유한 namespace/키만 생성·검증·정리하고 기존 데이터 손실 없이 반복 실행한다. DB 자격증명은 해당 역할에서만 받는다.
- `evidence`: evidence_id, `HARNESS_EVIDENCE_DIR` 아래의 상대 path, text 또는 json format, required, max_bytes. 승인된 경로·한도·형식만 첨부하며 cookies/origins/auth token은 증거로 보관하지 않는다. 현재 binary screenshot/trace 자동 안전 첨부는 지원하지 않는다.

준비 실패, service build 불일치, fixture cleanup 실패, 필수 evidence 누락/초과는 제품 case가 통과해도 검증 완료가 아니다. Windows에서는 소유한 Job Object의 프로세스를 종료하며 사용자의 다른 서버나 DB 서비스를 중지하지 않는다.

기능이 DB 저장을 요구하면 사용자 흐름 → 서버 요청 → 실제 DB 관찰 → 새 연결/새로고침 후 복원까지 독립 기대값을 정의한다. mock을 사용하는 검사는 준비 없이 실행할 수 있는 범위를 표시하고 실제 DB 저장 성공을 대체하지 않는다. DB 작업의 예상/실제 객체·행 수·commit/rollback·cleanup receipt를 제품 E2E 증거와 연결한다.

현재 snapshot은 workspace 전체이므로 다른 단위의 편집 뒤 이전 receipt는 source_changed가 될 수 있다. 현재 소스에 대한 새 `observe` 구현 receipt와 모든 required check를 다시 실행하며 새 소스의 자동 부분 결과 승계를 가정하지 않는다. 모든 필수 단위/case를 마치면 `evaluate_completion`의 판정과 남은 blocker를 확인한다.
