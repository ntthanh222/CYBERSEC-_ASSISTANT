param(
    [string]$BaselineCommit = "3c7c79e",
    [string]$IntegrationBranch = "feature/phase-2",
    [string]$BackendBranch = "feature/phase-2-backend",
    [string]$UiBranch = "feature/ui",
    [switch]$Json
)

$ErrorActionPreference = "Stop"

function Invoke-Git {
    param([string[]]$GitArgs)
    $output = & git @GitArgs 2>&1
    $code = $LASTEXITCODE
    return [pscustomobject]@{ Code = $code; Output = ($output -join "`n") }
}

function Add-Check {
    param(
        [string]$Name,
        [bool]$Passed,
        [string]$Detail
    )
    $script:Checks += [pscustomobject]@{ name = $Name; passed = $Passed; detail = $Detail }
    if (-not $Passed) { $script:Failed = $true }
}

$Checks = @()
$Failed = $false

$root = Invoke-Git @("rev-parse", "--show-toplevel")
Add-Check "git repository" ($root.Code -eq 0) $root.Output
if ($root.Code -ne 0) { exit 2 }

$branchList = Invoke-Git @("branch", "--format=%(refname:short)")
$branches = @($branchList.Output -split "`n" | Where-Object { $_ })
foreach ($branch in @("main", $IntegrationBranch, $BackendBranch, $UiBranch)) {
    Add-Check "branch exists: $branch" ($branches -contains $branch) $branch
}

$worktreesResult = Invoke-Git @("worktree", "list", "--porcelain")
$worktreeText = $worktreesResult.Output
Add-Check "backend worktree registered" ($worktreeText -match [regex]::Escape("branch refs/heads/$BackendBranch")) $BackendBranch
Add-Check "ui worktree registered" ($worktreeText -match [regex]::Escape("branch refs/heads/$UiBranch")) $UiBranch

$status = Invoke-Git @("status", "--porcelain")
Add-Check "current worktree clean" ($status.Output.Trim().Length -eq 0) $status.Output

foreach ($branch in @("main", $IntegrationBranch, $BackendBranch, $UiBranch)) {
    if ($branches -contains $branch) {
        $head = Invoke-Git @("rev-parse", "--short", $branch)
        Add-Check "head: $branch" ($head.Code -eq 0) $head.Output

        $contains = Invoke-Git @("merge-base", "--is-ancestor", $BaselineCommit, $branch)
        Add-Check "baseline $BaselineCommit contained in $branch" ($contains.Code -eq 0) $branch
    }
}

$divBackend = Invoke-Git @("rev-list", "--left-right", "--count", "main...$BackendBranch")
Add-Check "backend divergence computable" ($divBackend.Code -eq 0) $divBackend.Output
$divUi = Invoke-Git @("rev-list", "--left-right", "--count", "main...$UiBranch")
Add-Check "ui divergence computable" ($divUi.Code -eq 0) $divUi.Output

if ($Json) {
    [pscustomobject]@{
        ready = (-not $Failed)
        root = $root.Output
        checks = $Checks
    } | ConvertTo-Json -Depth 6
} else {
    foreach ($check in $Checks) {
        $mark = if ($check.passed) { "PASS" } else { "FAIL" }
        Write-Host ("[{0}] {1}: {2}" -f $mark, $check.name, $check.detail)
    }
}

if ($Failed) { exit 1 }
exit 0
