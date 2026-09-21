# 실제 검증 보고 항목

이 양식으로 결과를 만들기 전에 공개 runner로 검사하고 불변 attempt 결과를 확보한다. 실제 receipt를 대신 작성하는 양식이 아니다.

## 대상

구현 receipt·source snapshot, 승인된 TestPlan/UnitSpec refs, 환경·runtime/dependency 기준과 실행 시각을 적는다.

## 결과

check/case | attempt ID | 실제 argv/cwd | 판정 | 핵심 증거 | 실패/미실행 이유

실행기 결과를 그대로 근거로 삼고 pass·failed·blocked·중단·미실행을 구분한다. 실패를 숨기기 위해 옛 pass를 가져오지 않는다.

## 변경 감지와 제한

실행 중/후 source·계약·환경 drift, 누락 증거·외부 차단·부분 실행을 명시한다.

## 재현과 다음 행동

필요한 최소 로그·trace·화면, 재현 조건, 수정할 단계와 정확한 pins, 수정 뒤 필요한 새 검사를 기록한다. 제품 코드·테스트 기대값 변경은 검증 보고와 분리한다.
