# Groq Scene Director 전환 및 프로젝트 의사결정 기록

> 작성: 2026-08-11 13:35 KST  
> 목표: 2026-09-02 MVP  
> 범위: Scene Director LLM 공급자 변경과 현재 프로젝트의 미확정 항목 정리

## 1. 이번에 확정하여 구현한 내용

- Scene Director 공급자를 OpenAI에서 Groq로 변경했다.
- 기본 모델은 Groq의 운영용 모델 `llama-3.3-70b-versatile`이다.
- 호출 API는 `POST /openai/v1/chat/completions`다.
- Llama 모델에는 JSON Object Mode를 적용하고 Pydantic 검증 실패 시 최대 2회 호출한다.
- `openai/gpt-oss-20b`, `openai/gpt-oss-120b`를 설정하면 Groq의 Strict Structured Outputs를 자동 사용한다.
- Conversation/Message API 계약과 PostgreSQL 스키마는 변경하지 않았다.
- STT는 OpenAI, TTS는 Typecast를 유지했다.

Groq는 모델 자체가 아니라 여러 모델을 제공하는 추론 API 공급자다. 따라서 "Groq를 사용한다"와 "어떤 모델을 사용한다"는 별개의 결정이다.

## 2. 실행에 필요한 설정

실제 `backend/.env`에 다음 항목을 추가한다. API Key는 저장소에 커밋하지 않는다.

```dotenv
GROQ_API_KEY=실제_Groq_API_KEY
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_SCENE_MODEL=llama-3.3-70b-versatile
GROQ_SCENE_MAX_ATTEMPTS=2
```

기존 가상환경을 다시 만들거나 새 패키지를 설치할 필요는 없다. 현재 구현은 이미 설치된 `httpx`를 사용한다.

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest
python -m uvicorn app.main:app --reload
```

실제 Groq 호출 검증에는 유효한 `GROQ_API_KEY`와 인터넷 연결이 필요하다. 자동 테스트는 외부 호출을 Mock으로 대체하므로 키 없이 실행된다.

## 3. 개발할 때 매 작업마다 생각할 질문

기능을 추가하기 전에 아래 다섯 문장에 답한다.

1. 이 작업은 어떤 확정 요구사항 또는 사용자 문제를 해결하는가?
2. MVP에서 반드시 실제로 동작해야 하는가, 아니면 Mock이어도 되는가?
3. 완료를 어떤 관찰 가능한 결과와 수치로 판정할 것인가?
4. 실패하면 사용자 데이터와 대화 흐름이 어떤 상태로 남는가?
5. 지금 선택은 나중에 쉽게 바꿀 수 있는가? 바꾸기 어렵다면 근거를 기록했는가?

코드를 많이 작성하는 것보다 "가설 → 최소 구현 → 측정 → 결정" 순환을 짧게 만드는 것이 AI 프로젝트에 더 중요하다.

## 4. 지금 추가로 결정하고 기록해야 할 내용

### 4.1 MVP 제품 범위

- 9월 2일 시연에서 반드시 성공해야 하는 하나의 사용자 흐름
- 텍스트 입력을 대체 경로로 제공할지 여부
- 로그인·회원가입·캐릭터 생성 중 무엇을 Mock으로 고정할지
- 성공 기준: 예를 들어 모바일에서 한 세션 동안 사용자 3회 발화와 캐릭터 2명 응답이 중단 없이 완료되는지

### 4.2 캐릭터 정의

- `character_b`의 이름·성격·관계·말투·금지 행동은 현재 임시값이다.
- 두 캐릭터가 같은 답을 반복하지 않도록 역할 차이를 정의해야 한다.
- Typecast의 실제 voice ID와 감정별 음성 표현을 캐릭터별로 확정해야 한다.

### 4.3 LLM 모델 선정

모델은 인상으로 확정하지 말고 같은 평가 입력으로 비교한다.

- 후보: `llama-3.1-8b-instant`, `llama-3.3-70b-versatile`
- 평가 지표: ScenePlan 유효률, 한국어 공감 품질, 캐릭터 구분, p50/p95 지연시간, 한 턴 비용
- 평가 데이터: 정상 대화, 짧은 입력, 모호한 감정, 민감한 고민, 두 캐릭터 충돌 상황을 포함한 최소 20개 고정 문장
- Prompt에는 버전을 부여하고 모델·Prompt·결과·측정값을 함께 저장한다.

### 4.4 STT/TTS 범위

- 현재 LLM만 Groq로 바뀌었으며 STT는 여전히 OpenAI다.
- OpenAI를 프로젝트에서 완전히 제외하려면 Groq Whisper 등으로 STT도 별도 전환해야 한다.
- 녹음 최대 길이, 무음·잡음·재시도 정책, TTS 중단 버튼의 목표 중단시간을 정해야 한다.
- Typecast 실호출과 모바일 오디오 재생은 아직 실제 환경 검증이 필요하다.

### 4.5 데이터와 실패 복구

- 실제 `DATABASE_URL`로 PostgreSQL 통합 테스트를 아직 통과시키지 못했다.
- 현재 개발용 고정 사용자는 배포용 인증 방식이 아니다. MVP 배포 범위를 로컬/비공개 데모로 제한해야 한다.
- LLM 호출 실패 전 사용자 메시지는 저장된다. 재시도 시 중복 AI 응답을 막을 idempotency 또는 Job 상태 정책이 필요하다.
- 대화·음성·고민 데이터의 보관 기간, 삭제, 로그 마스킹, 연구 활용 동의 범위를 정해야 한다.

### 4.6 현재 구현되지 않은 영역

- Job/Redis 기반 서버 비동기 처리
- Memory 추출·검색·삭제 정책
- Scenario 진행 상태
- WebSocket/SSE Realtime
- 운영 인증과 권한 관리

이 항목들을 한꺼번에 구현하지 않는다. 먼저 `실제 Groq 1회 호출 → DB 저장 → TTS 재생`의 단일 수직 흐름을 완성한 뒤, 측정 결과로 필요한 항목만 추가한다.

## 5. 다음 작업 우선순위

1. Groq API Key 설정 후 실제 Scene Director 호출 1회 검증
2. 실제 `DATABASE_URL` 설정 후 PostgreSQL 통합 테스트 통과
3. 한 Message 요청이 Groq 응답 저장까지 완료되는지 검증
4. 저장된 각 AI turn을 Typecast TTS로 재생하는 프론트 연결
5. 20문장 평가셋으로 Llama 8B/70B 비교 후 모델 확정

## 6. 현재 검증 결과

- 자동 테스트: 27 passed, 1 skipped
- skipped: 실제 PostgreSQL 연결이 필요한 선택적 통합 테스트
- 외부 Groq 실호출: API Key가 없어 미검증
- 외부 OpenAI STT/Typecast TTS 실호출: 이 테스트 범위에서는 미검증
