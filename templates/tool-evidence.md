# 외부 도구 관찰과 검사 증거

실제 도구 응답을 읽고 기록하는 양식이다. 이 파일이나 아래 예시는 성공 증거가 아니다. 상세 typed result는 같은 release의 contracts/artifact-payloads.json 및 contracts/tool-policy.json을 따른다.

## 설계 관찰

- 적용 capability와 단위, provider와 실제 tool 이름.
- success/fallback/blocked, 시간대가 포함된 관찰 시각, 허용 대상, 확인한 내용.
- 실제 공개 source URL 또는 core에서 받은 artifact ref. 비밀 포함 URL·만든 hash 금지.
- Figma이면 실제 file/node와 구조·screenshot 재확인. local_only이면 사용자 선택, preferred 대체이면 실제 Figma failure와 구체적인 HTML/SVG·화면 계약.
- 문서이면 실제 library/version/ID, 공식 원문, 설치 타입·SDK 대조 범위와 설계 결정. fallback이면 실제 우선 도구의 차단.
- DB이면 실제 대상·read_only·catalog/readback·관찰 행 수·객체·기대값과 결과.

## 실제 검증 첨부

TestPlan.tool_checks의 capability(browser/database)·check_id·evidence_id를 required project-runner JSON evidence와 연결한다. envelope에는 tool_policy_version="1", capability, 현재 HARNESS_BUILD_ID, 현재 HARNESS_RUN_ID, 실제 observation을 넣는다.

브라우저 observation에는 실제 URL·engine·session·상호작용 수·기대값/관찰을, DB에는 실제 readback과 row/object/assertion을 담는다. 이전 build의 파일, mock, API 성공 표시, 설계 때 catalog만으로 완료하지 않는다. 별도 지속 회귀 runner의 case 결과와 혼동하지 않는다.

실행기가 보존한 attachment와 build/run 연결이 근거다. stdout/JSON 제출은 공급자 호출의 독립 인증이 아니며 실제 응답 없이 JSON을 만드는 것은 허용되지 않는다. 원문 인증 정보·업무 데이터·개인 브라우저 세션을 첨부하지 않는다.
