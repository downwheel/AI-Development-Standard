# Skill forward-test 결과

이 문서는 2.0 당시 11개 Skill 시험 기록을 보존한 자료다. 2.1의 현재 검증은 설치 담당자가 최신 스크립트를 실행해 개인 영역에 새 보고서를 남긴다. 아래 과거 결과를 현재 release의 시험 증거로 재사용하지 않는다.

합성 시나리오를 사용해 Skill 지침과 실제 CLI 연결을 확인했다. **기존 웹 프로젝트 시나리오 42개 확인, 신규 빈 폴더 등록 smoke 3개 확인이 통과했다.** 제품 변경·승인·검사 기록은 모두 격리 fixture에만 만들었다. 실제 고객 프로젝트·외부 계정·호스트 설치·Team Git은 변경하지 않았다.

## 시험 방법과 재현

요청은 “기존 웹 프로젝트에 설정 화면을 추가하고 싶어”로 고정했다. ES module 웹과 기존 홈 화면, 사용자의 staged/unstaged/untracked 변경이 있는 임시 제품을 만들었다. 설정 범위는 화면 진입·기본값·입력 검증·로컬 저장과 오류 복구이며 실제 테마 적용·백엔드·인증·배포는 제외했다.

실제 11개 SKILL.md와 자체 포함 runtime 참조, 6개 산출물 양식을 읽고 그 계약으로 조사→요구→시스템→단위→테스트 계획을 작성했다. 공개 CLI의 describe를 확인한 뒤 실제 operation만 호출했다. Gate 진행을 위한 두 결정은 **합성 시험 승인**으로 명시했으며 실제 사용자 승인으로 취급하지 않는다.

재현 스크립트는 [scripts/skill_forward_test.py](../scripts/skill_forward_test.py)다. Python, Git, Node.js가 필요하며 신규 임시 fixture를 만들고 검사 후 보존한다. 실제 개인/제품 경로는 스크립트에 하드코딩하지 않는다.

```text
python -B -X utf8 scripts/skill_forward_test.py --output "<personal-forward-test-result.json>"
python -B -X utf8 scripts/skill_forward_test.py --registration-only --output "<personal-registration-result.json>"
```

출력 경로는 공통 원본 밖이어야 한다. 생략하면 보존된 임시 fixture 안에 결과 JSON을 만든다. JSON은 실제 CLI operation/종료 코드·확인 결과·산출물 pins·읽은 Skill hash를 보존한다. 공통 문서에는 개인 경로와 원본 실행 기록을 넣지 않는다.

## 확인한 결과

| 범위 | 실제 확인 |
|---|---|
| 개별 Skill·자료 | 11개 Skill과 packaged runtime 읽기, 6개 양식 사용 가능 |
| 스키마 조회 | describe만으로 개인 registry/history가 생성되지 않음 |
| 기존 프로젝트 등록 | 제품 파일/.git/.harness를 새로 만들거나 변경하지 않음 |
| Gate A | 미승인 상태의 단위 설계·구현 진입 차단, 실패한 호출이 원장 변이 없음 |
| 정확 인계 | TestPlan이 정확한 UnitSpec artifact/revision/hash를 참조 |
| Gate B | 시스템 승인만 있을 때 구현 진입 차단 |
| 후보·발행 구분 | 탐색 candidate가 accepted head를 대체하지 않음 |
| 자료 조회 | get/list/diff/status/render 후 원장 bytes와 Git tip, 제품 bytes가 동일 |
| 사용자 자료 | render가 실제 Markdown 파일을 반환하고 canonical_changed=false |
| 구현 | 두 합성 승인 이후에만 허용 경로의 fixture 소스·검사 파일 작성 |
| 실제 검사 | Node에서 5개 독립 case assertion과 실제 marker 출력 후 passed |
| 재호출 | 동일 request ID는 같은 campaign, 새 요청은 새 실행 |
| 실패 보존 | 후속 요청의 의도적 실패가 남고 이전 pass로 현재 완료를 숨기지 않음 |
| snapshot·복원 | .env/.git 제외, 별도 폴더 export 검증, 미승인 원본 적용 차단 |
| 제품 Git·사용자 변경 | 전체 관찰 .git bytes와 staged/unstaged/untracked 사용자 파일 보존 |
| 신규 폴더 smoke | create_root=true로 빈 폴더 등록 후 dev-discover 시작 가능, 제품 코드/.git/.harness 없음 |

실행 환경은 Python 3.10.9와 Node.js v22.23.2였다. 원래 시나리오 42개와 후속 신규 등록 3개는 별도 실행 결과다. 이후 재현 스크립트에는 신규 등록 smoke를 기본 전체 실행에도 포함했다. 이 차이를 한 번의 45개 실행으로 표현하지 않는다.

## 발견하여 반영한 사항

1. 신규 폴더가 없을 때 무조건 생성하지 않던 조사 지침은 실제 registry 계약과 맞지 않았다. 사용자가 신규 개발과 대상 경로를 지정한 범위에서는 create_root=true로 빈 폴더 등록을 허용하고, 경로가 미정일 때는 질문·독립 준비로 분리했다. 추가 smoke 3개로 확인했다.
2. 검사 안내에 실제 case 결과 parser 계약을 반영했다. 기능 사례는 case-results/team-json의 정확한 ID·상태를 요구하며 command-exit/exit-code와 구분한다.
3. workspace 전체 snapshot 때문에 다른 단위 변경 후 옛 receipt가 현재 소스에 적용되지 않을 수 있음을 명시했다. 새 관찰 receipt와 필수 검사 재실행이 필요하다.
4. 팀 공통 문서의 호스트 상태를 조건화했다. 특정 개발자의 Claude 설치 여부를 모든 팀원의 기본 규칙으로 만들지 않는다.

## 이 결과로 확인하지 않은 것

이 시험은 브라우저 DOM 조작·반응형 rendering·키보드/focus·시각 품질 E2E를 실행하지 않았다. case-open은 소스의 navigation 선언과 기존 홈 구조 계약을 확인하고, 나머지는 설정 helper의 독립 단위 계약을 Node로 검사했다. 이를 전체 설정 화면의 브라우저 검증이라고 표현하지 않는다.

Figma native 작성, Context7·DB·Playwright MCP 계정 연결, Codex/Claude native Skill discovery는 이 시나리오에서 실행하지 않았다. [doctor](team-onboarding.md#진단과-공통-시험)의 호스트 확인과 외부 계정별 최소 기능 확인이 별도다.

이번 평가는 고정된 합성 요구를 CLI로 진행한 forward-test다. 여러 모델·호스트의 자동 Skill 선택 품질이나 장기적인 자율 개발 성공률을 측정한 벤치마크가 아니다. 실행기 중단·parser 실패 행렬·설치 충돌 등은 공통 unittest의 별도 범위다.
