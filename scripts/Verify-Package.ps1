[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$Required = @(
    "START_HERE.md",
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "START_PHASE_1_PROMPT.md",
    ".ai\PROJECT_CONTEXT.md",
    ".ai\MASTER_PLAN.md",
    ".ai\TASKS.md",
    "docs\00_PROJECT_REQUIREMENTS.md",
    "docs\01_OLD_PROJECT_ANALYSIS.md",
    "docs\13_OLD_TO_NEW_MAPPING.md",
    "reference\CYBERSEC_ASSISTANT_REBUILD_BLUEPRINT.md",
    "reference\OLD_PROJECT_REPOMIX.md",
    "reference\SOURCE_MANIFEST.json"
)

$Failures = 0
Write-Host "PROJECT_ROOT: $ProjectRoot" -ForegroundColor Cyan

foreach ($Relative in $Required) {
    $Path = Join-Path $ProjectRoot $Relative
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        Write-Host "[PASS] $Relative" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] Missing: $Relative" -ForegroundColor Red
        $Failures++
    }
}

$Forbidden = @(
    "D:\AI\Workspace\Projects\CyberSec-Assistant-Rebuild"
)

foreach ($Path in $Forbidden) {
    if ($ProjectRoot -eq $Path) {
        Write-Host "[INFO] This path is only valid if explicitly chosen by the user." -ForegroundColor Yellow
    }
}

if ($Failures -eq 0) {
    Write-Host "PACKAGE VERIFIED" -ForegroundColor Green
    exit 0
}

Write-Host "PACKAGE INVALID: $Failures failure(s)" -ForegroundColor Red
exit 1
