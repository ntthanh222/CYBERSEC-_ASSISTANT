[CmdletBinding()]
param(
    [string]$OutputDir = "backups/local"
)

# Not "Stop": see Seed-Demo.ps1 / Run-Acceptance-Tests.ps1 for why. Every
# docker step below already checks $LASTEXITCODE explicitly.
$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$dbUser = $env:DB_USER; if (-not $dbUser) { $dbUser = "cybersec" }
$dbName = $env:DB_NAME; if (-not $dbName) { $dbName = "cybersec_assistant" }

$status = docker compose ps postgres --format json 2>$null
if (-not $status -or $status -notmatch '"Health":"healthy"') {
    Write-Host "[FAIL] postgres service is not healthy - cannot back up." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path -LiteralPath $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$fileName = "${dbName}_${timestamp}.dump"
$outputPath = Join-Path $OutputDir $fileName

Write-Host "Backing up '$dbName' to $outputPath ..." -ForegroundColor Cyan

# Custom format (-Fc): compressed, restorable with pg_restore, independent
# of client tooling. Password comes from the container's own environment,
# never echoed to this console.
#
# Dump to a file INSIDE the container, then `docker compose cp` it out,
# rather than redirecting `docker compose exec`'s stdout with PowerShell's
# `>` - PowerShell's redirection re-encodes the stream as text (line-ending
# translation, encoding conversion), which silently corrupts pg_dump's
# binary custom-format archive. `docker compose cp` copies bytes verbatim.
$containerPath = "/tmp/backup_$([System.Guid]::NewGuid().ToString('N')).dump"
docker compose exec -T postgres pg_dump -U $dbUser -d $dbName -Fc -f $containerPath

if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] pg_dump exited with code $LASTEXITCODE" -ForegroundColor Red
    docker compose exec -T postgres rm -f $containerPath | Out-Null
    exit 1
}

docker compose cp "postgres:$containerPath" $outputPath
$copyExit = $LASTEXITCODE
docker compose exec -T postgres rm -f $containerPath | Out-Null

if ($copyExit -ne 0) {
    Write-Host "[FAIL] Could not copy the dump out of the postgres container." -ForegroundColor Red
    if (Test-Path -LiteralPath $outputPath) { Remove-Item -LiteralPath $outputPath -Force }
    exit 1
}

$size = (Get-Item -LiteralPath $outputPath).Length
if ($size -eq 0) {
    Write-Host "[FAIL] Backup file is empty." -ForegroundColor Red
    Remove-Item -LiteralPath $outputPath -Force
    exit 1
}

# Metadata sidecar: never a secret (no DSN, no password, no token) - just
# enough to know what a dump actually is later, since "backup.dump" alone
# doesn't say which schema version or app commit produced it.
$migrationRevision = (docker compose exec -T postgres psql -U $dbUser -d $dbName -tAc "SELECT version_num FROM alembic_version;" 2>$null)
if ($migrationRevision) { $migrationRevision = $migrationRevision.Trim() } else { $migrationRevision = "unknown" }

$pgvectorVersion = (docker compose exec -T postgres psql -U $dbUser -d $dbName -tAc "SELECT extversion FROM pg_extension WHERE extname = 'vector';" 2>$null)
if ($pgvectorVersion) { $pgvectorVersion = $pgvectorVersion.Trim() } else { $pgvectorVersion = "not_installed" }

$appCommit = (git -C $ProjectRoot rev-parse HEAD 2>$null)
if (-not $appCommit) { $appCommit = "unknown" }

$metadata = [ordered]@{
    timestamp          = (Get-Date -Format "o")
    database           = $dbName
    migration_revision = $migrationRevision
    pgvector_version   = $pgvectorVersion
    app_commit         = $appCommit.Trim()
    dump_file          = $fileName
    dump_size_bytes    = $size
}
$metadataPath = "$outputPath.meta.json"
$metadata | ConvertTo-Json | Set-Content -LiteralPath $metadataPath -Encoding utf8

Write-Host "[PASS] Backup written: $outputPath ($size bytes)" -ForegroundColor Green
Write-Host "[PASS] Metadata written: $metadataPath (migration=$migrationRevision pgvector=$pgvectorVersion commit=$($appCommit.Trim().Substring(0, [Math]::Min(12, $appCommit.Trim().Length))))" -ForegroundColor Green
exit 0
