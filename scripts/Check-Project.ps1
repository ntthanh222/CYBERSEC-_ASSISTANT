[CmdletBinding()]
param(
    [string]$BackendUrl = "http://localhost:8000",
    [string]$FrontendUrl = "http://localhost:3000",
    [string]$ComposeFile = "docker-compose.yml"
)

# Read-only local diagnostics for the Docker one-command stack. Never
# starts, stops, restarts, or otherwise mutates anything - every command
# below is a read (docker ps/inspect/stats/system df, HTTP GET). Never
# prints a secret, token, password, or connection string; only aggregated
# status fields from /api/system/health and container metadata are shown.

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$script:degraded = 0
$script:failed = 0

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "== $Title ==" -ForegroundColor Cyan
}

function Test-Endpoint {
    param([string]$Name, [string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
        if ($response.StatusCode -eq 200) {
            Write-Host "[PASS] $Name ($Url) -> 200" -ForegroundColor Green
            return $response
        }
        Write-Host "[FAIL] $Name ($Url) -> $($response.StatusCode)" -ForegroundColor Red
        $script:failed++
        return $null
    } catch {
        Write-Host "[FAIL] $Name ($Url) -> $($_.Exception.Message)" -ForegroundColor Red
        $script:failed++
        return $null
    }
}

Write-Section "Docker Desktop"
try {
    docker info --format '{{.ServerVersion}}' | Out-Null
    Write-Host "[PASS] Docker Desktop is reachable" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Docker Desktop is not reachable: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    Write-Host "OVERALL: FAILED (Docker Desktop unreachable - nothing else can be checked)" -ForegroundColor Red
    exit 2
}

Write-Section "Container status"
docker compose -f $ComposeFile ps

$services = @("postgres", "redis", "backend", "frontend")
$containerIds = @{}
foreach ($service in $services) {
    $id = (docker compose -f $ComposeFile ps -q $service 2>$null)
    if ($id) { $containerIds[$service] = $id.Trim() }
}

# The Compose project name (needed to scope the volume-usage report to only
# this project's own volumes, not every project on the machine) is read
# from a running container's own label rather than guessed from the
# directory name - Compose's directory-name sanitization isn't something
# this script should have to reimplement.
$composeProjectName = $null
foreach ($id in $containerIds.Values) {
    $composeProjectName = docker inspect --format '{{ index .Config.Labels `com.docker.compose.project` }}' $id 2>$null
    if ($composeProjectName) { break }
}

Write-Section "Container health, restarts, memory"
foreach ($service in $services) {
    if (-not $containerIds.ContainsKey($service) -or -not $containerIds[$service]) {
        Write-Host "[FAIL] $service : container not found" -ForegroundColor Red
        $script:failed++
        continue
    }
    $id = $containerIds[$service]
    $state = docker inspect --format '{{.State.Status}}' $id
    $health = docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}(no healthcheck){{end}}' $id
    $restarts = docker inspect --format '{{.RestartCount}}' $id
    $startedAt = docker inspect --format '{{.State.StartedAt}}' $id

    $color = "Green"
    if ($health -eq "unhealthy" -or $state -ne "running") {
        $color = "Red"; $script:failed++
    } elseif ($health -eq "starting") {
        $color = "Yellow"; $script:degraded++
    }
    Write-Host "[$service] state=$state health=$health restarts=$restarts startedAt=$startedAt" -ForegroundColor $color

    $stats = docker stats $id --no-stream --format '{{.CPUPerc}} {{.MemUsage}}' 2>$null
    if ($stats) { Write-Host "  resource usage: $stats" -ForegroundColor DarkGray }
}

Write-Section "Backend liveness + readiness"
Test-Endpoint -Name "backend /health (liveness)" -Url "$BackendUrl/health" | Out-Null

$systemHealth = Test-Endpoint -Name "backend /api/system/health (readiness)" -Url "$BackendUrl/api/system/health"
if ($systemHealth) {
    $body = $systemHealth.Content | ConvertFrom-Json
    Write-Host "  overall readiness status: $($body.status)" -ForegroundColor DarkCyan
    if ($body.status -eq "degraded") { $script:degraded++ }
    if ($body.status -eq "unavailable") { $script:failed++ }

    foreach ($checkName in $body.checks.PSObject.Properties.Name) {
        $check = $body.checks.$checkName
        $checkColor = "DarkCyan"
        if ($check.status -eq "unavailable") { $checkColor = "Red" }
        elseif ($check.status -eq "degraded") { $checkColor = "Yellow" }
        Write-Host "  - $checkName : $($check.status) ($($check.latency_ms) ms)" -ForegroundColor $checkColor
    }

    if ($body.embedding) {
        Write-Host "  embedding readiness: $($body.embedding.status)" -ForegroundColor DarkCyan
        if ($body.embedding.elapsed_seconds) {
            Write-Host "    elapsed: $($body.embedding.elapsed_seconds)s" -ForegroundColor DarkGray
        }
        if ($body.embedding.status -eq "warming") {
            Write-Host "    (normal on a fresh container - the AI model is still loading)" -ForegroundColor DarkGray
        }
        if ($body.embedding.status -eq "failed") {
            $script:degraded++
        }
    } else {
        Write-Host "  embedding readiness: (not reported by this backend build)" -ForegroundColor DarkGray
    }
}

Write-Section "Frontend"
Test-Endpoint -Name "frontend /health" -Url "$FrontendUrl/health" | Out-Null
Test-Endpoint -Name "frontend /" -Url "$FrontendUrl/" | Out-Null

Write-Section "Volume disk usage"
if (-not $composeProjectName) {
    Write-Host "  (could not determine the Compose project name - skipping)" -ForegroundColor DarkGray
} else {
    # `docker system df -v`'s JSON mode is inconsistent across Docker
    # Desktop versions (observed emitting one blob per resource type rather
    # than one object per volume), so this parses the stable plain-text
    # table instead: skip down to the "VOLUME NAME" section, then keep only
    # THIS project's own volumes (many other projects' volumes typically
    # coexist on a dev machine and must not be listed here).
    $dfLines = docker system df -v 2>$null
    $inVolumeSection = $false
    $prefix = "$composeProjectName" + "_"
    $found = $false
    foreach ($line in $dfLines) {
        if ($line -match '^VOLUME NAME') { $inVolumeSection = $true; continue }
        if (-not $inVolumeSection) { continue }
        if ($line.StartsWith($prefix)) {
            Write-Host "  $line" -ForegroundColor DarkGray
            $found = $true
        }
    }
    if (-not $found) {
        Write-Host "  (no volumes found with prefix '$prefix')" -ForegroundColor DarkGray
    }
}

Write-Section "Recent log errors (last 20 lines per container, ERROR/CRITICAL only)"
foreach ($service in $services) {
    if (-not $containerIds.ContainsKey($service)) { continue }
    $id = $containerIds[$service]
    # `docker logs` mixes stdout/stderr and many services (Postgres in
    # particular) log routine, non-error lines to stderr - under this
    # script's global $ErrorActionPreference = "Stop", redirecting a native
    # exe's stderr with 2>&1 turns every such line into a terminating
    # NativeCommandError instead of ordinary text. Scope Continue to just
    # this call rather than relaxing it script-wide.
    $lines = & {
        $ErrorActionPreference = "Continue"
        docker logs $id --tail 200 2>&1
    } | Select-String -Pattern '"level":\s*"(ERROR|CRITICAL)"|FATAL|Traceback' | Select-Object -Last 20
    if ($lines) {
        Write-Host "[$service] recent errors:" -ForegroundColor Yellow
        $lines | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkYellow }
    } else {
        Write-Host "[$service] no recent errors" -ForegroundColor Green
    }
}

Write-Section "Overall"
if ($script:failed -gt 0) {
    Write-Host "OVERALL: FAILED ($($script:failed) failing check(s), $($script:degraded) degraded)" -ForegroundColor Red
    exit 1
} elseif ($script:degraded -gt 0) {
    Write-Host "OVERALL: DEGRADED ($($script:degraded) degraded check(s))" -ForegroundColor Yellow
    exit 0
} else {
    Write-Host "OVERALL: HEALTHY" -ForegroundColor Green
    exit 0
}
