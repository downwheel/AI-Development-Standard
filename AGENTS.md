# 팀 개발 표준 배포 저장소 작업 지침

이 저장소는 Codex·Claude Code용 28개 스킬과 하네스, 기본 외부 도구 설치 원본이다. 설치 요청에는 현재 호스트의 START-HERE-CODEX.md 또는 START-HERE-CLAUDE.md를 따른다. 환경 설치에 제품 개발용 인터뷰나 설계 승인 절차를 추가하지 않는다.

- 공통 행동을 수정하면 `skills/codex`와 `skills/claude`의 대응 문서를 함께 검토한다. 호출 문법·메타데이터·설정 경로는 호스트별로 유지한다.
- 설치할 규칙은 `adapters`의 관리 블록이다. 이 루트 문서나 작성자의 개인 지침 전체를 팀원에게 복사하지 않는다.
- `manifest.json`이 배포 버전·파일 목록의 기준이다. `integrations/default-tools.json`은 기본 도구 설정의 기준이다. 개인 설정·토큰·plugin cache를 패키지에 넣지 않는다.
- 신규 테스트·fixture는 외부 Workspace의 `tests`, 임시 프로필·검사 결과는 `results`, 보고서는 `artifacts`에 둔다. 배포용 문서와 참조 자료는 이 저장소에 둔다.
- 수정 후 `python -B -X utf8 scripts/update_manifest.py`, `python -B -X utf8 scripts/verify_codex.py --package-only`를 실행한다. 격리된 양쪽 프로필에서 설치·반복 설치·충돌 보존을 검사한다.
- `verify_codex.py --native`와 `verify_claude.py --native`로 실제 스킬 인식을 확인한다. 모델 대화를 시작하지 않는다. 설치·인증·실제 도구 실행은 별도 결과로 보고한다.
- 외부 도구는 기존 설정을 보존해 없는 것만 구성한다. 계정 인증·권한 허용을 위조하거나 자동 확대하지 않는다. 백업은 공유하지 않는다.
- LICENSE를 유지한다. commit/push·원격 게시 요청이 없으면 로컬 변경과 패키지까지 완성한다.
