param(
    [string]$GemmaBaseUrl = "http://127.0.0.1:8080/v1",
    [string]$GemmaModel = ""
)

$ErrorActionPreference = "Stop"
$backend = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $backend ".env"
$line = Get-Content -LiteralPath $envFile | Where-Object { $_ -match "^DATABASE_URL=" } | Select-Object -First 1
if (-not $line) { throw "backend/.env에 DATABASE_URL이 없습니다." }

$mainUrl = $line.Substring("DATABASE_URL=".Length).Trim()
$driverUrl = $mainUrl -replace "^postgresql\+psycopg://", "postgresql://"
$builder = [System.UriBuilder]::new($driverUrl)
$builder.Path = "/character_companion_eval"
$env:DATABASE_URL = $builder.Uri.AbsoluteUri.TrimEnd("/") -replace "^postgresql://", "postgresql+psycopg://"
$env:DEV_USER_EXTERNAL_ID = "local-evaluation-user"
$env:DEV_USER_DISPLAY_NAME = "평가 사용자"
$env:CORS_ORIGINS = "http://localhost:5174,http://127.0.0.1:5174"
$env:OBSERVABILITY_LOG_FILE = "logs/evaluation-backend.jsonl"

# The evaluation server must not consume Groq Scene Director tokens.
# Confirm the local OpenAI-compatible server before Uvicorn starts.
$GemmaBaseUrl = $GemmaBaseUrl.TrimEnd("/")
try {
    $availableModels = Invoke-RestMethod -Method Get -Uri "$GemmaBaseUrl/models" -TimeoutSec 5
} catch {
    throw "Gemma 로컬 서버에 연결할 수 없습니다: $GemmaBaseUrl. Gemma 4 E2B 모델을 llama.cpp로 먼저 실행한 뒤 다시 시도하세요."
}

$modelIds = @(
    $availableModels.data |
        ForEach-Object { [string]$_.id } |
        Where-Object { $_ }
)
if ($GemmaModel) {
    if ($modelIds -notcontains $GemmaModel) {
        throw "요청한 Gemma 모델 '$GemmaModel'을 서버에서 찾지 못했습니다. 현재 모델: $($modelIds -join ', ')"
    }
    $selectedModel = $GemmaModel
} else {
    $selectedModel = $modelIds |
        Where-Object { $_ -match "(?i)(gemma.*e2b|e2b.*gemma)" } |
        Select-Object -First 1
    if (-not $selectedModel) {
        throw "Gemma 4 E2B 모델을 찾지 못했습니다. 현재 모델: $($modelIds -join ', ')"
    }
}

$env:SCENE_DIRECTOR_PROVIDER = "gemma4_e2b"
$env:GEMMA_BASE_URL = $GemmaBaseUrl
$env:GEMMA_SCENE_MODEL = $selectedModel
$env:GEMMA_SCENE_MAX_ATTEMPTS = "2"
$env:GEMMA_SCENE_TIMEOUT_SECONDS = "180"

Write-Host "평가 DB: character_companion_eval"
Write-Host "Scene Director: $env:SCENE_DIRECTOR_PROVIDER / $env:GEMMA_SCENE_MODEL"
Write-Host "Gemma 서버: $env:GEMMA_BASE_URL"

Set-Location $backend
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
