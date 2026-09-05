# start-leadgen-dev.ps1 — one-command local dev bring-up (ADR-189: Docker-only, WSL removed).
# Brings up: Docker Redis broker + Docker OmniRoute gateway + verifies Windows venv.
# Dev-only, loopback-only, idempotent. Does NOT touch production, .env, or VPS stack.
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\start-leadgen-dev.ps1

$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot
$ComposeOmni = Join-Path $repo 'deploy\compose\docker-compose.omniroute.yml'

Write-Host '==================================================='
Write-Host ' LeadGen local dev bring-up (Docker: Redis + OmniRoute)'
Write-Host '==================================================='

# 1) Docker engine check
Write-Host ''
Write-Host '== Docker Engine =='
docker version --format '{{.Server.Version}}' *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host '[FAIL] Docker engine not reachable. Start Docker Desktop, then re-run.'
} else {
    Write-Host '[OK] Docker engine reachable'
}

# 2) Start OmniRoute gateway (idempotent)
Write-Host ''
Write-Host '== OmniRoute Gateway =='
if (Test-Path $ComposeOmni) {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'start-omniroute.ps1')
} else {
    Write-Host "[WARN] Compose file not found: $ComposeOmni"
}

# 3) Start Redis broker (idempotent) - standalone container
Write-Host ''
Write-Host '== Redis Broker (loopback) =='
$redisStatus = docker ps --filter "name=leadgen_redis" --format "{{.Status}}" 2>$null
if (-not $redisStatus) {
    Write-Host "Starting Redis container..."
    docker run -d --name leadgen_redis -p 127.0.0.1:6379:6379 redis:7-alpine 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Redis started on 127.0.0.1:6379"
    } else {
        Write-Host "[FAIL] Redis container start failed"
    }
} else {
    Write-Host "[OK] Redis already running: $redisStatus"
}

# 4) Windows venv sanity
Write-Host ''
Write-Host '== Windows venv =='
$venv = Join-Path $repo '.venv\Scripts\python.exe'
if (Test-Path $venv) {
    & $venv --version
    Write-Host 'verify gate:  .venv\Scripts\python.exe scripts\prod_check.py'
} else {
    Write-Host 'venv missing — create: python -m venv .venv; .venv\Scripts\pip install --no-deps -r requirements.lock.txt'
}

# 5) Summary
Write-Host ''
Write-Host '== Ready =='
Write-Host 'OmniRoute dashboard : http://127.0.0.1:20128   (live-WS 20129 loopback-locked)'
Write-Host 'Redis broker        : 127.0.0.1:6379  (Docker redis:7-alpine)'
Write-Host 'OmniRoute logs      : docker compose -f deploy/compose/docker-compose.omniroute.yml logs -f omniroute'
Write-Host 'Redis logs          : docker logs -f leadgen_redis'
Write-Host ''
Write-Host 'Providers receive sanitized text only. No secrets in Docker.'
Write-Host ''
Write-Host 'Unity WebGL build (pending USER action): add Windows Defender exclusion for'
Write-Host '  C:\Program Files\Unity\Hub\Editor\2022.3.62f3'
Write-Host 'then:  cd unity\LeadGenVirtualOffice; & "C:\Program Files\Unity\Hub\Editor\2022.3.62f3\Editor\Unity.exe" -batchmode -quit -projectPath . -executeMethod LeadGen.Office.Editor.WebGLBuild.Build -logFile ..\build.log'