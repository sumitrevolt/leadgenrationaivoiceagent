param(
    [string]$BaseUrl = "http://127.0.0.1:20128"
)

$ErrorActionPreference = "Stop"

Write-Host "=== omniroute-check.ps1 (Docker mode, ADR-189) ==="

# 1) Check Docker engine
docker version --format '{{.Server.Version}}' *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] Docker engine not reachable. Start Docker Desktop."
    exit 1
}

# 2) Check container status
$container = docker ps --filter "name=leadgen_omniroute" --format "{{.Status}}" 2>$null
if (-not $container) {
    Write-Host "[FAIL] OmniRoute container not running. Run: docker compose -f deploy/compose/docker-compose.omniroute.yml up -d"
    exit 1
}
Write-Host "Container status: $container"

# 3) Check version via container
$version = docker exec leadgen_omniroute omniroute --version 2>&1 | Select-Object -Last 1
if ($LASTEXITCODE -eq 0 -and $version) {
    Write-Host "OmniRoute CLI version: $version"
} else {
    Write-Host "[WARN] Could not get version from container"
}

# 4) Health check HTTP
try {
    $health = Invoke-WebRequest -Uri "$BaseUrl/v1/models" -TimeoutSec 8 -UseBasicParsing
    if ($health.StatusCode -eq 200) {
        Write-Host "OmniRoute gateway is REACHABLE at $BaseUrl"
        $models = $health.Content | ConvertFrom-Json
        $count = ($models.data | Measure-Object).Count
        Write-Host "Available models: $count (loopback-only binding)"
    } else {
        Write-Host "[FAIL] OmniRoute health check failed: HTTP $($health.StatusCode)"
        exit 1
    }
} catch {
    Write-Host "[FAIL] HTTP request failed: $($_.Exception.Message)"
    Write-Host "       Check container logs: docker compose -f deploy/compose/docker-compose.omniroute.yml logs -f omniroute"
    exit 1
}

Write-Host ""
Write-Host "Provider keys and endpoint tokens are intentionally not printed."