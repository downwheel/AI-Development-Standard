# Git 배포와 Sourcetree 사용

공통 표준 배포 저장소는 [downwheel/AI-Development-Standard](https://github.com/downwheel/AI-Development-Standard)다. 비공개 저장소이며, 팀원은 자신의 GitHub 계정으로 접근 권한을 받은 뒤 clone한다. GitHub는 공통 원본 보관 서비스이고 Sourcetree는 각자의 컴퓨터에서 clone·변경 조회·업데이트를 하는 Git 클라이언트다.

## 접근 권한과 계정

저장소 소유자는 초대할 팀원의 GitHub 사용자명을 확인하고 저장소 Settings → Collaborators에서 접근 권한을 부여한다. 팀원이 초대를 수락한 뒤 자신의 계정으로 인증한다. 저장소 주소만 알아서는 비공개 원본을 받을 수 없다. [GitHub 공식 초대 절차](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository)

GitHub의 개인 저장소 권한 문서는 collaborator의 읽기와 쓰기를 함께 설명한다. 따라서 기본 collaborator 초대를 **읽기 전용 배포 권한으로 간주하지 않는다**. 초대할 때 실제 부여 권한을 확인하고, 읽기 전용 사용자와 표준 유지보수자의 역할을 확실히 나눠야 하면 조직 저장소의 권한 모델을 검토한다. [GitHub 공식 권한 설명](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/permission-levels-for-a-personal-account-repository)

소유자 계정·토큰·SSH 개인키를 공동 사용하지 않는다. 팀원은 자신의 GitHub 인증을 Sourcetree의 계정 연결 또는 자신이 사용하는 Git 인증 관리 방식으로 설정한다. Codex/Claude 로그인과 GitHub 인증도 별개다. 자격증명을 clone URL, 문서, 공통 Git, 채팅에 넣지 않는다.

## Sourcetree에서 받기

1. Sourcetree의 Clone 기능을 연다. 버전에 따라 Clone/New 또는 Clone from URL로 표시될 수 있다.
2. Source URL에 `https://github.com/downwheel/AI-Development-Standard.git`을 입력한다.
3. Destination Path에는 표준 전용의 새 로컬 폴더를 선택한다. 제품 소스 폴더와 개인 기록 폴더의 안이나 상위 폴더를 선택하지 않는다.
4. 자신의 GitHub 계정으로 인증해 clone한다. 실패하면 초대 수락·현재 인증 계정·저장소 접근 권한을 확인한다.
5. README, install.py, skills, harness, docs가 보이는지 확인한다. 최신 commit과 기본 branch를 확인하고, 배포 담당자가 지정한 tag 또는 commit이 있다면 그 revision을 사용한다.

Sourcetree의 clone은 원격 내용을 로컬 작업 사본으로 가져오는 단계다. 별도 호스트 설정을 설치하거나 제품 개발을 시작하는 단계는 아니다. [Atlassian 공식 clone 안내](https://support.atlassian.com/sourcetree/kb/clone-a-repository-into-sourcetree/)

CLI를 사용하는 팀원도 같은 원본을 받을 수 있다. 다음 경로 자리표시자는 자신의 표준 전용 목적지로 바꾼다.

```text
git clone https://github.com/downwheel/AI-Development-Standard.git "<standard-clone>"
```

## clone 다음에 설치하기

Python 3.10 이상과 Git이 필요하다. 공통 clone, 개인 기록, 제품 폴더를 서로 겹치지 않게 정하고, 공통 clone의 터미널에서 [팀원 온보딩](team-onboarding.md)에 따라 plan을 먼저 확인한다.

```text
python -B -X utf8 install.py plan --profile "<personal-profile>" --state-root "<personal-state>" --python "<python-executable>"
python -B -X utf8 install.py install --profile "<personal-profile>" --state-root "<personal-state>" --python "<python-executable>"
```

`<personal-profile>`은 사용할 도구의 사용자 홈, `<personal-state>`는 두 도구에서 접근할 별도 개인 로컬 폴더, `<python-executable>`은 실제 Python 실행 파일의 절대 경로다. 앱에 따라 경로가 달라질 수 있는 AppData 자동 기본값 대신 개인 기록 위치를 명시한다. 설치 결과와 백업은 개인 영역에만 남긴다.

설치기는 두 호스트용 Skill/MCP 설정을 준비하지만 Codex나 Claude Code 자체를 설치·로그인시키지는 않는다. [START-HERE.md](../START-HERE.md)를 통해 사용할 호스트를 준비한 뒤 새 세션에서 release에 선언된 Skill(2.1은 12개)과 `team_harness`의 실제 로딩을 확인한다. 한 호스트만 써도 된다. 외부 MCP는 필요한 서비스를 각자 연결하며, 다른 사람의 설정 파일을 통째로 복사하지 않는다.

공통 clone에는 제품 소스·설계 결과·승인 기록·검사 로그·설치 receipt·소스 snapshot·가상환경·의존성·개인 JSON을 만들지 않는다. `.gitignore`는 Git의 기본 추적 선택을 돕는 파일이며, 개인 데이터의 저장 위치를 분리하거나 배포 내용을 검토하는 일을 대신하지 않는다.

## 업데이트와 세 종류의 되돌리기

| 작업 | 바뀌는 대상 | 개인 제품 기록에 미치는 영향 |
|---|---|---|
| Sourcetree에서 공통 원본 fetch/pull 또는 revision 선택 | 공통 clone의 Skill·실행기·계약·문서 | 설치된 release와 개인 기록은 자동 변경되지 않음 |
| install.py로 새 release 설치 또는 receipt 기반 설치 rollback | 개인 호스트 설정과 설치 release 선택 | 기존 개인 이력과 이전 고정 release를 보존함 |
| dev-restore로 소스 export 또는 승인된 복원 실행 | 선택한 제품 파일 사본 또는 실제 제품 파일 | 별도 preview·충돌 확인·복원 증거를 남김 |

업데이트할 때는 먼저 Sourcetree에서 공통 clone의 미커밋 변경을 확인한다. 표준 수정 중이라면 그 변경을 해결한 뒤 합의된 배포 revision을 받는다. 제품이나 개인 기록의 Git을 대신 조작하지 않는다. 새 원본에서 plan → 검토 → install한 뒤 호스트를 재시작하고 다시 확인한다.

공통 Git에서 옛 commit을 선택하는 것만으로 설치된 Skill이나 개발 중인 제품이 돌아가지는 않는다. 설치를 되돌릴 때는 [온보딩의 receipt 기반 rollback](team-onboarding.md#업데이트돌리기)을 사용한다. 이전 run은 시작 당시 release에 고정되므로 같은 개인 state와 공통 source_root를 전달해 해당 고정 실행기로 재개한다. 옛 release를 삭제하거나 승인 기록을 새 release로 바꿔 끼우지 않는다.

개인 개발 이력의 bare Git에는 기본 remote가 없다. 이를 공통 저장소 origin에 연결하거나 push하지 않는다. 제품의 기존 Git도 기존 개발 정책대로 유지한다. 공통 표준의 commit/push는 표준을 유지보수하는 작업에서만 수행한다.

## 배포 담당자 확인

공통 원본만 변경 목록에 포함되었는지 확인하고 테스트 결과를 별도 개인 영역에 보관한다. 한 commit의 설치 release는 파일 bytes를 기준으로 만들어지므로 저장소의 `.gitattributes` 줄바꿈 규칙을 유지한다. 배포 후 새 clone에서 설치 plan과 호스트 연결을 확인하고, 검증한 Git revision과 설치 release를 구분해 기록한다.

이 문서의 절차 자체는 특정 사용자의 초대·로그인·clone·설치·호스트 검증이 완료됐다는 증거가 아니다. 실제 완료 여부는 해당 컴퓨터의 개인 진단 결과로 확인한다.
