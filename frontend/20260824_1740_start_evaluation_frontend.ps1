$ErrorActionPreference = "Stop"
$frontend = $PSScriptRoot
$env:VITE_API_BASE_URL = "http://127.0.0.1:8001"
Set-Location $frontend
npm run dev -- --host 127.0.0.1 --port 5174