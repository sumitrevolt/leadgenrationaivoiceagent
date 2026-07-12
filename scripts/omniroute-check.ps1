param(
    [string]$BaseUrl = "http://127.0.0.1:20128"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command omniroute -ErrorAction SilentlyContinue)) {
    throw "OmniRoute is not installed on this host. Install it inside WSL: npm install -g omniroute"
}

Write-Host "OmniRoute CLI:"
omniroute --version

$health = Invoke-WebRequest -Uri "$BaseUrl/health" -TimeoutSec 8 -UseBasicParsing
if ($health.StatusCode -ne 200) {
    throw "OmniRoute health check failed: HTTP $($health.StatusCode)"
}

Write-Host "OmniRoute local gateway is reachable at $BaseUrl"
Write-Host "Provider keys and endpoint tokens are intentionally not printed."
