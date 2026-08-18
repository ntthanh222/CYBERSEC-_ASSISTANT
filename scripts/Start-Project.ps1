[CmdletBinding()]
param(
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

if (-not (Test-Path -LiteralPath ".env")) {
    Write-Host "[FAIL] .env not found. Copy .env.example to .env before starting." -ForegroundColor Red
    exit 1
}

Write-Host "Building and starting the Phase 1 stack..." -ForegroundColor Cyan
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] docker compose up failed." -ForegroundColor Red
    exit 1
}

$services = @("postgres", "redis", "backend", "frontend")
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)

while ((Get-Date) -lt $deadline) {
    $states = docker compose ps --format json | ForEach-Object { $_ | ConvertFrom-Json }
    $unhealthy = $states | Where-Object {
        $services -contains $_.Service -and $_.Health -and $_.Health -ne "healthy"
    }
    $missing = $services | Where-Object { $_ -notin ($states | Select-Object -ExpandProperty Service) }

    if (-not $unhealthy -and -not $missing) {
        Write-Host "[PASS] All 4 services are healthy." -ForegroundColor Green
        docker compose ps
        exit 0
    }
    Start-Sleep -Seconds 5
}

Write-Host "[FAIL] Services did not become healthy within $TimeoutSeconds seconds." -ForegroundColor Red
docker compose ps
exit 1
