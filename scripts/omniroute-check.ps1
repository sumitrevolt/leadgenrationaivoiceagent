param(
    [string]$BaseUrl = "http://127.0.0.1:20128"
)

$ErrorActionPreference = "Stop"

$wslOmni = "/root/.nvm/versions/node/v22.23.1/bin/omniroute"
$wslPath = "/root/.nvm/versions/node/v22.23.1/bin:/usr/bin:/bin"
$version = (& wsl.exe -d Ubuntu-24.04 -- env -i HOME=/root PATH=$wslPath $wslOmni --version 2>&1 | Select-Object -Last 1)
if ($LASTEXITCODE -ne 0 -or -not $version) {
    throw "OmniRoute is not available in WSL Ubuntu-24.04 with the pinned Node 22 runtime."
}

Write-Host "OmniRoute CLI:"
Write-Host $version

$health = Invoke-WebRequest -Uri "$BaseUrl/v1/models" -TimeoutSec 8 -UseBasicParsing
if ($health.StatusCode -ne 200) {
    throw "OmniRoute health check failed: HTTP $($health.StatusCode)"
}

Write-Host "OmniRoute local gateway is reachable at $BaseUrl"
Write-Host "Provider keys and endpoint tokens are intentionally not printed."
