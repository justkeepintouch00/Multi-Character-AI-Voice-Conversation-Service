# 2026-08-11 개발 작업 정리

> 작성 시각: 2026-08-11 17:28 KST
>
> 기준 브랜치: `feat/voice-conservation-poc`
>
> 대상: 2026-09-02 MVP의 대화·AI 음성 수직 경로

## 1. 집계 범위

이 문서는 2026-08-11에 구현하거나 검증한 작업만 기록한다.

다음 항목은 이전 작업이므로 오늘 작업에 포함하지 않는다.

- FastAPI 기본 백엔드 구조
- PostgreSQL 연결 설정
- SQLAlchemy 모델과 Alembic 초기 마이그레이션
- `GET /health`
- `GET /health/db`

## 2. 오늘 구현한 Conversation·Message API

| Method | Path | 설명 |
|---|---|---|
| `POST` | `/api/v1/conversations` | TALK 대화 생성 |
| `GET` | `/api/v1/conversations/{conversation_id}` | 개발 사용자 소유 대화 조회 |
| `POST` | `/api/v1/conversations/{conversation_id}/complete` | 대화 완료 |
| `POST` | `/api/v1/conversations/{conversation_id}/messages` | 사용자 메시지 저장, Scene Director 호출, AI 메시지 저장 |
| `GET` | `/api/v1/conversations/{conversation_id}/messages` | 메시지 목록 조회 |

로그인·회원가입 대신 개발용 고정 사용자를 사용한다. 사용자 메시지를 먼저
저장한 뒤 최근 대화 기록을 조회하고 Scene Director를 호출하며, 반환된 AI
메시지를 PostgreSQL에 저장한다.

## 3. 오늘 구현한 AI 음성 API

| Method | Path | 설명 |
|---|---|---|
| `POST` | `/api/v1/stt/transcriptions` | MP3, M4A, WebM 등의 음성을 텍스트로 변환 |
| `POST` | `/api/v1/scene-plans` | 발화할 캐릭터, 감정, 대사와 순서 결정 |
| `POST` | `/api/v1/tts/stream` | 캐릭터 대사를 Typecast 음성으로 생성 |
| `POST` | `/api/v1/audio/convert/mp3` | 브라우저 녹음을 실제 MP3로 변환 |
| `GET` | `/health/providers` | Groq·Typecast 설정 여부 확인 |

기존 `GET /health`, `GET /health/db`와 달리 `GET /health/providers`는 오늘
추가한 외부 AI 공급자 설정 진단 API다.

## 4. Groq·Typecast 공급자 연동

- Scene Director를 Groq GPT-OSS 120B 기준으로 구성했다.
- STT를 Groq Whisper Large V3 Turbo로 구성했다.
- Whisper 응답을 `verbose_json`으로 받아 세그먼트, `no_speech_prob`,
  `avg_logprob`를 확인할 수 있게 했다.
- Scene Director가 모든 캐릭터를 강제로 발화시키지 않고 필요한 캐릭터만
  선택할 수 있도록 지침을 조정했다.
- 캐릭터 대사를 Typecast TTS로 생성하고 순서대로 자동 재생하도록 했다.

## 5. 음성 파이프라인 테스트 화면

개발용 테스트 화면:

```text
backend/devtools/20260811_1434_voice_pipeline_test.html
```

검증 경로:

```text
마이크 또는 MP3/M4A 파일
→ Groq Whisper STT
→ Scene Director
→ Groq GPT-OSS 120B
→ Typecast TTS
→ 자동 음성 재생
```

테스트 화면에서 다음 정보를 확인할 수 있다.

- Groq·Typecast 설정 상태
- 실제 STT 인식 문장
- Whisper `verbose_json` 세그먼트
- ScenePlan JSON
- 캐릭터별 LLM 응답
- Typecast 음성 자동 재생
- 현재 마이크 이름과 음량 진단 정보

## 6. 음성 파일과 마이크 감지 개선

- 브라우저 WebM 녹음을 FFmpeg로 실제 MP3로 변환한다.
- MP3와 M4A 업로드 테스트를 지원한다.
- 업로드 파일은 마이크 VAD를 거치지 않고 STT로 직접 전달한다.
- 무음 입력은 Groq STT에 전달하지 않도록 VAD를 적용했다.
- 작은 목소리를 잃던 `Uint8Array` 측정을 `Float32Array`로 변경했다.
- 최소 RMS 기준을 `0.0008`, 최소 감지 시간을 `100ms`로 조정했다.
- 브라우저에 자동 게인, 노이즈 억제, 에코 제거를 요청한다.
- 현재 RMS, 감지 기준 RMS, 최고 RMS를 화면에 표시한다.

업로드한 녹음 파일의 STT→LLM→TTS 경로는 정상 동작을 확인했다. 수정된
마이크 직접 입력 경로는 실제 사용자 환경에서 재검증이 필요하다.

## 7. 프론트엔드 작업

- Vite + React + TypeScript 프론트엔드 환경을 구성했다.
- 캐릭터 시나리오 웹 프로토타입을 추가했다.
- 시나리오 흐름과 A1 화면을 개선했다.

프론트엔드 UI 작업은 음성 API 수직 경로와 분리해서 진행한다.

## 8. 검증 결과

- 백엔드 자동 테스트: `33 passed, 1 skipped`
- 음성 테스트 화면 JavaScript 문법 검사 통과
- 실제 MP3 변환 결과의 ID3 헤더 확인
- MP3·M4A 업로드 경로 확인
- 업로드 녹음본의 STT→LLM→TTS 동작 확인

## 9. 오늘 구현하지 않은 범위

- 로그인·회원가입
- 캐릭터 생성·수정 API
- Memory API
- Scenario API
- Job·Worker와 Redis
- WebSocket 실시간 음성
- 버튼 없는 연속 대화
- 캐릭터 모션
- 실제 모바일 화면과의 최종 연동

## 10. 다음 작업

1. 개선된 마이크 감지 경로를 실제 환경에서 재검증한다.
2. 브라우저가 선택한 마이크와 Discord에서 사용하는 마이크를 비교한다.
3. 현재 RMS와 감지 기준 RMS를 근거로 VAD 기준을 조정한다.
4. 버튼 기반 녹음을 자동 발화 감지 방식으로 확장한다.
5. Scene Director의 답변 품질을 평가하고 프롬프트를 개선한다.
6. 프론트엔드 UI와 Conversation·STT·TTS API를 연결한다.
