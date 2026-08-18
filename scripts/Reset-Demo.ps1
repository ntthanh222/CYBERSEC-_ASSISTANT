[CmdletBinding()]
param(
    [switch]$DryRun
)

# Not "Stop": see Seed-Demo.ps1 / Run-Acceptance-Tests.ps1 for why.
$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$argsList = @("-m", "backend.scripts.reset_demo")
if ($DryRun) { $argsList += "--dry-run" }

docker compose exec -T backend python @argsList
exit $LASTEXITCODE
