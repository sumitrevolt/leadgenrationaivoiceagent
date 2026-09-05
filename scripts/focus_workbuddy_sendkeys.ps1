# focus_workbuddy_sendkeys.ps1 — Bring WorkBuddy AI to active desktop focus and SendKeys

Add-Type -AssemblyName Microsoft.VisualBasic
Add-Type -AssemblyName System.Windows.Forms

$wshell = New-Object -ComObject WScript.Shell

# 1. Activate WorkBuddy window
$activated = $wshell.AppActivate("WorkBuddy")
if (-not $activated) {
    $activated = $wshell.AppActivate("Design multi-platform")
}
if (-not $activated) {
    $activated = $wshell.AppActivate("WorkBuddyAI")
}

Write-Output "WorkBuddy AppActivate Status: $activated"
Start-Sleep -Milliseconds 600

# 2. Set Clipboard Text
$taskText = "Haan, SDXL (AI Image generation) ka setup shuru karo for automated video thumbnails and visual content assets. Free local stack follow karo."
Set-Clipboard -Value $taskText
Write-Output "Clipboard set."

# 3. Send Ctrl+V and Enter
$wshell.SendKeys("^v")
Start-Sleep -Milliseconds 500
$wshell.SendKeys("~")  # ~ is Enter in SendKeys
Write-Output "Sent Ctrl+V and Enter into WorkBuddy AI."
