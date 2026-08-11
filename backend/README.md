# Character Companion Backend

캐릭터 기반 멀티 AI 음성 동반자 서비스의 FastAPI 백엔드다.

현재 구현 범위:

- PostgreSQL용 SQLAlchemy 모델 27개
- Alembic 초기 마이그레이션
- FastAPI 실행 골격과 자동 OpenAPI 문서
- `GET /health`: FastAPI 프로세스 상태 확인
- `GET /health/db`: PostgreSQL 연결 상태 확인

기능 API 계약은 `docs/20260810_1714_API_DESIGN.md`에 있다. 캐릭터·대화·메시지 기능 API의 실제 처리 로직은 아직 구현 전이다.

## SQLAlchemy와 Alembic의 역할

### SQLAlchemy 모델

`app/db/models.py`는 애플리케이션이 현재 사용하는 데이터 구조다.

앞으로 Python 코드에서 `User`, `Conversation`, `Message` 객체를 만들고 조회할 때 사용한다. 모델은 테이블, 컬럼, FK, UNIQUE, CHECK 제약을 Python으로 표현한다.

### Alembic migration

`alembic/versions/20260810_0001_initial_schema.py`는 실제 PostgreSQL을 변경하는 순서가 기록된 이력이다.

```text
빈 PostgreSQL
    → alembic upgrade head
27개 애플리케이션 테이블 생성
```

모델을 수정한 것만으로 이미 존재하는 운영 DB가 자동 변경되지는 않는다. 모델 변경 후에는 migration을 만들어야 한다.

```text
SQLAlchemy 모델 변경
    → alembic revision --autogenerate
새 migration 검토
    → alembic upgrade head
PostgreSQL 반영
```

Alembic 자동 생성은 모델 메타데이터와 현재 DB 상태를 비교해 초안을 만드는 기능이다. 생성된 migration은 반드시 사람이 검토한다.

## 설치

```powershell
cd backend
python -m pip install -e ".[dev]"
```

## PostgreSQL 연결 설정

예제 파일을 실제 설정 파일로 복사한다.

```powershell
Copy-Item .env.example .env
```

`.env`를 열고 `YOUR_POSTGRES_PASSWORD`를 PostgreSQL 설치 시 정한 실제 비밀번호로 바꾼다.

```dotenv
DATABASE_URL=postgresql+psycopg://postgres:YOUR_POSTGRES_PASSWORD@localhost:5432/character_companion
```

루트 `.gitignore`가 `.env`를 제외하므로 실제 비밀번호 파일은 커밋하지 않는다. 비밀번호에 `@`, `:`, `/`, `#` 같은 문자가 있으면 URL 인코딩이 필요하다.

## migration 적용

```powershell
python -m alembic -c alembic.ini upgrade head
```

현재 버전 확인:

```powershell
python -m alembic -c alembic.ini current
```

한 단계 되돌리기:

```powershell
python -m alembic -c alembic.ini downgrade -1
```

모델 변경 후 migration 초안 만들기:

```powershell
python -m alembic -c alembic.ini revision --autogenerate -m "describe change"
```

## FastAPI 서버 실행

`backend` 폴더에서 실행한다.

```powershell
python -m uvicorn app.main:app --reload
```

터미널에 다음 주소가 보이면 실행 중이다.

```text
Uvicorn running on http://127.0.0.1:8000
```

- 서버 상태: <http://127.0.0.1:8000/health>
- PostgreSQL 상태: <http://127.0.0.1:8000/health/db>
- Swagger UI: <http://127.0.0.1:8000/docs>
- ReDoc: <http://127.0.0.1:8000/redoc>

서버 종료는 실행 중인 터미널에서 `Ctrl+C`를 누른다.

## 테스트

```powershell
python -m pytest
```

## 현재 구현 범위

- 사용자·에셋·캐릭터·프로필·관계·적응 상태
- 대화·참여자·메시지·TTS 세그먼트
- Scene Director 계획과 최대 처리 제약
- 서버 비동기 Job·Checkpoint
- Scoped Memory와 know/read/disclose-to ACL
- A/B/C 시나리오·장면·턴·결말·실행·평가

`memory_items.embedding`은 공급자와 차원이 미확정이므로 현재 JSONB다. 공급자 결정 후 별도 migration으로 pgvector 타입과 인덱스를 추가한다.
