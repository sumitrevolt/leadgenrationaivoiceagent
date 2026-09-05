$ws = New-Object -ComObject WScript.Shell
$ws.AppActivate(39104)
Write-Host "AppActivate called for PID 39104"