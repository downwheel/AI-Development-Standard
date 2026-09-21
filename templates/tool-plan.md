# 외부 도구 사용 계획

SystemDesign의 tool_plan과 사람이 읽는 Gate A 자료에 사용한다. core 계약은 2.1, 해당 run의 도구 정책은 1인지 먼저 확인한다.

| capability | mode | 적용 unit_ids | 제품상 이유 | 필요한 결과 | 차단 시 대안/영향 |
|---|---|---|---|---|---|
| ui_design | UI이면 기본 preferred | 실제 unit ID | 사용자 과업·디자인 요구 | native 화면·상태와 재조회 | Gate A에 승인한 로컬 대안; required는 대체 완료 불가 |
| library_docs | required 또는 not_applicable | 실제 unit ID | 버전 의존 선택 여부 | Context7/OpenAI Docs·공식 원문·설치 타입 근거 | 실제 원인+공식 문서 대체 |
| browser | UI이면 required | UI 단위 전체 포함 | 실제 과업 검증 | 브라우저 관찰+별도 회귀 runner | 미실행은 미완료 |
| database | required 또는 not_applicable | DB 관련 unit | 데이터 구조·저장 요구 | 실제 조사·정량 계획·재조회 | mock 대체 불가 |

위 표는 작성 안내이며 실행 가능한 JSON이나 실제 승인 기록이 아니다. 네 capability는 각각 한 행이며 적용이면 알려진 unit ID가 한 개 이상, not_applicable이면 unit_ids가 빈 배열이어야 한다. preferred/local_only는 UI 전용이다. local_only는 실제 사용자 선택 출처가 필요하다.

SystemDesign.tool_observations에는 적용 문서 근거를 고정한다. UnitSpec에는 해당 단위의 디자인/문서/DB 관찰을 고정한다. 실제 contracts/artifact-payloads.json·contracts/tool-policy.json schema와 [필수 근거 안내](../docs/v2.2-tools.md)를 읽고 작성한다. 없던 source ref·성공한 조회·사용자 결정을 만들지 않는다.
