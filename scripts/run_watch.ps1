# run_watch.ps1 — upload watch_sweep.sh and launch it detached on the VPS
$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\Ratanshila\Documents\leadgenrationaiagent'
$ssh  = 'C:\PROGRA~1\Git\usr\bin\ssh.exe'
$key  = 'C:\Users\Ratanshila\.ssh\id_rsa'
$lf   = (Get-Content -Raw (Join-Path $repo 'scripts\watch_sweep.sh')) -replace "`r`n", "`n"
$tmp  = Join-Path $env:TEMP 'watch_lf.sh'
[System.IO.File]::WriteAllText($tmp, $lf)
Get-Content -Raw $tmp | & $ssh -i $key -o StrictHostKeyChecking=no -o ConnectTimeout=25 root@72.61.245.204 'cat > /tmp/watch_sweep.sh'
& $ssh -i $key -o StrictHostKeyChecking=no -o ConnectTimeout=25 root@72.61.245.204 'sed -i "s/\r$//" /tmp/watch_sweep.sh; setsid nohup bash /tmp/watch_sweep.sh > /tmp/watch_launch.log 2>&1 < /dev/null & sleep 2; cat /tmp/watch_launch.log' 2>&1 | Out-String
