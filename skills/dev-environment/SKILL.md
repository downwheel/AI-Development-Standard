---
name: dev-environment
description: Configure private typed environment profiles and role-specific credentials, probe connection readiness, and publish pinned environment contracts for development units.
---

# 개인 개발 환경

[실행 계약](references/runtime.md)을 읽는다. 프로젝트 등록 전에도 사용자별 `.env`와 역할 연결을 준비할 수 있다. 특정 제품·기존 프로젝트의 DB·계정을 새 요청에 자동 적용하지 않는다. 실제 계정 로그인은 호스트·서비스별 기본 연결 절차를 사용한다.

## 프로필 준비와 관찰

1. 현재 runtime의 개인 state 경로와 사용자가 지정한 profile ID, 필요한 대상 종류·역할을 확인한다. 이미 설정된 프로필은 `environment_inspect`로 값의 존재·형식·현재 binding을 조회한다. 원문 `.env`를 도구 출력이나 채팅에 표시하지 않는다.
2. 필요한 키·형식·역할·실행 변수 매핑을 설계한다. 새 SQL Server 프로필에는 고정 release의 `templates/environment/sqlserver.profile.json`을 읽는다. 다른 공급자는 현재 공개 schema와 실제 어댑터 지원 여부를 확인한다. `environment_plan`에 실제 인증 값이 없는 profile을 전달하고 구체적 변경을 확인한 뒤 허용된 설정 범위에서 `environment_apply`를 실행한다.
3. 생성된 개인 `secrets/.env`의 실제 경로와 필요한 키 설명을 사용자에게 제공한다. 기존 `.env`는 덮어쓰지 않는다. 실제 값은 사용자가 로컬에서 입력한다. 값을 입력하지 않았다면 준비된 빈 파일과 연결 미검증을 구분한다.
4. 대상·역할별 `environment_probe`를 실행한다. 성공, 필수 값 누락, 드라이버 미설치, 연결·권한 실패를 구분한다. 다른 계정으로 우회하거나 인증 값을 argv·설정 JSON·보고서로 복사하지 않는다. SQL Server 절차는 [프로필 연결 계약](references/profiles.md)을 읽는다.

## 호스트별 외부 도구 준비

외부 도구가 필요한 작업은 현재 호스트의 Figma·Context7/OpenAI Docs·브라우저·DB 설정 존재, 도구 노출, 인증, 허용된 대상 읽기와 쓰기를 따로 확인한다. 다른 호스트의 연결 결과를 재사용해 성공으로 표시하지 않는다. 공통 설치가 각 공급자 계정을 연결하는 것은 아니다. 기존 연결을 보존하고 필요 없는 중복 서버나 계정 변경을 만들지 않는다. 사용자 인증은 로컬 공급자 절차로 안내하고 비밀을 입력 payload나 산출물에 넣지 않는다. 도구별 관찰은 현재 artifact schema로 남기며 SQL profile/probe receipt로 Figma 등 다른 서비스 인증을 표현하지 않는다.

## 단위의 환경 계약

유효 Gate A 이후 정확한 UnitSpec pin을 입력으로 `dev-environment` StageRun을 시작한다. 해당 단위가 환경을 필요로 하면 실제 성공한 probe receipt에서 `profile_id`, `profile_revision`, `target_revision`, 사용할 `roles`를 고정하여 `environment-contract`를 발행한다. 단일 역할은 `probe_receipt_id`, 여러 역할은 **모든 역할의** `role_probe_receipts` 맵을 사용한다. 필요 시 확인한 `target_ref`를 넣는다. 비밀 값·연결 문자열·private HMAC 자료는 포함하지 않는다.

Markdown에는 키 이름·역할별 용도·연결 준비도·실제 관찰·미검증·환경 계약 변경 조건을 쓴다. 정확한 ref를 `dev-unit-design`의 범위/DB 계획과 `dev-test-design`에 넘긴다. 사용자에게 승인된 범위와 같은 환경 계약이 Gate B에 묶인다.

암호만 바뀌어도 새 probe가 필요하다. 대상·역할 구성·관찰된 계정/권한이 같으면 기존 환경 계약을 재사용할 수 있다. 대상·구성·계정/권한이 달라지면 해당 계약과 Gate B를 갱신한다. 파일 준비·연결 성공·제품의 DB 저장 성공은 각각 별도의 결과다.
