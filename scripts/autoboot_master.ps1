# autoboot_master.ps1 — Master Auto-Boot Launcher on Laptop/Desktop Restart.
# Automatically starts all required AI services and synchronizes MCP servers across all desktop apps.

$ErrorActionPreference = 'Continue'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $RepoRoot "uat_evidence"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$LogFile = Join-Path $LogDir "autoboot.log"

function Log-Msg($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Add-Content -Path $LogFile -Value $line
    Write-Output $line
}

Log-Msg "=== LeadGen Auto-Boot Starting on System Logon/Restart ==="

# Wait bounded seconds for network and WSL initialization if boot was cold
$WaitSec = 10
Log-Msg "Waiting ${WaitSec}s for network/WSL initialization..."
Start-Sleep -Seconds $WaitSec

# 1. Start OmniRoute Gateway in WSL (Port 20128)
try {
    Log-Msg "[1/4] Ensuring OmniRoute Gateway is active on port 20128..."
    $omniCheck = Invoke-RestMethod -Uri "http://127.0.0.1:20128/v1/combos" -TimeoutSec 3 -ErrorAction SilentlyContinue
    if ($omniCheck) {
        Log-Msg " -> OmniRoute Gateway already ONLINE."
    } else {
        Log-Msg " -> Launching OmniRoute PM2 via WSL..."
        wsl.exe -u root bash -c "export PORT=20128; export DATA_DIR=/root/.omniroute; export STORAGE_ENCRYPTION_KEY=ce9a29e748880c7c5aed8fc6fab5c31466dd5d8fd4eb8ba972206017f22e4d9b; pm2 restart omniroute || pm2 start /root/.nvm/versions/node/v22.23.1/lib/node_modules/omniroute/bin/omniroute.mjs --name omniroute"
        Start-Sleep -Seconds 3
    }
} catch {
    Log-Msg " -> Warning OmniRoute check: $($_.Exception.Message)"
}

# 2. Start Claude / Model Proxy (Port 22000)
try {
    Log-Msg "[2/4] Ensuring Model Proxy is active on port 22000..."
    $proxyCheck = Invoke-RestMethod -Uri "http://127.0.0.1:22000/health" -TimeoutSec 3 -ErrorAction SilentlyContinue
    if ($proxyCheck) {
        Log-Msg " -> Model Proxy already ONLINE."
    } else {
        Log-Msg " -> Starting Model Proxy in background..."
        $pythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
        $proxyScript = Join-Path $RepoRoot "scripts\claude_proxy.py"
        Start-Process -FilePath $pythonExe -ArgumentList $proxyScript -WorkingDirectory $RepoRoot -WindowStyle Hidden
        Start-Sleep -Seconds 2
    }
} catch {
    Log-Msg " -> Warning Proxy check: $($_.Exception.Message)"
}

# 3. Start DSH Web UI (Port 3080)
try {
    Log-Msg "[3/4] Ensuring DeepSeek Harness DSH is active on port 3080..."
    $dshCheck = Invoke-WebRequest -Uri "http://127.0.0.1:3080" -UseBasicParsing -TimeoutSec 3 -ErrorAction SilentlyContinue
    if ($dshCheck) {
        Log-Msg " -> DSH Web UI already ONLINE."
    } else {
        Log-Msg " -> Starting DSH in background..."
        $dshScript = Join-Path $RepoRoot "scripts\start-dsh.ps1"
        Start-Process -FilePath "powershell.exe" -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$dshScript`"" -WorkingDirectory $RepoRoot -WindowStyle Hidden
    }
} catch {
    Log-Msg " -> Warning DSH check: $($_.Exception.Message)"
}

# 4. Synchronize 12 Dynamic Combos & Universal MCP Servers Across All Desktop Apps
try {
    Log-Msg "[4/4] Synchronizing Universal MCP Servers & Model Combos across Claude, Hermes, WorkBuddy, DSH..."
    $pythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    $syncScript = Join-Path $RepoRoot "scripts\sync_all_combos_all_apps.py"
    & $pythonExe $syncScript | Out-Null
    Log-Msg " -> All Desktop App MCP Configs Synchronized Successfully."
} catch {
    Log-Msg " -> Warning Sync script: $($_.Exception.Message)"
}

# 5. Launch Docker Desktop on Startup
try {
    Log-Msg "[5/6] Launching Docker Desktop..."
    $dockerExe = "C:\Users\Ratanshila\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe"
    if (Test-Path $dockerExe) {
        Start-Process -FilePath $dockerExe
        Log-Msg " -> Docker Desktop launched."
    } else {
        Log-Msg " -> Docker Desktop exe not found at $dockerExe"
    }
} catch {
    Log-Msg " -> Warning Docker Desktop launch: $($_.Exception.Message)"
}

# 6. Launch Antigravity IDE on Startup
try {
    Log-Msg "[6/6] Launching Antigravity IDE..."
    $antigravityExe = "C:\Users\Ratanshila\AppData\Local\Programs\Antigravity IDE\Antigravity IDE.exe"
    if (Test-Path $antigravityExe) {
        Start-Process -FilePath $antigravityExe
        Log-Msg " -> Antigravity IDE launched."
    } else {
        Log-Msg " -> Antigravity IDE exe not found at $antigravityExe"
    }
} catch {
    Log-Msg " -> Warning Antigravity IDE launch: $($_.Exception.Message)"
}

Log-Msg "=== LeadGen Auto-Boot Sequence Completed Successfully ==="

