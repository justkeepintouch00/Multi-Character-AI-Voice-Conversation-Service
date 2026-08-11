# AI 음성 핵심 API 구현 기록

> 작성 시각: 2026-08-11 11:23 KST  
> 구현 브랜치: `feat/voice-conversation-poc`  
> 범위: Scene Director, 파일 STT, 스트리밍 TTS

## 1. 구현 범위

이번 구현은 UI와 인증을 제외한 AI 음성 수직 경로만 제공한다.

```text
프론트엔드
→ POST /api/v1/stt/transcriptions
→ POST /api/v1/scene-plans
→ POST /api/v1/tts/stream
→ 오디오 재생
```

구현하지 않은 항목:

- 로그인·회원가입
- 캐릭터 생성·수정 API
- 대화·메시지 DB 저장
- Redis/Worker
- WebSocket 실시간 STT
- 장기 기억

## 2. API

### `POST /api/v1/stt/transcriptions`

- `multipart/form-data`
- `file`: 20MB 이하 음성 파일
- `language`: 기본값 `ko`
- OpenAI Audio Transcriptions API Adapter 사용

응답:

```json
{"text":"오늘 조금 힘들었어.","language":"ko"}
```

### `POST /api/v1/scene-plans`

요청:

```json
{
  "user_text": "오늘 조금 힘들었어.",
  "character_ids": ["character_a", "character_b"],
  "recent_messages": []
}
```

서버 검증:

- 활성 캐릭터 1~2명
- 캐릭터 ID 중복 금지
- 보이는 AI 발화 1~2회
- 요청에 포함된 캐릭터만 발화
- `return_turn_to = USER`
- `max_internal_turns <= 2`

현재 `character_a`는 루미 기획을 반영한다. `character_b`의 상세 설정은 확정되지
않았으므로 개발용 플레이스홀더다. 캐릭터 설정이 확정되면 서버 관리 catalog로
교체해야 한다.

### `POST /api/v1/tts/stream`

요청:

```json
{
  "speaker_id": "character_a",
  "text": "천천히 이야기해도 괜찮아.",
  "emotion": "concern",
  "emotion_intensity": 1.0,
  "audio_format": "mp3"
}
```

서버가 `TYPECAST_VOICE_MAP`에서 `speaker_id`에 대응하는 Typecast `voice_id`를
찾는다. 프론트엔드는 실제 공급자 voice ID와 API key를 알 필요가 없다.

## 3. 환경변수

실제 `.env`에 다음 값을 추가한다. 실제 키를 저장소에 커밋하지 않는다.

```dotenv
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
OPENAI_API_KEY=실제_OpenAI_API_KEY
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_SCENE_MODEL=gpt-5.6-terra
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-transcribe
TYPECAST_API_KEY=실제_Typecast_API_KEY
TYPECAST_BASE_URL=https://api.typecast.ai
TYPECAST_TTS_MODEL=ssfm-v30
TYPECAST_VOICE_MAP={"character_a":"tc_실제ID","character_b":"tc_실제ID"}
```

계정별 모델 접근 권한과 Typecast voice ID는 코드만으로 확인할 수 없다.

## 4. 실행과 자동 테스트

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
python -m uvicorn app.main:app --reload
```

Swagger 수동 테스트는 이번 범위에 포함하지 않는다. 테스트는 FastAPI dependency
override와 HTTP mock transport를 사용하므로 외부 API 비용을 발생시키지 않는다.

## 5. 현재 한계

- STT는 녹음 종료 후 파일을 업로드하는 방식이다.
- 업로드 파일을 최대 20MB까지 메모리에 읽으므로 장시간 녹음에는 적합하지 않다.
- `character_b`는 개발용 설정이다.
- 실제 공급자 연결 성공 여부는 유효한 API key와 계정 권한으로 별도 확인해야 한다.
- 대화 기록은 DB에 저장하지 않는다.
