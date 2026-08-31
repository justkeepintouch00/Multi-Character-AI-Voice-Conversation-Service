# 실행 명령어

## 0. 백엔드 실행 전 설정

cd "C:\Users\only\OneDrive\문서\ChatGPT\멋사 갠플\Multi-Character-AI-Voice-Conversation-Service\backend"
.\.venv\Scripts\Activate.ps1
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
$env:LANGSMITH_TRACING="true"
$env:LANGSMITH_API_KEY="여기에_LangSmith_API_KEY"
$env:LANGSMITH_PROJECT="character-companion-dev"
alembic upgrade head

## 1. Gemma 추론 켜기

$env:Path = "C:\Program Files\llama;$env:Path"
llama serve -hf "bartowski/google_gemma-4-E2B-it-GGUF:Q4_K_M" --host 127.0.0.1 --port 8080 --jinja --chat-template-kwargs '{"enable_thinking":true}'

## 2. Gemma 추론 끄기

$env:Path = "C:\Program Files\llama;$env:Path"
llama serve -hf "bartowski/google_gemma-4-E2B-it-GGUF:Q4_K_M" --host 127.0.0.1 --port 8080 --jinja --chat-template-kwargs '{"enable_thinking":false}'

## 3. 백엔드 8001

cd "C:\Users\only\OneDrive\문서\ChatGPT\멋사 갠플\Multi-Character-AI-Voice-Conversation-Service"
.\backend\.venv\Scripts\Activate.ps1
.\backend\scripts\20260824_1740_start_evaluation_backend.ps1

## 4. 프론트 5174

cd "C:\Users\only\OneDrive\문서\ChatGPT\멋사 갠플\Multi-Character-AI-Voice-Conversation-Service\frontend"
$env:VITE_API_BASE_URL="http://127.0.0.1:8001"
npm run dev -- --port 5174

## 5. 메모리 정책 선택 (3번 실행 전에 하나만 선택)

$env:MEMORY_POLICY_VERSION="v1"
# 또는
$env:MEMORY_POLICY_VERSION="v2"

## 6. 메모리 구조 평가

cd "C:\Users\only\OneDrive\문서\ChatGPT\멋사 갠플\Multi-Character-AI-Voice-Conversation-Service\backend"
python scripts\20260831_235500_evaluate_memory_structure.py --policy-version v1 --database-url "postgresql+psycopg://postgres:0206@localhost:5432/character_companion_eval" --output evals\runs\20260831_235500_memory_structure_v1.json
python scripts\20260831_235500_evaluate_memory_structure.py --policy-version v2 --database-url "postgresql+psycopg://postgres:0206@localhost:5432/character_companion_eval" --output evals\runs\20260831_235500_memory_structure_v2.json
python scripts\20260831_235500_evaluate_memory_structure.py --compare evals\runs\20260831_235500_memory_structure_v1.json evals\runs\20260831_235500_memory_structure_v2.json --output evals\runs\20260831_235500_memory_structure_comparison.json
