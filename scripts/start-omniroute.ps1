# start-omniroute.ps1
# Idempotent, bounded-wait launcher for the OmniRoute gateway (runs inside WSL,
# tmux session "leadgen-omni", window "gateway"). Safe to re-run.
# - Does NOT touch Redis/FastAPI/Celery/PostgreSQL/Qdrant.
# - Does NOT print secrets. Only sanitized status lines.
# Exit codes: 0 = healthy (already running or started), 1 = failed to reach healthy state.

$ErrorActionPreference = 'Stop'
$LogPath = "C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\uat_evidence\omniroute_setup\launcher_log.txt"

function Write-Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Write-Output $line
    Add-Content -Path $LogPath -Value $line
}

function Test-OmniRoutePort {
    $conn = Get-NetTCPConnection -LocalPort 20128 -State Listen -ErrorAction SilentlyContinue
    return [bool]$conn
}

Write-Log "start-omniroute.ps1 invoked"

if (Test-OmniRoutePort) {
    Write-Log "OmniRoute already listening on port 20128 - no action needed (idempotent skip)."
    exit 0
}

Write-Log "Port 20128 not listening. Ensuring tmux session 'leadgen-omni' + window 'gateway' exist and starting omniroute..."

# Ensure session/window exist, then (re)start the omniroute process in the gateway window.
# This does not disturb the other coding-lane windows/panes in the same session.
wsl.exe bash /mnt/c/Users/Ratanshila/Documents/leadgenrationaivoiceagent/scripts/omniroute_ensure_running.sh | Out-Null

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
    Write-Log "Debug command: wsl.exe bash /mnt/c/Users/Ratanshila/Documents/leadgenrationaivoiceagent/scripts/omniroute_debug_capture.sh"
    exit 1
}
