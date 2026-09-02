# start-omniroute.ps1 — Idempotent, bounded-wait launcher for OmniRoute gateway (Docker).
# -----------------------------------------------------------------------------
# Replaces the old WSL/tmux launcher after ADR-189 (WSL removed, Docker-only).
# - Does NOT touch Redis/FastAPI/Celery/PostgreSQL/Qdrant.
# - Does NOT print secrets. Only sanitized status lines.
# Exit codes: 0 = healthy (already running or started), 1 = failed to reach healthy state.

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $RepoRoot 'deploy\compose\docker-compose.omniroute.yml'
$LogPath = Join-Path $RepoRoot 'uat_evidence\omniroute_setup\launcher_log.txt'

function Write-Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Write-Output $line
    Add-Content -Path $LogPath -Value $line
}

function Test-OmniRoutePort {
    $conn = Get-NetTCPConnection -LocalPort 20128 -State Listen -ErrorAction SilentlyContinue
    return [bool]$conn
}

function Test-DockerEngine {
    docker version --format '{{.Server.Version}}' *> $null
    return ($LASTEXITCODE -eq 0)
}

Write-Log "start-omniroute.ps1 invoked (Docker mode, ADR-189)"

# 0) Preflight: Docker engine must be reachable
if (-not (Test-DockerEngine)) {
    Write-Log "[FAIL] Docker engine not reachable. Start Docker Desktop, then re-run."
    exit 1
}

# 1) Idempotent: if already listening on 20128, skip
if (Test-OmniRoutePort) {
    Write-Log "OmniRoute already listening on port 20128 - no action needed (idempotent skip)."
    exit 0
}

# 2) Start container via Docker Compose (builds if image missing)
Write-Log "Starting OmniRoute gateway container..."
$startResult = docker compose -f $ComposeFile up -d --build 2>&1
Write-Log "Compose output: $startResult"
if ($LASTEXITCODE -ne 0) {
    Write-Log "[FAIL] Docker compose up failed: $startResult"
    exit 1
}

# 3) Bounded wait for health readiness (max 30s)
Write-Log "Start command sent. Waiting for bounded health readiness (max 30s)..."
$ready = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 2
    if (Test-OmniRoutePort) {
        $ready = $true
        break
    }
}

if ($ready) {
    Write-Log "OmniRoute reachable on port 20128 after start. Degraded-mode NOT needed."
    exit 0
} else {
    Write-Log "OmniRoute did NOT become reachable within 30s."
    Write-Log "Degraded-mode: existing LeadGen AI fallback chain (free_ai.py) remains available."
    Write-Log "OmniRoute routing is simply unavailable until manually investigated."
    Write-Log "Debug: docker compose -f $ComposeFile logs -f omniroute"
    exit 1
}