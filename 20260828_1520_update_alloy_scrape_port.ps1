$ErrorActionPreference = 'Stop'

$configPath = 'C:\Program Files\GrafanaLabs\Alloy\config.alloy'
$serviceName = 'Alloy'
$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupPath = "$configPath.$timestamp.bak"

if (-not (Test-Path -LiteralPath $configPath)) {
    throw "Alloy 설정 파일을 찾을 수 없습니다: $configPath"
}

Copy-Item -LiteralPath $configPath -Destination $backupPath -Force
$content = [System.IO.File]::ReadAllText($configPath)
$updated = [System.Text.RegularExpressions.Regex]::Replace(
    $content,
    '127\.0\.0\.1:8000',
    '127.0.0.1:8001'
)

if ($updated -eq $content) {
    Write-Output '변경할 127.0.0.1:8000 대상이 없습니다. 실제 설정의 scrape 대상 포트를 확인하세요.'
    Write-Output "백업 파일: $backupPath"
    exit 2
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($configPath, $updated, $utf8NoBom)

try {
    Restart-Service -Name $serviceName -Force
    Start-Sleep -Seconds 3
    $service = Get-Service -Name $serviceName
    if ($service.Status -ne 'Running') {
        throw "Alloy 서비스가 재시작 후 실행 중이 아닙니다. 현재 상태: $($service.Status)"
    }
    Write-Output 'Alloy scrape 대상 포트를 8001로 변경하고 서비스를 재시작했습니다.'
    Write-Output "설정 파일: $configPath"
    Write-Output "백업 파일: $backupPath"
}
catch {
    Copy-Item -LiteralPath $backupPath -Destination $configPath -Force
    try { Restart-Service -Name $serviceName -Force } catch {}
    throw
}
