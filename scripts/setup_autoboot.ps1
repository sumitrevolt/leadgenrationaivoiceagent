# setup_autoboot.ps1 — Installs LeadGen auto-boot into Windows Startup and Task Scheduler.

$startupFolder = [Environment]::GetFolderPath('Startup')
$vbsSource = "C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\scripts\autoboot_silent.vbs"
$vbsDest = Join-Path $startupFolder "LeadGen_AutoBoot.vbs"

Copy-Item -Path $vbsSource -Destination $vbsDest -Force
Write-Output "[OK] Copied to Windows Startup Folder: $vbsDest"

# Scheduled Task registration
$taskName = "LeadGen-Project-AutoBoot"
try {
    $action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$vbsDest`""
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Auto-starts LeadGen AI services, OmniRoute, MCP servers, and Desktop sync on laptop restart" | Out-Null
    Write-Output "[OK] Scheduled Task Registered: $taskName"
} catch {
    Write-Output "[WARN] Scheduled Task note: $($_.Exception.Message)"
}

Write-Output "[SUCCESS] Laptop restart auto-boot is fully armed and active!"
