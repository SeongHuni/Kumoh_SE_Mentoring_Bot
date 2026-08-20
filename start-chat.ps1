# 대화형 챗봇 실행 런처.
#
#   .\start-chat.ps1              대화형 모드
#   .\start-chat.ps1 -Debug       검색 계획기 판단 근거까지 출력
#
# Chroma 서버가 꺼져 있으면 자동으로 띄우고, 준비될 때까지 기다린 뒤 챗봇을 실행한다.
# (Docker 없이 Python chromadb로 띄운다)
param(
    [switch]$Debug,
    [int]$K = 5
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
chcp 65001 > $null
$Host.UI.RawUI.WindowTitle = "SE 챗봇"

$Url = "http://localhost:8000"

function Test-Chroma {
    try {
        $r = Invoke-WebRequest -Uri "$Url/api/v2/heartbeat" -TimeoutSec 2 -UseBasicParsing
        return $r.StatusCode -eq 200
    } catch { return $false }
}

Write-Host ""
Write-Host "  소프트웨어전공 안내 챗봇" -ForegroundColor White
Write-Host "  ────────────────────────" -ForegroundColor DarkGray

# 1) Chroma 확인 / 기동
if (Test-Chroma) {
    Write-Host "  Chroma 서버: 이미 실행 중" -ForegroundColor DarkGray
} else {
    Write-Host "  Chroma 서버를 시작합니다..." -ForegroundColor DarkGray

    if (-not (Test-Path "chroma-data\chroma.sqlite3")) {
        Write-Host "  [오류] chroma-data 가 없습니다. 먼저 데이터를 적재하세요:" -ForegroundColor Red
        Write-Host "         npm run load" -ForegroundColor Red
        Read-Host "`n  엔터를 누르면 종료합니다"
        exit 1
    }

    # 창을 띄우지 않고 뒤에서 돌린다. 로그는 파일로 남긴다.
    $log = Join-Path $PSScriptRoot "chroma-server.log"
    Start-Process -FilePath "chroma" `
        -ArgumentList "run", "--path", "./chroma-data", "--port", "8000" `
        -WorkingDirectory $PSScriptRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $log `
        -RedirectStandardError "$log.err"

    $ready = $false
    foreach ($i in 1..40) {
        Start-Sleep -Milliseconds 500
        if (Test-Chroma) { $ready = $true; break }
    }

    if (-not $ready) {
        Write-Host "  [오류] Chroma 서버가 20초 안에 뜨지 않았습니다." -ForegroundColor Red
        Write-Host "         로그: $log" -ForegroundColor Red
        Read-Host "`n  엔터를 누르면 종료합니다"
        exit 1
    }
    Write-Host "  Chroma 서버: 준비 완료" -ForegroundColor DarkGray
}

# 2) 챗봇 실행
$nodeArgs = @("scripts/chat.js", "--k", "$K")
if ($Debug) { $nodeArgs += "--debug" }

Write-Host ""
node @nodeArgs

Write-Host ""
Write-Host "  Chroma 서버는 계속 실행 중입니다. 완전히 끄려면:" -ForegroundColor DarkGray
Write-Host "  Get-Process chroma | Stop-Process" -ForegroundColor DarkGray
Write-Host ""
