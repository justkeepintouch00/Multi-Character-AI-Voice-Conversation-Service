# Backend

FastAPI API, PostgreSQL, Groq STT·LLM, Typecast TTS를 담당한다.

## 최초 설치

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

`backend/.env`에 다음 값을 설정한다.

```dotenv
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/character_companion
GROQ_API_KEY=YOUR_KEY
GROQ_SCENE_MODEL=openai/gpt-oss-120b
GROQ_TRANSCRIPTION_MODEL=whisper-large-v3-turbo
TYPECAST_API_KEY=YOUR_KEY
TYPECAST_VOICE_MAP={"character_a":"VOICE_ID","character_b":"VOICE_ID"}
```

## DB 반영

```powershell
python -m alembic -c alembic.ini upgrade head
```

## 서버 실행

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

- 상태: <http://127.0.0.1:8000/health>
- DB: <http://127.0.0.1:8000/health/db>
- 공급자: <http://127.0.0.1:8000/health/providers>
- API 문서: <http://127.0.0.1:8000/docs>

## 테스트

```powershell
python -m pytest
```

## 폴더 역할

```text
backend/
├─ app/
│  ├─ api/            FastAPI 라우터·의존성·오류 응답
│  ├─ db/             SQLAlchemy 모델·DB 세션
│  ├─ domain/         캐릭터 등 도메인 정의
│  ├─ providers/      Groq·Typecast API 연결
│  ├─ repositories/   PostgreSQL 조회·저장
│  ├─ schemas/        Pydantic 요청·응답 형식
│  ├─ services/       대화 처리 규칙
│  ├─ config.py       .env 설정 읽기
│  └─ main.py         FastAPI 시작점
├─ alembic/           DB migration
├─ devtools/          개발용 HTML 테스트 화면
├─ docs/              백엔드 설계 기록
├─ scripts/           수동 점검 스크립트
├─ tests/             pytest
└─ pyproject.toml     Python 패키지·의존성
```

서버 종료: `Ctrl+C`
