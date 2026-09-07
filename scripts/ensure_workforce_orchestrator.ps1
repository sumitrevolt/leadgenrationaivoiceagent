# ensure_workforce_orchestrator.ps1 — idempotent keepalive for the 31-agent workforce orchestrator
#
# Landmine this fixes (progress.md 2026-09-06): scripts/autonomous_workforce_orchestrator.py
# is a `while True` daemon that dies with the terminal/session that launched it, leaving
# data/workforce_live_status.json stale. This script is SAFE to run any number of times:
#   - if an orchestrator process is already running -> no-op (exit 0)
#   - if not -> start it detached (hidden, survives this console) -> exit 0
#
# Optional registration (OPT-IN, same pattern as register_omniroute_watchdog.ps1):
#   powershell -ExecutionPolicy Bypass -File scripts\ensure_workforce_orchestrator.ps1 -Register
#   powershell -ExecutionPolicy Bypass -File scripts\ensure_workforce_orchestrator.ps1 -Register -Minutes 5
#   powershell -ExecutionPolicy Bypass -File scripts\ensure_workforce_orchestrator.ps1 -Unregister
# The scheduled task re-runs this ensure script every N minutes, so the daemon
# self-heals after reboot/crash. Unregister = full rollback.

param(
    [switch]$Register,
    [switch]$Unregister,
    [int]$Minutes = 5
)

$ErrorActionPreference = "Continue"

$repo = "C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent"
$venvPython = Join-Path $repo ".venv\Scripts\python.exe"
$orchestrator = Join-Path $repo "scripts\autonomous_workforce_orchestrator.py"
$ensureScript = Join-Path $repo "scripts\ensure_workforce_orchestrator.ps1"
$stalenessScript = Join-Path $repo "scripts\workforce_staleness_watchdog.py"
$taskName = "LeadGen-Workforce-Orchestrator-Keepalive"

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "[OK] Unregistered scheduled task: $taskName"
    exit 0
}

if (-not (Test-Path $venvPython)) {
    Write-Output "[FAIL] venv python not found: $venvPython"
    exit 1
}
if (-not (Test-Path $orchestrator)) {
    Write-Output "[FAIL] orchestrator not found: $orchestrator"
    exit 1
}

if ($Register) {
    # Idempotent re-register: replace any existing task with the same name.
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ensureScript`""
    $start = (Get-Date).AddMinutes(5)
    $trigger = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Minutes $Minutes)
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
        -MultipleInstances IgnoreNew -StartWhenAvailable
    try {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
            -Settings $settings -Description "Idempotent keepalive: start 31-agent workforce orchestrator if not running" | Out-Null
        Write-Output "[OK] Scheduled Task Registered: $taskName (every $Minutes min)"
        Write-Output "     Ensure script: $ensureScript"
        Write-Output "     Rollback: powershell -File scripts\ensure_workforce_orchestrator.ps1 -Unregister"
    } catch {
        Write-Output "[WARN] Scheduled Task note: $($_.Exception.Message)"
    }
    exit 0
}

# Evidence-first liveness check: a real process whose command line targets the
# orchestrator script (matches how the prior death was diagnosed via Win32_Process).
$running = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*autonomous_workforce_orchestrator.py*" }

if ($running) {
    Write-Output "[OK] Orchestrator already running (pid $($running.ProcessId -join ',')) - no-op"
    if (Test-Path $stalenessScript) {
        & $venvPython $stalenessScript --quiet | Out-Null
        Write-Output "[OK] Staleness check complete (exit $LASTEXITCODE)"
    }
    exit 0
}

# Detached start: survives the calling console (the prior session-bound death mode).
Start-Process -FilePath $venvPython -ArgumentList "`"$orchestrator`"" `
    -WorkingDirectory $repo -WindowStyle Hidden
Write-Output "[OK] Orchestrator started detached (hidden window)"

# Progress-signal check (complements process-liveness above): catches the
# alive-but-hung case where the keepalive no-ops but no cycle is writing.
# Gated ntfy alert; exit code intentionally NOT propagated (restart already succeeded).
if (Test-Path $stalenessScript) {
    & $venvPython $stalenessScript --quiet | Out-Null
    Write-Output "[OK] Staleness check complete (exit $LASTEXITCODE)"
}
exit 0
