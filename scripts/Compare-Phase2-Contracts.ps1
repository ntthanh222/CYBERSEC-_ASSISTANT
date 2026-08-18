param(
    [ValidateSet("Readiness", "Required")]
    [string]$Mode = "Readiness",
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

function Add-Finding {
    param([string]$Severity, [string]$Module, [string]$Message)
    $script:Findings += [pscustomobject]@{
        severity = $Severity
        module = $Module
        message = $Message
    }
}

$Findings = @()

$backendRoutes = Invoke-Git @("grep", "-n", "@router", $BackendBranch, "--", "backend/api")
$uiFixtures = Invoke-Git @("grep", "-n", "FixtureDataProvider\|mock", $UiBranch, "--", "frontend/src")

$backendText = $backendRoutes.Output
$uiRoutesSource = Invoke-Git @("show", "$UiBranch`:frontend/src/routes/AppRoutes.tsx")
$uiRouteText = $uiRoutesSource.Output
$fixtureText = $uiFixtures.Output

$backendSource = Invoke-Git @("show", "$BackendBranch`:backend/api/chatbot.py")
$backendSource2 = Invoke-Git @("show", "$BackendBranch`:backend/api/tools.py")
$backendSource3 = Invoke-Git @("show", "$BackendBranch`:backend/api/cves.py")
$backendSource4 = Invoke-Git @("show", "$BackendBranch`:backend/api/scan_history.py")
$backendSource5 = Invoke-Git @("show", "$BackendBranch`:backend/api/system.py")
$backendAll = @($backendSource.Output, $backendSource2.Output, $backendSource3.Output, $backendSource4.Output, $backendSource5.Output) -join "`n"

$expectedBackend = @(
    "chat",
    "conversations",
    "ai-health",
    "url-scan",
    "password-check",
    "password-guidance",
    "scan-history",
    "cve_id",
    "search"
)

foreach ($route in $expectedBackend) {
    if ($backendAll -notmatch [regex]::Escape($route)) {
        Add-Finding "P1" "backend-routes" "Expected backend route not observed: $route"
    }
}

$expectedUi = @("/ai", "/toolkit/url-scanner", "/toolkit/password-checker", "/toolkit/cve-lookup", "/toolkit/history", "/threat-intelligence", "/assets", "/vulnerabilities")
foreach ($route in $expectedUi) {
    if ($uiRouteText -notmatch [regex]::Escape("path=`"$route")) {
        Add-Finding "P2" "ui-routes" "Expected UI route not observed: $route"
    }
}

if ($fixtureText -match "FixtureDataProvider|mock") {
    Add-Finding "P2" "ui-adapter" "UI still uses fixtures or mock data providers for Phase 2/3 views."
}

if ($backendText -match "/password-check") {
    Add-Finding "P1" "password-privacy" "Backend password-check endpoint exists; integration must keep UI local-first by default."
}

$pageSchema = Invoke-Git @("grep", "-n", "class Page\|page_size\|items\|total", $BackendBranch, "--", "backend/schemas/common.py", "backend/api")
if ($pageSchema.Output -match "page_size" -and $fixtureText -match "getScanHistory|getChatThreads") {
    Add-Finding "P2" "pagination" "Backend uses page/page_size envelope; UI fixtures are array-based and need adapter tests."
}

$requiredFailure = $false
if ($Mode -eq "Required") {
    $requiredFailure = ($Findings | Where-Object { $_.severity -in @("P1", "P2") } | Measure-Object).Count -gt 0
}

if ($Json) {
    [pscustomobject]@{
        mode = $Mode
        findings = $Findings
        ready = (-not $requiredFailure)
    } | ConvertTo-Json -Depth 5
} else {
    if ($Findings.Count -eq 0) {
        Write-Host "[PASS] No static contract mismatches found."
    } else {
        foreach ($finding in $Findings) {
            Write-Host ("[{0}] {1}: {2}" -f $finding.severity, $finding.module, $finding.message)
        }
    }
}

if ($requiredFailure) { exit 1 }
exit 0
