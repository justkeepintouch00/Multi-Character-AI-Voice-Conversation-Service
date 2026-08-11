# Groq GPT-OSS 120B 모델 결정

> 확정: 2026-08-11 13:45 KST  
> 이전 `20260811_1335_GROQ_MIGRATION_AND_PROJECT_DECISIONS.md`의 기본 Llama 모델 결정을 대체한다.

## 확정 구성

- API 공급자: GroqCloud
- API Key 발급·요금·속도·장애 대응 주체: Groq
- 모델: OpenAI가 공개한 오픈 웨이트 모델 `gpt-oss-120b`
- Groq API model ID: `openai/gpt-oss-120b`
- ScenePlan 출력: Groq Strict Structured Outputs 적용
- STT: 현재 OpenAI 유지
- TTS: 현재 Typecast 유지

Groq는 모델 브랜드가 아니라 여러 모델을 실행해 API로 제공하는 추론 서비스 브랜드다. `gpt-oss-120b`는 OpenAI가 만든 모델이지만, 이 프로젝트의 LLM 요청은 OpenAI API가 아니라 Groq API로 전송된다.

## 환경변수

```dotenv
GROQ_API_KEY=실제_Groq_API_KEY
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_SCENE_MODEL=openai/gpt-oss-120b
GROQ_SCENE_MAX_ATTEMPTS=2
```

## 데이터 흐름

```text
FastAPI
  → GroqCloud API
  → Groq가 호스팅한 OpenAI gpt-oss-120b 추론
  → Strict JSON ScenePlan 반환
  → FastAPI Pydantic 재검증
  → PostgreSQL 저장
```

## 아직 검증하지 못한 부분

- 로컬 `.env`에 `GROQ_API_KEY`가 없어 실제 Groq 호출은 아직 미검증이다.
- `DATABASE_URL`이 없어 실제 PostgreSQL을 포함한 전체 대화 흐름은 아직 미검증이다.
