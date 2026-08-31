# start-hermes-omniroute.ps1
# "Open Hermes Desktop -> OmniRoute gateway also comes up."
#
# Ensures the OmniRoute gateway container is running (Docker-based, WSL-free),
# THEN launches the Hermes Desktop app. Idempotent: if OmniRoute is already
# up, it skips the bring-up and just launches Hermes.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\start-hermes-omniroute.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\start-hermes-omniroute.ps1 -HermesApp "C:\path\to\hermes.exe"
#
# Hermes discovery (first match wins, override with -HermesApp):
#   %LOCALAPPDATA%\hermes\bin\hermes.cmd
#   %LOCALAPPDATA%\hermes\hermes-setup.exe
#   %LOCALAPPDATA%\hermes\hermes.exe
#
# gateway-only; providers receive sanitized text only. No secret is printed.

param(
    [string]$HermesApp,
    [string]$Combo = "leadgen.project_best",
    [string]$OmniHost = "127.0.0.1",
    [int]$Port = 20128
)

$ErrorActionPreference = 'Continue'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$StartOmni = Join-Path $RepoRoot 'scripts\start-omniroute.ps1'
$OmniRouteUrl = "http://${OmniHost}:${Port}/v1"

Write-Output "=== start-hermes-omniroute.ps1 ==="
Write-Output "Target OmniRoute Gateway: $OmniRouteUrl"
Write-Output "Selected OmniRoute Combo : $Combo"

# 1) Make sure the local OmniRoute gateway is up if local host
if ($OmniHost -eq "127.0.0.1" -or $OmniHost -eq "localhost") {
    Write-Output "[1/3] Ensuring OmniRoute gateway is up (Docker)..."
    if (Test-Path $StartOmni) {
        & powershell -ExecutionPolicy Bypass -File $StartOmni
    } else {
        Write-Output "WARN: start-omniroute.ps1 not found at $StartOmni"
    }
} else {
    Write-Output "[1/3] Remote OmniRoute Host specified: $OmniHost (skipping local container launch)."
}

# 2) Environment preparation for Hermes process
$apiKey = [Environment]::GetEnvironmentVariable("OMNIROUTE_API_KEY", "User")
if (-not $apiKey) {
    $apiKey = [Environment]::GetEnvironmentVariable("OMNIROUTE_API_KEY", "Process")
}

Write-Output "[2/3] Setting process environment for Hermes Desktop profile..."
$env:OPENAI_BASE_URL = $OmniRouteUrl
$env:ANTHROPIC_BASE_URL = $OmniRouteUrl
$env:OMNIROUTE_COMBO = $Combo
if ($apiKey) {
    $env:OPENAI_API_KEY = $apiKey
    $env:ANTHROPIC_API_KEY = $apiKey
}

# 3) Launch Hermes Desktop.
Write-Output "[3/3] Launching Hermes Desktop..."
$candidates = @(
    $HermesApp,
    (Join-Path $env:LOCALAPPDATA 'hermes\hermes-agent\apps\desktop\release\win-unpacked\Hermes.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Hermes\Hermes.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\hermes\Hermes.exe'),
    (Join-Path $env:LOCALAPPDATA 'hermes\bin\hermes.cmd'),
    (Join-Path $env:LOCALAPPDATA 'hermes\hermes.exe'),
    (Join-Path $env:APPDATA 'Hermes\Hermes.exe')
) | Where-Object { $_ -and (Test-Path $_) }

if ($candidates.Count -gt 0) {
    $target = $candidates[0]
    Write-Output "Launching: $target"
    try {
        Start-Process -FilePath $target
        Write-Output "Hermes Desktop launched (OmniRoute combo '$Combo' active at $OmniRouteUrl)."
    } catch {
        Write-Output "ERROR launching Hermes: $($_.Exception.Message)"
        exit 1
    }
} else {
    Write-Output "WARN: Hermes app binary not found. Pass -HermesApp <path>."
    Write-Output "      OmniRoute gateway is active ($OmniRouteUrl); Hermes environment ready."
    exit 0
}

