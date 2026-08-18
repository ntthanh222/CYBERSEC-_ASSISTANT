param(
    [ValidateSet("Readiness", "Required")]
    [string]$Mode = "Readiness"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir

function Run-Gate {
    param(
        [string]$Name,
        [scriptblock]$Command,
        [bool]$Required = $true
    )
    Write-Host ("== {0} ==" -f $Name)
    $global:LASTEXITCODE = 0
    & $Command
    if (-not $?) {
        $code = 1
    } else {
        $code = $LASTEXITCODE
    }
    if ($code -ne 0 -and $Required) {
        Write-Host ("[FAIL] {0} exited {1}" -f $Name, $code)
        exit $code
    }
    if ($code -ne 0) {
        Write-Host ("[NOT READY] {0} exited {1}" -f $Name, $code)
    } else {
        Write-Host ("[PASS] {0}" -f $Name)
    }
}

Set-Location $Root

Run-Gate "PowerShell syntax: branch readiness" { [scriptblock]::Create((Get-Content -LiteralPath (Join-Path $ScriptDir "Check-Phase2-Branch-Readiness.ps1") -Raw)) > $null }
Run-Gate "PowerShell syntax: contract compare" { [scriptblock]::Create((Get-Content -LiteralPath (Join-Path $ScriptDir "Compare-Phase2-Contracts.ps1") -Raw)) > $null }

Run-Gate "Branch readiness" { & (Join-Path $ScriptDir "Check-Phase2-Branch-Readiness.ps1") } ($Mode -eq "Required")
Run-Gate "Static contract compare" { & (Join-Path $ScriptDir "Compare-Phase2-Contracts.ps1") -Mode $Mode } $true

if (Test-Path -LiteralPath "tests/contracts") {
    $pytestProbe = & python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('pytest') else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Run-Gate "Contract scaffolding tests" { python -m pytest -q tests/contracts tests/integration } $true
    } else {
        Run-Gate "Contract scaffolding tests" {
            python tests\contracts\test_phase2_contract_manifest.py
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            python tests\integration\test_phase2_integration_modes.py
        } $true
    }
}

if ($Mode -eq "Required") {
    Write-Host "Required integration mode selected. Add backend/frontend build, Docker, migration, OpenAPI, API adapter, and browser E2E gates after feature branches are merged."
} else {
    Write-Host "Readiness mode selected. Missing endpoints or unfinished branch readiness are reported without destructive actions."
}

exit 0
