# 실제 검증 보고 항목

이 양식으로 결과를 만들기 전에 공개 runner로 검사하고 불변 attempt 결과를 확보한다. 실제 receipt를 대신 작성하는 양식이 아니다.

## 대상

구현 receipt·source snapshot, 승인된 TestPlan/UnitSpec/scope/환경/DB refs, 역할별 probe·runtime/dependency 기준과 실행 시각을 적는다.

## 결과

check/case | attempt ID | 실제 argv/cwd | 판정 | 핵심 증거 | 실패/미실행 이유

실행기 결과를 그대로 근거로 삼고 pass·failed·blocked·중단·미실행을 구분한다. 실패를 숨기기 위해 옛 pass를 가져오지 않는다.

서비스의 소유권/build/health, fixture setup/cleanup, 필수 text/JSON 증거 첨부/hash/마스킹을 표시한다. DB가 있으면 계획 대비 실제 객체/action/영향 행 수·시간·commit/rollback·새 연결 검증·정리 상태를 연결한다. 실제 DB를 연결하지 않은 검사로 DB 저장 완료를 주장하지 않는다.

## 변경 감지와 제한

실행 중/후 source·계약·환경 drift, 누락 증거·외부 차단·부분 실행을 명시한다.

전체 작업 완료는 `evaluate_completion`의 required 단위/case 수, live 검증 결과, 남은 blocker를 함께 표시한다. 다른 단위의 소스 변경으로 이전 검증이 오래됐으면 observe receipt와 실제 재검사가 필요하다.

## 재현과 다음 행동

필요한 최소 로그·trace·화면, 재현 조건, 수정할 단계와 정확한 pins, 수정 뒤 필요한 새 검사를 기록한다. 제품 코드·테스트 기대값 변경은 검증 보고와 분리한다.

## 외부 도구 계약 확인

도구별 적용 단위·mode·필수 결과, 실제 호스트 준비도, 사용한 근거·차단·승인한 대안을 보여준다. Gate A/B와 실제 검증의 결과를 구분한다. 미적용에는 제품 범위 이유를, 미실행에는 실제 차단 이유를 적는다. browser/database의 필수 tool_checks와 첨부 출처/현재 실행 연결을 확인한다. 협조적 관찰 제출을 공급자 호출 인증으로 표현하지 않는다.
