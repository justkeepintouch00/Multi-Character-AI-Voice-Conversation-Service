# Conversation·Message 최소 API 구현 기록

> 작성 시각: 2026-08-11 12:06 KST  
> 대상: 2026-09-02 MVP의 C 모드 TALK 수직 경로  
> 인증: 개발용 고정 사용자, 운영 인증 아님

## 1. 구현 API

| Method | Path | 설명 |
|---|---|---|
| POST | `/api/v1/conversations` | TALK 대화 생성 |
| GET | `/api/v1/conversations/{conversation_id}` | 개발 사용자 소유 대화 조회 |
| POST | `/api/v1/conversations/{conversation_id}/complete` | 대화 완료 |
| POST | `/api/v1/conversations/{conversation_id}/messages` | 사용자 메시지 저장, Scene Director 호출, AI 메시지 저장 |
| GET | `/api/v1/conversations/{conversation_id}/messages` | 메시지 목록 조회 |

PRACTICE·SCENARIO 모드, 목록 pagination, archive, cancel, Job API는 포함하지 않는다.

## 2. 개발 사용자와 고정 캐릭터

실제 로그인 대신 다음 환경변수로 개발 사용자를 식별한다.

```dotenv
DEV_USER_EXTERNAL_ID=local-development-user
DEV_USER_DISPLAY_NAME=개발 사용자
```

첫 Conversation 요청 시 해당 사용자가 없으면 `users`에 생성한다. 이어서
`character_a`, `character_b`에 필요한 template, version, instance를 최소 범위로
준비한다. 외부 API에는 문자열 ID를 사용하지만 PostgreSQL FK에는 실제
`character_instances.id` UUID를 저장한다.

`character_b`는 캐릭터 기획이 확정되지 않은 개발용 플레이스홀더다.

## 3. Message 트랜잭션 순서

```text
Conversation ACTIVE 확인
→ 사용자 Message 저장·commit
→ 최근 대화 최대 12개 조회
→ Scene Director 외부 호출
→ ScenePlan + AI Message 1~2개 저장·commit
→ 응답 반환
```

사용자 원문을 외부 호출 전에 commit하므로 OpenAI 장애가 발생해도 사용자
메시지는 유지된다. 현재는 idempotency key와 실패 Job 레코드가 없으므로 같은
요청을 수동 재시도하면 사용자 메시지가 중복될 수 있다. 이 문제는 Job 구현 시
보완한다.

## 4. 사용 예시

대화 생성:

```json
{
  "mode": "TALK",
  "character_ids": ["character_a", "character_b"]
}
```

메시지 전송:

```json
{
  "content": "오늘 회사에서 조금 힘들었어.",
  "input_mode": "TEXT"
}
```

음성 입력은 STT API 결과를 `content`에 넣고 `input_mode`를 `VOICE`로 지정한다.
Message API는 텍스트 ScenePlan과 저장된 AI 메시지를 반환한다. 음성 재생은 각
AI 메시지를 TTS API에 전달해 별도로 수행한다.

## 5. 검증 상태

자동 테스트:

```text
25 passed
1 skipped: 선택형 PostgreSQL rollback 통합 테스트
```

검증한 항목:

- Conversation·Message 요청/응답 계약
- 고정 캐릭터 수 제한
- 존재하지 않는 캐릭터 차단
- 완료된 대화에 대한 Message 차단
- 사용자 Message 저장 후 Scene Director 호출 순서
- 현재 사용자 메시지가 recent history에 중복되지 않음
- AI Message 응답 구조
- 메시지 목록 limit 1~100 검증

실제 PostgreSQL 통합 테스트는 `RUN_POSTGRES_TESTS=1`일 때만 실행되며 모든 변경을
외부 transaction에서 rollback한다.

```powershell
$env:RUN_POSTGRES_TESTS='1'
python -m pytest tests/test_conversation_repository_integration.py -q
Remove-Item Env:RUN_POSTGRES_TESTS
```

2026-08-11 12:06 KST 현재 `backend/.env`에 `DATABASE_URL`이 없어 기본 비밀번호
`postgres`로 접속을 시도했고 인증에 실패했다. 실제 DB 왕복 검증을 위해서는
`DATABASE_URL`을 복구해야 한다.

## 6. 다음 구현 대상

1. 실제 `DATABASE_URL`로 rollback 통합 테스트 통과
2. 실제 OpenAI API key로 Message→Scene Director 1회 검증
3. 프론트 C 모드에서 Conversation·Message 연결
4. TTS 중단과 Message `interrupted` 반영
5. 이후 idempotency·Job·Worker

Memory, Scenario, Realtime WebSocket은 위 수직 경로 검증 후 구현한다.
