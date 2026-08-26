# 웹 서비스 전체 실행 런처.
#
#   .\start-web.ps1
#
# Chroma(8000) -> API(8787) -> 프론트엔드(3000) 순서로 띄우고,
# 각 단계가 실제로 응답할 때까지 기다린 뒤 다음으로 넘어간다.
param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
chcp 65001 > $null
$Host.UI.RawUI.WindowTitle = "SE 챗봇 - 웹 서비스"

function Test-Endpoint($url) {
    try { return (Invoke-WebRequest -Uri $url -TimeoutSec 2 -UseBasicParsing).StatusCode -eq 200 }
    catch { return $false }
}

function Wait-For($url, $name, $seconds = 40) {
    foreach ($i in 1..($seconds * 2)) {
        Start-Sleep -Milliseconds 500
        if (Test-Endpoint $url) {
            Write-Host "  $name 준비 완료" -ForegroundColor DarkGray
            return $true
        }
    }
    Write-Host "  [오류] $name 이(가) ${seconds}초 안에 응답하지 않았습니다." -ForegroundColor Red
    return $false
}

Write-Host ""
Write-Host "  SE 챗봇 웹 서비스" -ForegroundColor White
Write-Host "  ─────────────────" -ForegroundColor DarkGray

# 1) Chroma
if (Test-Endpoint "http://localhost:8000/api/v2/heartbeat") {
    Write-Host "  Chroma(8000): 이미 실행 중" -ForegroundColor DarkGray
} else {
    if (-not (Test-Path "chroma-data\chroma.sqlite3")) {
        Write-Host "  [오류] chroma-data 가 없습니다. 먼저 'npm run load' 를 실행하세요." -ForegroundColor Red
        Read-Host "`n  엔터를 누르면 종료합니다"; exit 1
    }
    Write-Host "  Chroma(8000) 시작..." -ForegroundColor DarkGray
    Start-Process -FilePath "chroma" `
        -ArgumentList "run", "--path", "./chroma-data", "--port", "8000" `
        -WorkingDirectory $PSScriptRoot -WindowStyle Hidden `
        -RedirectStandardOutput "chroma-server.log" -RedirectStandardError "chroma-server.log.err"
    if (-not (Wait-For "http://localhost:8000/api/v2/heartbeat" "Chroma(8000)")) {
        Read-Host "`n  엔터를 누르면 종료합니다"; exit 1
    }
}

# 2) API
if (Test-Endpoint "http://localhost:8787/api/health") {
    Write-Host "  API(8787): 이미 실행 중" -ForegroundColor DarkGray
} else {
    Write-Host "  API(8787) 시작..." -ForegroundColor DarkGray
    Start-Process -FilePath "python" -ArgumentList "-m","uvicorn","backend.app.main:app","--host","127.0.0.1","--port","8787" `
        -WorkingDirectory $PSScriptRoot -WindowStyle Hidden `
        -RedirectStandardOutput "api-server.log" -RedirectStandardError "api-server.log.err"
    if (-not (Wait-For "http://localhost:8787/api/health" "API(8787)")) {
        Write-Host "  로그: api-server.log.err" -ForegroundColor Red
        Read-Host "`n  엔터를 누르면 종료합니다"; exit 1
    }
}

# 3) 프론트엔드
if (Test-Endpoint "http://localhost:3000") {
    Write-Host "  웹(3000): 이미 실행 중" -ForegroundColor DarkGray
} else {
    if (-not (Test-Path "frontend\node_modules")) {
        Write-Host "  프론트엔드 의존성 설치 중... (처음 한 번만)" -ForegroundColor DarkGray
        npm --prefix frontend install --no-fund --no-audit | Out-Null
    }
    Write-Host "  웹(3000) 시작..." -ForegroundColor DarkGray
    $nextBin = Join-Path $PSScriptRoot "frontend\node_modules\next\dist\bin\next"
    Start-Process -FilePath "node" -ArgumentList "`"$nextBin`"", "dev" `
        -WorkingDirectory (Join-Path $PSScriptRoot "frontend") -WindowStyle Hidden `
        -RedirectStandardOutput "frontend\next-dev.log" -RedirectStandardError "frontend\next-dev.log.err"
    if (-not (Wait-For "http://localhost:3000" "웹(3000)" 60)) {
        Write-Host "  로그: frontend\next-dev.log.err" -ForegroundColor Red
        Read-Host "`n  엔터를 누르면 종료합니다"; exit 1
    }
}

$health = (Invoke-WebRequest "http://localhost:8787/api/health" -UseBasicParsing).Content

Write-Host ""
Write-Host "  준비 완료" -ForegroundColor Green
Write-Host "  $health" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  웹  http://localhost:3000" -ForegroundColor White
Write-Host "  API http://localhost:8787" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  전부 종료하려면:" -ForegroundColor DarkGray
Write-Host "  Get-Process node,chroma | Stop-Process" -ForegroundColor DarkGray
Write-Host ""

if (-not $NoBrowser) { Start-Process "http://localhost:3000" }
