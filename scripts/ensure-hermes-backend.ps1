# ensure-hermes-backend.ps1
# Backend-ONLY, idempotent launcher for the machine-level Hermes backend on 127.0.0.1:9119.
#
# WHY THIS EXISTS (OPS-012, diagnosed 2026-09-06):
#   The Hermes backend on 9119 had NO autostart of any kind. After every reboot it
#   stayed down until someone manually ran scripts/start-hermes-omniroute.ps1.
#   Evidence: health sweep Run 11 (21:56 IST) found 9119 DOWN after the 16:56 IST
#   reboot - second occurrence (first: 2026-09-03 Run 1).
#     - Scheduled task "LeadGen-OmniRoute-DSH-AutoStart" covers OmniRoute + DSH only.
#     - LeadGen_AutoBoot.vbs -> autoboot_master.ps1 covers OmniRoute + MCP sync only.
#     - Hermes_Gateway.vbs (Startup) starts gateway-service, a DIFFERENT component.
#
# WHY NOT REUSE start-hermes-omniroute.ps1 AS THE LOGON HOOK:
#   Its step [4/4] always launches the Hermes Desktop GUI and exits 1 if the GUI
#   dies within 20s. Unsuitable for unattended logon. This script uses the SAME
#   backend-spawn mechanism (step [3/4] of that script), extracted, GUI-free.
#
# CONTRACT:
#   already-listening => no-op, exit 0
#   started + ready   => exit 0
#   cannot start      => exit 1
# No secrets printed. No Docker. No remote/host mutation. Nothing outside $LOCALAPPDATA.

param(
    [int]$Port = 9119,
    [int]$ReadyTimeoutSec = 90
)

$ErrorActionPreference = 'Continue'
$RepoRoot  = Split-Path -Parent $PSScriptRoot
$LogPath   = Join-Path $RepoRoot 'uat_evidence\hermes_backend_autostart.log'
$AgentDir  = Join-Path $env:LOCALAPPDATA 'hermes\hermes-agent'
$HermesExe = Join-Path $AgentDir 'venv\Scripts\hermes.exe'

# Log directory may not exist on a fresh clone; never let logging break the boot.
try {
    $logDir = Split-Path -Parent $LogPath
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
} catch { }

function Write-Boot($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Write-Output $line
    try { Add-Content -Path $LogPath -Value $line } catch { }
}

function Test-PortListening {
    param([int]$P)
    $c = Get-NetTCPConnection -LocalPort $P -State Listen -ErrorAction SilentlyContinue
    return ($null -ne $c)
}

Write-Boot "=== ensure-hermes-backend invoked (port=$Port) ==="

if (Test-PortListening -P $Port) {
    Write-Boot "Backend already listening on 127.0.0.1:$Port - no-op."
    exit 0
}

if (-not (Test-Path $HermesExe)) {
    Write-Boot "ERROR: hermes.exe not found at $HermesExe - cannot start backend."
    exit 1
}

try {
    Start-Process -FilePath $HermesExe `
        -ArgumentList 'serve','--skip-build','--host','127.0.0.1','--port',$Port `
        -WorkingDirectory $AgentDir -WindowStyle Hidden
    Write-Boot 'Backend spawn issued.'
} catch {
    Write-Boot "ERROR spawning backend: $($_.Exception.Message)"
    exit 1
}

$deadline = (Get-Date).AddSeconds($ReadyTimeoutSec)
while ((Get-Date) -lt $deadline) {
    if (Test-PortListening -P $Port) {
        $owner = (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
                  Select-Object -First 1).OwningProcess
        Write-Boot "Backend READY on 127.0.0.1:$Port (pid $owner)."
        exit 0
    }
    Start-Sleep -Seconds 2
}

Write-Boot "ERROR: backend did not become ready on 127.0.0.1:$Port within ${ReadyTimeoutSec}s."
exit 1
