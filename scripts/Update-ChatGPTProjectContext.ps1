param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

function Invoke-Git {
    param([string[]]$GitArgs)
    $output = & git -C $ProjectRoot -c core.quotePath=false @GitArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "git $($GitArgs -join ' ') failed: $output"
    }
    return ($output -join "`n")
}

function Get-OptionalGit {
    param([string[]]$GitArgs)
    $output = & git -C $ProjectRoot -c core.quotePath=false @GitArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        return ""
    }
    return ($output -join "`n")
}

$contextPath = Join-Path $ProjectRoot ".ai\CHATGPT_PROJECT_CONTEXT.md"
if (-not (Test-Path -LiteralPath $contextPath)) {
    throw "Context file not found: $contextPath"
}

$root = Invoke-Git @("rev-parse", "--show-toplevel")
$branch = Invoke-Git @("branch", "--show-current")
$head = Invoke-Git @("rev-parse", "--short", "HEAD")
$status = Invoke-Git @("status", "--short", "--branch")
$worktrees = Invoke-Git @("worktree", "list")
$recentCommits = Invoke-Git @("log", "--oneline", "--decorate", "-15")
$remotes = Get-OptionalGit @("remote", "-v")

$migrationDir = Join-Path $ProjectRoot "backend\database\migrations\versions"
$migrations = @()
if (Test-Path -LiteralPath $migrationDir) {
    $migrations = Get-ChildItem -LiteralPath $migrationDir -File |
        Sort-Object Name |
        ForEach-Object { $_.Name }
}

$reportNames = Get-ChildItem -LiteralPath $ProjectRoot -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "PHASE_*_REPORT.md" -or $_.Name -like "CODEX_*_REVIEW.md" } |
    Sort-Object Name |
    ForEach-Object { $_.Name }

$aiReportNames = Get-ChildItem -LiteralPath (Join-Path $ProjectRoot ".ai") -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match "HANDOFF|DECISIONS|TEST_REPORT|SECURITY_REPORT|PROJECT_CONTEXT|CHATGPT_PROJECT_CONTEXT" } |
    Sort-Object Name |
    ForEach-Object { ".ai/$($_.Name)" }

$timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss zzz")
$remoteText = if ([string]::IsNullOrWhiteSpace($remotes)) { "No Git remote configured." } else { $remotes }
$migrationText = if ($migrations.Count -eq 0) { "No migration files found." } else { ($migrations -join "`n") }
$reportText = (($reportNames + $aiReportNames) | Sort-Object) -join "`n"
if ([string]::IsNullOrWhiteSpace($reportText)) {
    $reportText = "No report files found."
}

$dynamic = @"
<!-- CHATGPT_CONTEXT_DYNAMIC_START -->
Last dynamic refresh: $timestamp

Repository root:

~~~~text
$root
~~~~

Current branch:

~~~~text
$branch
~~~~

Current HEAD:

~~~~text
$head
~~~~

Working tree:

~~~~text
$status
~~~~

Worktrees:

~~~~text
$worktrees
~~~~

Recent commits:

~~~~text
$recentCommits
~~~~

Git remotes:

~~~~text
$remoteText
~~~~

Migration files:

~~~~text
$migrationText
~~~~

Phase and review files:

~~~~text
$reportText
~~~~
<!-- CHATGPT_CONTEXT_DYNAMIC_END -->
"@

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
$content = [System.IO.File]::ReadAllText($contextPath, $utf8NoBom)
$pattern = "(?s)<!-- CHATGPT_CONTEXT_DYNAMIC_START -->.*?<!-- CHATGPT_CONTEXT_DYNAMIC_END -->"
if ($content -notmatch $pattern) {
    throw "Dynamic markers not found in $contextPath"
}

$updated = [regex]::Replace($content, $pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $dynamic })
[System.IO.File]::WriteAllText($contextPath, $updated, $utf8NoBom)

Write-Output "Updated $contextPath"
