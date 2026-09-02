# start-dsh.ps1
# Idempotent, bounded-wait launcher for the DeepSeek Harness (DSH) web UI.
# Runs directly on Windows via npx (NOT WSL).
# Safe to re-run - skips if already listening.
#
# NOTE: DSH is EVAL/RESEARCH only (ADR-179 REJECT as runtime/dep).
#       This launcher exists for local development and pattern exploration.
#       DSH_RUNTIME_ENABLED=0 in prod; this script does NOT arm anything.
#
# Exit codes: 0 = healthy (already running or started), 1 = failed to reach healthy state.

$ErrorActionPreference = 'Stop'
$LogPath = "C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\uat_evidence\dsh_setup\launcher_log.txt"

# --- Configurable defaults ---
$DshPort = $env:DSH_WEB_PORT
if (-not $DshPort) { $DshPort = 3000 }
$MaxWaitSeconds = $env:DSH_MAX_WAIT_SECONDS
if (-not $MaxWaitSeconds) { $MaxWaitSeconds = 120 }
$CheckIntervalSeconds = 2

function Write-Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Write-Output $line
    # Ensure log directory exists
    $logDir = Split-Path $LogPath -Parent
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    Add-Content -Path $LogPath -Value $line
}

function Test-DshPort {
    $conn = Get-NetTCPConnection -LocalPort $DshPort -State Listen -ErrorAction SilentlyContinue
    return [bool]$conn
}

function Test-DshHealthy {
    # Try HTTP health - any response (including 401) proves the server is alive.
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$DshPort/" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        return $true
    } catch {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode.value__) {
            # Any HTTP response = server is up
            return $true
        }
        return $false
    }
}

Write-Log "start-dsh.ps1 invoked (port=$DshPort)"

# --- Idempotent skip if already healthy ---
if (Test-DshPort) {
    Write-Log "DSH already listening on port $DshPort - checking health..."
    if (Test-DshHealthy) {
        Write-Log "DSH healthy on port $DshPort - no action needed (idempotent skip)."
        exit 0
    } else {
        Write-Log "Port $DshPort is listening but health check failed - process may be hung."
        Write-Log "Consider killing the existing process and re-running this script."
        exit 1
    }
}

Write-Log "Port $DshPort not listening. Starting DSH web UI via npx..."

# --- Check prerequisites ---
# Verify npx is available
try {
    $npxVersion = & npx --version 2>&1
    Write-Log "npx version: $npxVersion"
} catch {
    Write-Log "ERROR: npx not found. Ensure Node.js is installed and on PATH."
    exit 1
}

# --- Start DSH web in background ---
# Use Start-Process so the DSH process survives this launcher exiting.
# Redirect stdout/stderr to log files for debugging.
$dshOutLog = Join-Path (Split-Path $LogPath -Parent) "dsh_stdout.log"
$dshErrLog = Join-Path (Split-Path $LogPath -Parent) "dsh_stderr.log"

try {
    # npx = .cmd batch shim - Start-Process direct launch "%1 is not a valid Win32 application" deta hai.
    # Isliye cmd.exe /c wrapper use karo.
    $startArgs = @{
        FilePath     = "cmd.exe"
        ArgumentList = "/c", "npx", "@deepseek-ai/dsh", "web", "--port", $DshPort
        WindowStyle  = "Hidden"
        RedirectStandardOutput = $dshOutLog
        RedirectStandardError  = $dshErrLog
    }
    $proc = Start-Process @startArgs -PassThru
    Write-Log "DSH process started (PID=$($proc.Id)). Waiting for bounded health readiness (max ${MaxWaitSeconds}s)..."
} catch {
    Write-Log "ERROR: Failed to start DSH process: $($_.Exception.Message)"
    exit 1
}

# --- Bounded wait for health ---
$ready = $false
$checks = [math]::Floor($MaxWaitSeconds / $CheckIntervalSeconds)
for ($i = 0; $i -lt $checks; $i++) {
    Start-Sleep -Seconds $CheckIntervalSeconds

    # Check if process already exited (crashed)
    if ($proc.HasExited) {
        Write-Log "DSH process exited prematurely (exit code=$($proc.ExitCode))."
        Write-Log "Check stderr log: $dshErrLog"
        exit 1
    }

    if (Test-DshHealthy) {
        $ready = $true
        break
    }
}

if ($ready) {
    Write-Log "DSH web UI reachable on port $DshPort after start. Open http://127.0.0.1:$DshPort in browser."
    exit 0
} else {
    Write-Log "DSH did NOT become reachable within ${MaxWaitSeconds}s."
    Write-Log "Process may still be starting (npx cold-cache download can be slow on first run)."
    Write-Log "Check logs:"
    Write-Log "  stdout: $dshOutLog"
    Write-Log "  stderr: $dshErrLog"
    Write-Log "Manual check: curl http://127.0.0.1:$DshPort/"
    Write-Log "Kill process if needed: Stop-Process -Id $($proc.Id) -Force"
    exit 1
}
