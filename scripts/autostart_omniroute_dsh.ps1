# autostart_omniroute_dsh.ps1
# Logon-time auto-start wrapper: OmniRoute gateway (WSL, port 20128) + DSH web UI (port 3000).
# Dono underlying launchers IDEMPOTENT hain (already-listening = skip), isliye re-run safe.
# Triggered by Scheduled Task "LeadGen-OmniRoute-DSH-AutoStart" (At log on).

$ErrorActionPreference = 'Continue'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$LogPath = Join-Path $RepoRoot "uat_evidence\autostart_wrapper.log"

function Write-WrapLog($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Add-Content -Path $LogPath -Value $line
}

# Logon ke turant baad WSL/network warm-up ho uske liye bounded delay.
$DelaySeconds = 60
if ($env:AUTOSTART_DELAY_SECONDS) { $DelaySeconds = [int]$env:AUTOSTART_DELAY_SECONDS }

Write-WrapLog "=== autostart wrapper invoked (delay=${DelaySeconds}s) ==="
Start-Sleep -Seconds $DelaySeconds

# --- 1) OmniRoute gateway ---
try {
    Write-WrapLog "Invoking start-omniroute.ps1..."
    & (Join-Path $PSScriptRoot "start-omniroute.ps1") | Out-Null
    Write-WrapLog "start-omniroute.ps1 exit code: $LASTEXITCODE"
} catch {
    Write-WrapLog "ERROR start-omniroute.ps1: $($_.Exception.Message)"
}

# --- 2) DSH web UI ---
try {
    Write-WrapLog "Invoking start-dsh.ps1..."
    & (Join-Path $PSScriptRoot "start-dsh.ps1") | Out-Null
    Write-WrapLog "start-dsh.ps1 exit code: $LASTEXITCODE"
} catch {
    Write-WrapLog "ERROR start-dsh.ps1: $($_.Exception.Message)"
}

Write-WrapLog "=== autostart wrapper done ==="
