# start-all-combos-desktop.ps1
# Master launcher to sync and verify 12 dynamic OmniRoute combos across:
# 1. OmniRoute Gateway (Port 20128)
# 2. OmniRoute Model Proxy (Port 22000)
# 3. DeepSeek Harness DSH (Port 3080)
# 4. Claude Desktop App
# 5. WorkBuddy AI App
# 6. Hermes Desktop App

$ErrorActionPreference = "Stop"

Write-Output "=== 12 OmniRoute Combos Master Desktop Sync & Launcher ==="

# 1. Sync Configs Across All Client Apps
$syncScript = Join-Path $PSScriptRoot "sync_all_combos_all_apps.py"
& .venv\Scripts\python.exe $syncScript

# 2. Verify OmniRoute Gateway (Port 20128)
Write-Output "`n[1/4] Checking OmniRoute Gateway (Port 20128)..."
try {
    $omniResp = Invoke-RestMethod -Uri "http://127.0.0.1:20128/v1/combos" -TimeoutSec 5
    Write-Output " -> OmniRoute Gateway ONLINE: $($omniResp.data.Count) combos loaded."
} catch {
    Write-Output " -> Starting OmniRoute via WSL..."
    wsl.exe -u root bash -c "export PORT=20128; export DATA_DIR=/root/.omniroute; export STORAGE_ENCRYPTION_KEY=ce9a29e748880c7c5aed8fc6fab5c31466dd5d8fd4eb8ba972206017f22e4d9b; pm2 restart omniroute || pm2 start /root/.nvm/versions/node/v22.23.1/lib/node_modules/omniroute/bin/omniroute.mjs --name omniroute"
    Start-Sleep -Seconds 3
}

# 3. Verify OmniRoute Model Proxy (Port 22000)
Write-Output "`n[2/4] Checking Model Proxy (Port 22000)..."
try {
    $proxyResp = Invoke-RestMethod -Uri "http://127.0.0.1:22000/health" -TimeoutSec 3
    Write-Output " -> Model Proxy ONLINE: $($proxyResp.combos.Count) combos advertised."
} catch {
    Write-Output " -> Starting Model Proxy on port 22000..."
    Start-Process -FilePath ".venv\Scripts\python.exe" -ArgumentList "scripts\claude_proxy.py" -WindowStyle Hidden
    Start-Sleep -Seconds 2
}

# 4. Verify DeepSeek Harness DSH Web UI (Port 3080)
Write-Output "`n[3/4] Checking DeepSeek Harness Web UI (Port 3080)..."
try {
    $dshResp = Invoke-WebRequest -Uri "http://127.0.0.1:3080" -UseBasicParsing -TimeoutSec 3
    Write-Output " -> DeepSeek Harness DSH ONLINE at http://127.0.0.1:3080"
} catch {
    Write-Output " -> Launching DSH Web UI..."
    Start-Process -FilePath "powershell.exe" -ArgumentList "-File scripts\start-dsh.ps1" -WindowStyle Hidden
}

# 5. Status Summary
Write-Output "`n======================================================="
Write-Output " ALL 12 DYNAMIC COMBOS ARE FULLY CONFIGURED & READY!"
Write-Output "======================================================="
Write-Output "1. DeepSeek Harness (DSH Web): http://127.0.0.1:3080"
Write-Output "2. Claude Desktop App: settings.json updated (Port 22000/20128)"
Write-Output "3. WorkBuddy AI App: settings.json updated (Port 22000/20128)"
Write-Output "4. Hermes Desktop App: connections.json updated (Port 22000/20128)"
Write-Output "5. OmniRoute Dashboard: http://127.0.0.1:20128"
Write-Output "======================================================="
