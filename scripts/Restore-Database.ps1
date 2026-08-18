[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile,

    [switch]$Force
)

# Not "Stop": see Seed-Demo.ps1 / Run-Acceptance-Tests.ps1 for why. Every
# docker step below already checks $LASTEXITCODE explicitly.
$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$dbUser = $env:DB_USER; if (-not $dbUser) { $dbUser = "cybersec" }
$dbName = $env:DB_NAME; if (-not $dbName) { $dbName = "cybersec_assistant" }
$verifyDbName = "${dbName}_restore_verify"

if (-not (Test-Path -LiteralPath $BackupFile)) {
    Write-Host "[FAIL] Backup file not found: $BackupFile" -ForegroundColor Red
    exit 1
}

$status = docker compose ps postgres --format json 2>$null
if (-not $status -or $status -notmatch '"Health":"healthy"') {
    Write-Host "[FAIL] postgres service is not healthy - cannot restore." -ForegroundColor Red
    exit 1
}

Write-Host "WARNING: this will DROP and recreate all objects in database '$dbName'." -ForegroundColor Yellow
Write-Host "Source: $BackupFile" -ForegroundColor Yellow

if (-not $Force) {
    $confirmation = Read-Host "Type 'yes' to continue"
    if ($confirmation -ne "yes") {
        Write-Host "Aborted." -ForegroundColor Yellow
        exit 1
    }
}

# Step 1 of 3: back up the CURRENT state before touching anything, so a bad
# restore is always recoverable. Reuses Backup-Database.ps1 rather than
# duplicating its dump logic.
Write-Host ""
Write-Host "[1/3] Safety-backing up current state before restoring ..." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "Backup-Database.ps1") -OutputDir "backups/pre-restore-safety"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] Safety backup failed - aborting restore without touching '$dbName'." -ForegroundColor Red
    exit 1
}

function Remove-VerifyDatabase {
    docker compose exec -T postgres psql -U $dbUser -d postgres -c "DROP DATABASE IF EXISTS ""$verifyDbName"";" 2>$null | Out-Null
    return $LASTEXITCODE -eq 0
}

# Step 2 of 3: restore into a disposable database first and verify it looks
# like real, intact data - never trust a dump just because pg_restore
# exited 0 (a truncated or wrong-schema dump can still "restore" cleanly).
Write-Host ""
Write-Host "[2/3] Restoring into a disposable database ('$verifyDbName') to verify first ..." -ForegroundColor Cyan
Remove-VerifyDatabase | Out-Null
docker compose exec -T postgres psql -U $dbUser -d postgres -c "CREATE DATABASE ""$verifyDbName"" OWNER $dbUser;" | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] Could not create the disposable verification database." -ForegroundColor Red
    exit 1
}

$containerPath = "/tmp/restore_$([System.Guid]::NewGuid().ToString('N')).dump"
docker compose cp $BackupFile "postgres:$containerPath"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] Could not copy backup file into the postgres container." -ForegroundColor Red
    Remove-VerifyDatabase | Out-Null
    exit 1
}

docker compose exec -T postgres pg_restore -U $dbUser -d $verifyDbName --no-owner $containerPath
$verifyRestoreExit = $LASTEXITCODE
if ($verifyRestoreExit -ne 0) {
    Write-Host "[FAIL] pg_restore into the disposable database exited with code $verifyRestoreExit - the dump is suspect. Root database was NOT touched." -ForegroundColor Red
    docker compose exec -T postgres rm -f $containerPath | Out-Null
    Remove-VerifyDatabase | Out-Null
    exit 1
}

$verifySchema = docker compose exec -T postgres psql -U $dbUser -d $verifyDbName -tAc "SELECT to_regclass('public.schema_bootstrap') IS NOT NULL;"
$verifyMigration = docker compose exec -T postgres psql -U $dbUser -d $verifyDbName -tAc "SELECT version_num FROM alembic_version;"
if ($LASTEXITCODE -ne 0 -or $verifySchema.Trim() -ne "t" -or -not $verifyMigration.Trim()) {
    Write-Host "[FAIL] Disposable-database verification failed (schema_bootstrap or alembic_version missing). Root database was NOT touched." -ForegroundColor Red
    docker compose exec -T postgres rm -f $containerPath | Out-Null
    Remove-VerifyDatabase | Out-Null
    exit 1
}
Write-Host "[PASS] Disposable-database verification passed (migration=$($verifyMigration.Trim()))." -ForegroundColor Green

# Gate step 3 on this cleanup actually succeeding - if a routine DROP
# DATABASE fails, that is a real sign something is wrong with the
# Postgres connection/permissions right now, not something to silently
# ignore before touching the real database.
if (-not (Remove-VerifyDatabase)) {
    Write-Host "[FAIL] Could not drop the disposable verification database ('$verifyDbName') after a passing verification - aborting before touching '$dbName'. It may still exist; clean it up manually once Postgres connectivity is confirmed healthy, then re-run." -ForegroundColor Red
    exit 1
}

# Step 3 of 3: only now touch the real database - the dump has already
# proven it restores and verifies cleanly. --single-transaction wraps the
# whole restore (every DROP/CREATE/COPY) in one transaction, so a failure
# partway through rolls back cleanly instead of leaving the real database
# with some objects dropped and never recreated - the disposable-database
# rehearsal above proves the dump itself is good, but this is what
# guarantees a failure THIS time (e.g. a transient connection drop) can't
# still leave live data in an inconsistent state.
Write-Host ""
Write-Host "[3/3] Restoring into '$dbName' ..." -ForegroundColor Cyan
docker compose exec -T postgres pg_restore -U $dbUser -d $dbName --clean --if-exists --no-owner --single-transaction $containerPath
$restoreExit = $LASTEXITCODE

docker compose exec -T postgres rm -f $containerPath | Out-Null

if ($restoreExit -ne 0) {
    Write-Host "[FAIL] pg_restore into '$dbName' exited with code $restoreExit - rolled back cleanly (--single-transaction), '$dbName' is unchanged. A pre-restore safety backup also exists under backups/pre-restore-safety/ if further recovery is needed." -ForegroundColor Red
    exit 1
}

$verify = docker compose exec -T postgres psql -U $dbUser -d $dbName -tAc "SELECT to_regclass('public.schema_bootstrap') IS NOT NULL;"
if ($LASTEXITCODE -ne 0 -or $verify.Trim() -ne "t") {
    Write-Host "[FAIL] Post-restore verification failed (schema_bootstrap not found)." -ForegroundColor Red
    exit 1
}

Write-Host "[PASS] Restore complete and verified." -ForegroundColor Green
exit 0
