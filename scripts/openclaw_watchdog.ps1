# OpenClaw Gateway watchdog (local desktop).
# Health-checks the loopback gateway; restarts it if dead; optional ntfy page.
# GREEN-only: this script NEVER changes OpenClaw capabilities or approval policy.
# It only answers "is the gateway process alive?" and restarts it if not.
#
# v2026-09-01: added setup-conflict detection, PID logging, and tray restart hint.

$ErrorActionPreference = "SilentlyContinue"

$Port     = 18789
$Launcher = "$env:USERPROFILE\.openclaw\gateway.cmd"
$LogDir   = "$env:USERPROFILE\.openclaw\logs"
$Log      = Join-Path $LogDir "watchdog.log"
$NtfyCfg  = "C:\oc\watchdog\ntfy.txt"   # optional: one line, full ntfy topic URL
$MaxLines = 2000

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Log([string]$msg) {
  $line = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssK") + "  " + $msg
  Add-Content -Path $Log -Value $line
}

function Trim-Log {
  if (Test-Path $Log) {
    $c = @(Get-Content $Log)
    if ($c.Count -gt $MaxLines) { $c | Select-Object -Last $MaxLines | Set-Content $Log }
  }
}

function Notify([string]$title, [string]$body) {
  if (-not (Test-Path $NtfyCfg)) { return }
  $url = (Get-Content $NtfyCfg -Raw).Trim()
  if ([string]::IsNullOrWhiteSpace($url)) { return }
  try {
    Invoke-RestMethod -Uri $url -Method Post -Body $body -TimeoutSec 10 `
      -Headers @{ "Title" = $title; "Priority" = "high"; "Tags" = "warning,openclaw" } | Out-Null
    Write-Log "ntfy sent: $title"
  } catch { Write-Log ("ntfy FAILED: " + $_.Exception.Message) }
}

function Get-PortOwner {
  # Returns the PID of the process owning the gateway port, or $null.
  $conn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($conn) { return $conn.OwningProcess } else { return $null }
}

function Test-Health {
  $listening = $null -ne (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
  if (-not $listening) { return $false }
  try {
    $r = Invoke-WebRequest -Uri ("http://127.0.0.1:" + $Port + "/") -TimeoutSec 8 -UseBasicParsing
    return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500)
  } catch {
    # auth-gated responses still prove the process is alive
    if ($_.Exception.Response) {
      $c = [int]$_.Exception.Response.StatusCode
      return ($c -eq 401 -or $c -eq 403 -or $c -eq 404)
    }
    return $false
  }
}

function Get-ProcessName([int]$pid) {
  $p = Get-Process -Id $pid -ErrorAction SilentlyContinue
  if ($p) { return $p.ProcessName } else { return "unknown" }
}

if (Test-Health) {
  $ownerPid = Get-PortOwner
  if ($ownerPid) {
    $ownerName = Get-ProcessName $ownerPid
    Write-Log "HEALTHY: gateway alive on :$Port (PID $ownerPid, process=$ownerName)"
  }
  Trim-Log
  exit 0
}

# Gateway not healthy — check if port is held by a non-gateway process (setup conflict)
$ownerPid = Get-PortOwner
if ($ownerPid) {
  $ownerName = Get-ProcessName $ownerPid
  $isNode = $ownerName -match "node|openclaw|gateway"
  if (-not $isNode) {
    Write-Log "CONFLICT: port $Port held by non-gateway process PID $ownerPid ($ownerName) — skipping restart"
    Notify "OpenClaw port conflict" "Port $Port is held by $ownerName (PID $ownerPid), not the gateway. Setup may be running. Manual check needed."
    Trim-Log
    exit 2
  }
}

Write-Log "UNHEALTHY: gateway not responding on port $Port - restarting (owner PID=$ownerPid process=$(Get-ProcessName $ownerPid))"

if (-not (Test-Path $Launcher)) {
  Write-Log "FATAL: launcher missing at $Launcher - cannot restart"
  Notify "OpenClaw DOWN" "Gateway dead and launcher missing at $Launcher. Manual fix needed."
  Trim-Log
  exit 1
}

Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "`"$Launcher`"" -WindowStyle Hidden

$ok = $false
for ($i = 0; $i -lt 12; $i++) {
  Start-Sleep -Seconds 5
  if (Test-Health) { $ok = $true; break }
}

if ($ok) {
  $newPid = Get-PortOwner
  Write-Log "RECOVERED: gateway healthy again after restart (new PID=$newPid)"
  Notify "OpenClaw recovered" "Gateway was down and has been restarted successfully on $env:COMPUTERNAME (PID $newPid)."
} else {
  Write-Log "FAILED: gateway still down 60s after restart attempt"
  Notify "OpenClaw DOWN" "Gateway restart FAILED on $env:COMPUTERNAME. Check ~/.openclaw/logs. If setup is running, wait for it to finish first."
}

Trim-Log
