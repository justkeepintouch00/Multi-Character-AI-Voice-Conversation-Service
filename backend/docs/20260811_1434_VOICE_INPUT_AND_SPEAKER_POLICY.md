# 직접 음성 입력과 캐릭터 선택 발화 정책

> 확정·구현: 2026-08-11 14:34 KST  
> 이전 문서의 OpenAI STT 구성과 두 캐릭터 발화 해석을 대체한다.

## 확정 구성

- 마이크 녹음: 브라우저 `MediaRecorder`
- STT 공급자: Groq
- STT 모델: `whisper-large-v3-turbo`
- Scene Director: Groq `openai/gpt-oss-120b`
- TTS: Typecast `ssfm-v30`
- 실제 제품 프론트와 분리된 로컬 마이크 테스트 화면 제공

## 캐릭터 발화 정책

- 기본적으로 가장 적합한 캐릭터 한 명만 답한다.
- 두 번째 캐릭터는 첫 답과 다른 유의미한 관점이나 실제 의견 차이가 있을 때만 답한다.
- 단순 동의, 같은 위로 반복, 말투만 바꾼 반복이면 두 번째 캐릭터는 침묵한다.
- 보이는 발화는 최소 1회, 최대 2회라는 기존 확정 제약은 유지한다.
- 마지막 발화권은 항상 사용자에게 반환한다.

## 환경변수

```dotenv
GROQ_API_KEY=실제_Groq_API_KEY
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_SCENE_MODEL=openai/gpt-oss-120b
GROQ_SCENE_MAX_ATTEMPTS=2
GROQ_TRANSCRIPTION_MODEL=whisper-large-v3-turbo
```

## 로컬 마이크 테스트 화면

파일:

```text
backend/devtools/20260811_1434_voice_pipeline_test.html
```

실행 흐름:

```text
브라우저 마이크 녹음
→ POST /api/v1/stt/transcriptions
→ Groq Whisper 한국어 전사
→ POST /api/v1/scene-plans
→ 발화할 캐릭터 1~2명 선택
→ POST /api/v1/tts/stream
→ Typecast MP3 생성 및 브라우저 재생
```

테스트 화면은 `localhost:5173`에서만 띄우며 API Key는 브라우저에 전달하지 않는다. 모든 외부 공급자 호출은 FastAPI 서버가 수행한다.
