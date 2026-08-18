[CmdletBinding()]
param(
    [switch]$DryRun
)

# Not "Stop": the container's own INFO logging on stderr would otherwise be
# converted into a terminating PowerShell error even on a fully successful
# run. This script already gates on $LASTEXITCODE below. See
# Run-Acceptance-Tests.ps1 for the same fix and full explanation.
$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$argsList = @("-m", "backend.scripts.seed_demo")
if ($DryRun) { $argsList += "--dry-run" }

docker compose exec -T backend python @argsList
exit $LASTEXITCODE
