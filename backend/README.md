# Backend

## 설치

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m alembic -c alembic.ini upgrade head
```

## 일반 백엔드 (8000)

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 8000
```

## 평가 실행 (Gemma 4 E2B)

### 터미널 1: Gemma 서버 (8080)

```powershell
$env:Path = "C:\Program Files\llama;$env:Path"
llama serve -hf "bartowski/google_gemma-4-E2B-it-GGUF:Q4_K_M" --host 127.0.0.1 --port 8080
```

### 터미널 2: 평가 백엔드 (8001)

```powershell
cd "C:\Users\only\OneDrive\문서\ChatGPT\멋사 갠플\Multi-Character-AI-Voice-Conversation-Service"
.\backend\.venv\Scripts\Activate.ps1
.\backend\scripts\20260824_1740_start_evaluation_backend.ps1
```

### 상태 확인

```powershell
Invoke-RestMethod "http://127.0.0.1:8080/v1/models"
Invoke-RestMethod "http://127.0.0.1:8001/health"
```

## 테스트

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest -q
```

## 종료

```text
Ctrl+C
```
