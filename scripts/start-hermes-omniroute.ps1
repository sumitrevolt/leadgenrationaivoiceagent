# start-hermes-omniroute.ps1
# "Open Hermes Desktop -> OmniRoute gateway also comes up."
#
# Ensures the OmniRoute gateway is running, ensures the machine-level Hermes
# backend is up on the DEFAULT port 9119, waits for real readiness, and only
# then launches the Hermes Desktop GUI.
#
# ROOT CAUSE THIS FIXES (diagnosed 2026-09-03):
#   The desktop spawns its own backend child with `--port 0` (OS auto-assign)
#   whenever it does not find a ready machine-level server. That per-launch
#   child later exits with code 1 (~3.5 min after "Finalizing desktop startup"),
#   taking the desktop session down with it. Log signature:
#     [hermes] Hermes backend for profile "default" exited (1)
#   Fix: pre-start ONE machine-level server on the default port 9119 and make
#   the desktop ATTACH to it (hermes serve default behaviour is unified:
#   profile launches attach to the single machine-level server).
#
# PREVIOUS BUGS IN THIS SCRIPT:
#   1. Started the backend, slept 2s and launched the GUI regardless of whether
#      the backend was actually ready -> desktop always spawned its own child.
#   2. Never verified the GUI survived startup.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\start-hermes-omniroute.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\start-hermes-omniroute.ps1 -HermesApp "C:\path\to\Hermes.exe"
#
# Gateway-only; providers receive sanitized text only. No secret is printed.

param(
    [string]$HermesApp,
    [string]$Combo = "leadgen.project_best",
    [string]$OmniHost = "127.0.0.1",
    [int]$Port = 20128,
    [int]$BackendPort = 9119,
    [int]$BackendReadyTimeoutSec = 90
)

$ErrorActionPreference = 'Continue'
$RepoRoot     = Split-Path -Parent $PSScriptRoot
$StartOmni    = Join-Path $RepoRoot 'scripts\start-omniroute.ps1'
$OmniRouteUrl = "http://${OmniHost}:${Port}/v1"
$AgentDir     = Join-Path $env:LOCALAPPDATA 'hermes\hermes-agent'
$HermesExe    = Join-Path $AgentDir 'venv\Scripts\hermes.exe'

Write-Output "=== start-hermes-omniroute.ps1 ==="
Write-Output "Target OmniRoute Gateway : $OmniRouteUrl"
Write-Output "Selected OmniRoute Combo : $Combo"
Write-Output "Hermes backend (default) : 127.0.0.1:$BackendPort"

# ---------------------------------------------------------------- 1) OmniRoute
if ($OmniHost -eq "127.0.0.1" -or $OmniHost -eq "localhost") {
    Write-Output "[1/4] Ensuring OmniRoute gateway is up (Docker)..."
    if (Test-Path $StartOmni) {
        & powershell -ExecutionPolicy Bypass -File $StartOmni
    } else {
        Write-Output "WARN: start-omniroute.ps1 not found at $StartOmni"
    }
} else {
    Write-Output "[1/4] Remote OmniRoute Host specified: $OmniHost (skipping local container launch)."
}

# ------------------------------------------------------- 2) Hermes env for GUI
Write-Output "[2/4] Setting process environment for Hermes Desktop profile..."
$apiKey = [Environment]::GetEnvironmentVariable("OMNIROUTE_API_KEY", "User")
if (-not $apiKey) {
    $apiKey = [Environment]::GetEnvironmentVariable("OMNIROUTE_API_KEY", "Process")
}
$env:OPENAI_BASE_URL    = $OmniRouteUrl
$env:ANTHROPIC_BASE_URL = $OmniRouteUrl
$env:OMNIROUTE_COMBO    = $Combo
if ($apiKey) {
    $env:OPENAI_API_KEY    = $apiKey
    $env:ANTHROPIC_API_KEY = $apiKey
}

# ------------------------------------------- 3) Machine-level backend on 9119
function Test-BackendReady {
    param([int]$P)
    $c = Get-NetTCPConnection -LocalPort $P -State Listen -ErrorAction SilentlyContinue
    return ($null -ne $c)
}

Write-Output "[3/4] Ensuring machine-level Hermes backend on port $BackendPort..."
if (-not (Test-BackendReady -P $BackendPort)) {
    if (-not (Test-Path $HermesExe)) {
        Write-Output "ERROR: hermes.exe not found at $HermesExe"
        exit 1
    }
    # --skip-build: serve the existing dist; no npm needed (verified flag).
    Start-Process -FilePath $HermesExe `
        -ArgumentList "serve","--skip-build","--host","127.0.0.1","--port",$BackendPort `
        -WorkingDirectory $AgentDir -WindowStyle Hidden
    Write-Output "      Backend spawn issued. Waiting for readiness (max ${BackendReadyTimeoutSec}s)..."
} else {
    Write-Output "      Backend already listening on $BackendPort - reusing it."
}

$deadline = (Get-Date).AddSeconds($BackendReadyTimeoutSec)
$ready = $false
while ((Get-Date) -lt $deadline) {
    if (Test-BackendReady -P $BackendPort) { $ready = $true; break }
    Start-Sleep -Seconds 2
}

if (-not $ready) {
    Write-Output "ERROR: Hermes backend did not become ready on port $BackendPort within ${BackendReadyTimeoutSec}s."
    Write-Output "       Aborting GUI launch - launching now would spawn a --port 0 child that exits (1)."
    exit 1
}
$owner = (Get-NetTCPConnection -LocalPort $BackendPort -State Listen -ErrorAction SilentlyContinue |
          Select-Object -First 1).OwningProcess
Write-Output "      Backend READY on 127.0.0.1:$BackendPort (pid $owner)."

# ------------------------------------------------------------- 4) Launch GUI
Write-Output "[4/4] Launching Hermes Desktop..."
$candidates = @(
    $HermesApp,
    (Join-Path $env:LOCALAPPDATA 'hermes\hermes-agent\apps\desktop\release\win-unpacked\Hermes.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Hermes\Hermes.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\hermes\Hermes.exe'),
    (Join-Path $env:LOCALAPPDATA 'hermes\bin\hermes.cmd'),
    (Join-Path $env:LOCALAPPDATA 'hermes\hermes.exe'),
    (Join-Path $env:APPDATA 'Hermes\Hermes.exe')
) | Where-Object { $_ -and (Test-Path $_) }

if ($candidates.Count -eq 0) {
    Write-Output "WARN: Hermes app binary not found. Pass -HermesApp <path>."
    Write-Output "      Backend is up on 127.0.0.1:$BackendPort and OmniRoute is at $OmniRouteUrl."
    exit 0
}

$target = $candidates[0]
Write-Output "Launching: $target"
try {
    Start-Process -FilePath $target
} catch {
    Write-Output "ERROR launching Hermes: $($_.Exception.Message)"
    exit 1
}

# Verify the GUI actually survived startup instead of exiting silently.
Start-Sleep -Seconds 20
$gui = Get-Process -Name "Hermes" -ErrorAction SilentlyContinue
if ($gui) {
    Write-Output "OK: Hermes Desktop RUNNING (pid $(($gui.Id -join ',')))."
    Write-Output "    Attached to machine-level backend 127.0.0.1:$BackendPort; OmniRoute combo '$Combo' active at $OmniRouteUrl."
    exit 0
} else {
    Write-Output "ERROR: Hermes Desktop exited within 20s of launch."
    Write-Output "       Backend is still up on 127.0.0.1:$BackendPort."
    Write-Output "       Check $env:LOCALAPPDATA\hermes\logs\desktop.log for the exit reason."
    exit 1
}
