[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

if (Test-Path -LiteralPath ".git") {
    Write-Host "Git repository already exists." -ForegroundColor Yellow
} else {
    git init -b main
    if ($LASTEXITCODE -ne 0) { throw "git init failed" }
}

git add .
git commit -m "chore(project): add AI rebuild handoff package"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Commit may already exist or Git identity is not configured." -ForegroundColor Yellow
}

$Branches = @("feature/phase-1", "feature/phase-2", "feature/ui")
foreach ($Branch in $Branches) {
    git show-ref --verify --quiet "refs/heads/$Branch"
    if ($LASTEXITCODE -ne 0) {
        git branch $Branch
    }
}

git switch feature/phase-1
if ($LASTEXITCODE -ne 0) { throw "Cannot switch to feature/phase-1" }

Write-Host "Git initialized in one physical folder. Current branch: feature/phase-1" -ForegroundColor Green
