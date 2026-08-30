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
    [string]$HermesApp
)

$ErrorActionPreference = 'Continue'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$StartOmni = Join-Path $RepoRoot 'scripts\start-omniroute.ps1'

Write-Output "=== start-hermes-omniroute.ps1 ==="

# 1) Make sure the OmniRoute gateway is up (idempotent; graceful-degrade on failure).
Write-Output "[1/2] Ensuring OmniRoute gateway is up (Docker)..."
if (Test-Path $StartOmni) {
    & powershell -ExecutionPolicy Bypass -File $StartOmni
} else {
    Write-Output "WARN: start-omniroute.ps1 not found at $StartOmni"
}

# 2) Launch Hermes Desktop.
Write-Output "[2/2] Launching Hermes Desktop..."
$candidates = @(
    $HermesApp,
    (Join-Path $env:LOCALAPPDATA 'hermes\bin\hermes.cmd'),
    (Join-Path $env:LOCALAPPDATA 'hermes\hermes-setup.exe'),
    (Join-Path $env:LOCALAPPDATA 'hermes\hermes.exe')
) | Where-Object { $_ -and (Test-Path $_) }

if ($candidates.Count -gt 0) {
    $target = $candidates[0]
    Write-Output "Launching: $target"
    try {
        Start-Process -FilePath $target
        Write-Output "Hermes Desktop launched (OmniRoute gateway is up)."
    } catch {
        Write-Output "ERROR launching Hermes: $($_.Exception.Message)"
        exit 1
    }
} else {
    Write-Output "WARN: Hermes app not found under %LOCALAPPDATA%\hermes. Pass -HermesApp <path>."
    Write-Output "      OmniRoute gateway is up; Hermes launch skipped."
    exit 2
}
