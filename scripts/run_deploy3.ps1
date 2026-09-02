# run_deploy3.ps1 — upload + launch ADR-097 deploy detached
$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\Ratanshila\Documents\leadgenrationaiagent'
$ssh  = 'C:\PROGRA~1\Git\usr\bin\ssh.exe'
$key  = 'C:\Users\Ratanshila\.ssh\id_rsa'
$lf   = (Get-Content -Raw (Join-Path $repo 'scripts\deploy_adr097.sh')) -replace "`r`n", "`n"
$tmp  = Join-Path $env:TEMP 'dep3_lf.sh'
[System.IO.File]::WriteAllText($tmp, $lf)
Get-Content -Raw $tmp | & $ssh -i $key -o StrictHostKeyChecking=no -o ConnectTimeout=25 root@72.61.245.204 'cat > /tmp/deploy_adr097.sh'
& $ssh -i $key -o StrictHostKeyChecking=no -o ConnectTimeout=25 root@72.61.245.204 'sed -i "s/\r$//" /tmp/deploy_adr097.sh; rm -f /tmp/adr097_run.log; setsid nohup bash /tmp/deploy_adr097.sh > /tmp/adr097_run.log 2>&1 < /dev/null & sleep 2; echo LAUNCHED' 2>&1 | Out-String
