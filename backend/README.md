# 실행 명령어

## Gemma 추론 켜기

$env:Path = "C:\Program Files\llama;$env:Path"
llama serve -hf "bartowski/google_gemma-4-E2B-it-GGUF:Q4_K_M" --host 127.0.0.1 --port 8080 --jinja --chat-template-kwargs '{"enable_thinking":true}'

## Gemma 추론 끄기

$env:Path = "C:\Program Files\llama;$env:Path"
llama serve -hf "bartowski/google_gemma-4-E2B-it-GGUF:Q4_K_M" --host 127.0.0.1 --port 8080 --jinja --chat-template-kwargs '{"enable_thinking":false}'

## 평가 백엔드 8001

cd "C:\Users\only\OneDrive\문서\ChatGPT\멋사 갠플\Multi-Character-AI-Voice-Conversation-Service"
.\backend\.venv\Scripts\Activate.ps1
.\backend\scripts\20260824_1740_start_evaluation_backend.ps1

## 프론트 5174

cd "C:\Users\only\OneDrive\문서\ChatGPT\멋사 갠플\Multi-Character-AI-Voice-Conversation-Service\frontend"
$env:VITE_API_BASE_URL = "http://127.0.0.1:8001"
npm install
npm run dev -- --port 5174
