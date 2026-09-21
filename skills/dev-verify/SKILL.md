---
name: dev-verify
description: Run the approved verification plan against an identified implementation snapshot and preserve every real attempt, failure, block, and source drift. Use for final verification or a new retest request; showing old results is read-only.
---

# 실제 검증

[실행 계약](references/runtime.md)과 [검사 설계 기준](references/test-quality.md)을 읽는다. 정확한 승인 TestPlan·UnitSpec·구현 receipt·source snapshot을 받는다.

## 실행

1. “지난 결과 보여줘”는 기존 attempt만 조회한다. “다시 테스트해줘”는 새 실제 실행 요청이다. 같은 request ID의 전송 재시도만 기존 실행을 재사용한다.
2. 현재 승인·정확한 scope·환경 역할/현재 probe·DB 계획 대비 실제 receipt·소스/runtime/dependency를 확인한다. 계획과 구현의 단위나 pins가 다르면 검사 전에 차이를 해결한다. dependency 관찰 한도와 reparse 제한을 무시하고 연결 성공으로 대체하지 않는다.
3. 공개 스키마에서 검사 실행 operation과 입력을 읽는다. `run_checks`가 있으면 승인된 계획을 실제 실행한다. 임의 JSON 보고서로 실행을 대신하지 않는다. 직접 runner를 써야 할 경우 공식 지원 기록 경로가 없으면 미기록 제한을 명시한다.
4. case/check별 argv·cwd·시간 제한·환경과 예상 결과를 지킨다. 반환 코드뿐 아니라 assertion·결과·필수 증거를 읽는다. 실패 시 필요한 최소 로그·스크린샷·trace를 보관하고 민감 정보는 제거 사실과 함께 처리한다.
   기본 case-results/team-json의 실제 case ID와 상태가 계획과 정확히 맞는지 확인한다. marker 누락·중복·0건·추가/누락 case·skipped를 pass로 바꾸지 않는다. 명령 완료만 판정하는 command-exit/exit-code와 구분한다.
5. tool_checks로 지정한 필수 capability 증거를 실제 검사/관찰과 대조한다. UI는 실제 브라우저의 승인 과업·기대 결과를 관찰하고 지속 회귀 runner도 별도로 검증한다. 공급자 응답에 근거한 관찰을 계획된 text/JSON evidence로 수집하되 결과·호스트·시간·대상·출처를 실제 범위로 적는다. stdout 제출만으로 MCP 호출 인증이 됐다고 주장하지 않는다. 필수 관찰 누락·skip·권한/쿼터 차단은 미완료다.
6. 실행 중/후 source manifest와 계약·환경 변경을 검사한다. drift가 있으면 명령이 0으로 끝나도 현재 제품의 pass로 만들지 않는다.
7. 준비 receipt의 service 소유권/build/health, fixture setup/cleanup case, 필수 text/JSON evidence의 실제 첨부/hash/마스킹을 확인한다. 저장 요구는 UI 성공 표시 외에 승인된 기대값으로 실제 DB의 재조회 결과를 검증한다. fixture 데이터 정리는 해당 namespace/키로 제한하고 기존 사용자 데이터를 지우지 않는다.
   모든 실제 시도를 불변 기록으로 보존한다. pass/failed/blocked를 구분하며 미실행·중단·취소를 pass로 바꾸지 않는다. 필수 검사나 cleanup/evidence가 실패·차단이면 전체 검증 완료라고 말하지 않는다.
8. 실행기가 반환한 불변 verification 결과와 사람이 읽는 보고서를 제공한다. 실행 대상·승인 계획·attempt ID·실제 명령·결과·근거·미실행 이유·위험·다음 행동을 연결한다. 공개 publish_artifact가 verification-report kind를 지원하지 않으면 그 kind를 전송하지 않는다. 실행기의 실제 보존/조회/보고 기능을 사용하며 원시 attempt가 권위 근거다.

## 재검증·실패 조사

새 실행에서 실패하면 옛 pass로 최신 상태를 덮지 않는다. 같은 소스/계획/검사/환경/dependency 키의 일부 재사용은 실행기가 명시적으로 지원하는 경우 출처를 표시하며, 사용자가 재실행을 요청한 검사는 실제로 다시 실행한다.

현재 전체 workspace snapshot 기준이므로 다른 단위 변경으로 이전 receipt가 source_changed가 되면 `begin_implementation(mode:observe)`로 현재 소스의 새 관찰 receipt를 만들고 모든 required check를 재실행한다. observe 중 소스나 DB를 변경하지 않는다. 자동 부분 결과 승계가 있다고 가정하지 않는다. 모든 required 단위가 준비되면 `evaluate_completion`의 live 결과로 전체 완료 여부와 남은 blocker를 확인한다.

제품 결함은 `dev-implement`, 계약/기대값 오류는 해당 설계 단계로 정확한 pins와 실패 증거를 넘긴다. 검증 Skill이 테스트를 삭제·약화하거나 제품을 몰래 수정하지 않는다. 수정 후 새 구현 receipt와 필요한 새 시도를 만든다.

Playwright MCP 탐색은 재현·화면 관찰 근거다. 저장된 회귀 테스트 runner 결과와 구분한다. Figma 구조·스크린샷 비교도 정의된 UI 인수 기준으로 검토하며 서비스 연결 확인을 제품 검증으로 확대하지 않는다. stage의 보고서 작성 완료와 제품 verified 상태는 서로 다르다.
