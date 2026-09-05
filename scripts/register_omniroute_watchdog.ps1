# register_omniroute_watchdog.ps1 — Optionally schedules omniroute_combo_watchdog.py
#
# Runs the watchdog as a one-shot every N minutes via Windows Task Scheduler —
# the same registration pattern setup_autoboot.ps1 uses. The watchdog itself
# keeps strike state in data/omniroute_combo_state.json (gitignored), so
# scheduled one-shots share one consecutive-failure counter and only alert
# after `--strikes` consecutive dead passes.
#
# OPT-IN: nothing is registered until you run this script.
#
# Usage:
#     powershell -ExecutionPolicy Bypass -File scripts\register_omniroute_watchdog.ps1
#     powershell -ExecutionPolicy Bypass -File scripts\register_omniroute_watchdog.ps1 -Minutes 5
#     powershell -ExecutionPolicy Bypass -File scripts\register_omniroute_watchdog.ps1 -Unregister

param(
    [int]$Minutes = 5,
    [switch]$Unregister
)

$ErrorActionPreference = "Continue"

$repo = "C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent"
$venvPython = Join-Path $repo ".venv\Scripts\python.exe"
$watchdog = Join-Path $repo "scripts\omniroute_combo_watchdog.py"
$taskName = "LeadGen-OmniRoute-Combo-Watchdog"

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "[OK] Unregistered scheduled task: $taskName"
    exit 0
}

if (-not (Test-Path $venvPython)) {
    Write-Output "[FAIL] venv python not found: $venvPython"
    exit 1
}
if (-not (Test-Path $watchdog)) {
    Write-Output "[FAIL] watchdog not found: $watchdog"
    exit 1
}

# NTFY_URL / NTFY_TOPIC come from the user environment at runtime; the scheduled
# task runs as the current user so those resolve. Register a one-shot every
# $Minutes minutes with indefinite repetition.
$action = New-ScheduledTaskAction -Execute $venvPython -Argument "`"$watchdog`" --quiet"
$start = (Get-Date).Date.AddMinutes(5)
if ((Get-Date) -gt $start) { $start = (Get-Date).AddMinutes(5) }
$trigger = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Minutes $Minutes)
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew -StartWhenAvailable

try {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
        -Settings $settings -Description "Ping all 14 leadsgen combos every $Minutes min; ntfy alert on dead lanes" | Out-Null
    Write-Output "[OK] Scheduled Task Registered: $taskName (every $Minutes min)"
    Write-Output "     Watchdog: $watchdog"
    Write-Output "     Alerts: gated by NTFY_URL + NTFY_TOPIC (unset = print-only, no crash)"
} catch {
    Write-Output "[WARN] Scheduled Task note: $($_.Exception.Message)"
}
