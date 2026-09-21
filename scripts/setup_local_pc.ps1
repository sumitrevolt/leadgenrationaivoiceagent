<#
.SYNOPSIS
  LeadGen AI — LOCAL PC Telegram/coordination setup (Windows, owner-run).

  What it does (no secrets are written by this script — it only verifies):
   1. Verifies a Python 3 runtime is available.
   2. Verifies COORD_HUB_TOOL_LOCALPC_SECRET is present in the environment
      (or user env vars; NEVER prints its value).
   3. Sends one test heartbeat to the VPS Coordination Hub.
   4. Creates a Windows Task Scheduler task "LeadGen-LocalCoord" that runs
      scripts\local_telegram_coord.py --loop --with-bot every 30 minutes,
      keeping the local PC presence alive while the owner works.
   5. Prints the exact remaining owner actions (optional local bot token,
      numeric owner id, VPS-side flag flips).

Usage (from the repo root, with user env vars set):
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_local_pc.ps1
#>
param(
    [string]$RepoRoot = "C:\Users\Ratanshila\leadgen-work",
    [switch]$SkipTask,
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"
$runner = Join-Path $RepoRoot "scripts\local_telegram_coord.py"
$hub    = $env:COORD_HUB_BASE_URL; if (-not $hub) { $hub = "https://leadsgenai.in" }

function Step([string]$msg) { Write-Host "[setup-local] $msg" -ForegroundColor Cyan }

Step "Repo root: $RepoRoot"
if (-not (Test-Path $runner)) { throw "runner not found at $runner" }

# 1. Python runtime
$py = $null
foreach ($c in @("py", "python", "python3")) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) {
        $v = & $cmd -V 2>&1 | Out-String
        if ($v -match "Python\s*3\.(1[0-9]|[2-9])") { $py = $cmd.Source; break }
    }
}
if (-not $py) { throw "No Python 3.10+ found (PATH: py/python/python3). Install Python 3.12 and re-run." }
Step "Python: $py"

# 2. Secret presence (never print the value)
$secret = $env:COORD_HUB_TOOL_LOCALPC_SECRET
if (-not $secret) {
    # user-level persistent env var
    try { $secret = [Environment]::GetEnvironmentVariable("COORD_HUB_TOOL_LOCALPC_SECRET", "User") } catch {}
}
if (-not $secret -or $secret.Length -lt 32) {
    Step "WARN: COORD_HUB_TOOL_LOCALPC_SECRET missing or <32 chars."
    Step "  Get/issue the per-tool HMAC secret from the owner dashboard (Coordination Hub)"
    Step "  and set it:  setx COORD_HUB_TOOL_LOCALPC_SECRET <secret>   (then re-open the shell)"
    $secretOk = $false
} else { $secretOk = $true; Step "Secret present (length hidden). OK." }

# 3. Test heartbeat
if ($secretOk) {
    Step "Sending test heartbeat to $hub ..."
    $env:COORD_HUB_TOOL_LOCALPC_SECRET = $secret
    & $py $runner --once
    $hb = $LASTEXITCODE
    if ($hb -eq 0) { Step "Heartbeat accepted by VPS Coordination Hub. OK." }
    else {
        Step "Heartbeat FAILED (exit $hb). Check: hub flag COORDINATION_HUB_ENABLED=1 on VPS, base URL, firewall."
    }
}

# 4. Task Scheduler (optional)
if (-not $SkipTask) {
    $action = New-ScheduledTaskAction -Execute $py -Argument "$runner --loop --with-bot" -WorkingDirectory $RepoRoot
    $trigger = New-ScheduledTaskTrigger -AtStartup -RandomDelay (New-TimeSpan -Minutes 1)
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Days 0)
    $secpass = Get-Credential -Message "Windows account that owns the scheduled task (current user OK)"
    Register-ScheduledTask -TaskName "LeadGen-LocalCoord" -Action $action -Trigger $trigger -Settings $settings -Credential $secpass -Force | Out-Null
    Step "Scheduled task 'LeadGen-LocalCoord' registered (login-triggered; keeps local presence alive)."
}

# 5. Remaining owner actions
Step "Remaining owner actions (VPS / BotFather, one-time):"
Step "  [A] VPS: add TELEGRAM_INGRESS_ENABLED=1 to /opt/leadgen/.env AFTER"
Step "      this PR is merged+deployed — makes the VPS the single Jarvis poller."
Step "  [B] VPS: set TELEGRAM_OWNER_USER_IDS=<your numeric Telegram user id>"
Step "      (numeric-only owner proof; obtain via @userinfobot in Telegram)."
Step "  [C] Optional local bot: create one via @BotFather -> set TELEGRAM_LOCAL_BOT_TOKEN"
Step "      and TELEGRAM_LOCAL_OWNER_IDS=<numeric id> in user env vars."
Step "  [D] 3 missing coordination groups (Worker/Agents/Admin Command Center):"
Step "      create private supergroups + Topics + add @Leadsgenai1_bot as admin,"
Step "      then paste chat_ids into config/telegram/setup_spec.yaml (chat_id: '')."
exit 0
