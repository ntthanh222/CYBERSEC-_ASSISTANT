[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

Write-Host "Stopping the Phase 1 stack (containers only, volumes preserved)..." -ForegroundColor Cyan
docker compose stop
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] docker compose stop failed." -ForegroundColor Red
    exit 1
}

Write-Host "[PASS] Stack stopped. Named volumes were not removed." -ForegroundColor Green
exit 0
