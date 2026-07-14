# run_deploy_detached.ps1 — upload deploy script (LF) then launch it detached on the VPS
$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\Ratanshila\Documents\leadgenrationaiagent'
$ssh  = 'C:\PROGRA~1\Git\usr\bin\ssh.exe'
$key  = 'C:\Users\Ratanshila\.ssh\id_rsa'

function Send-Lf($localPath, $remotePath) {
  $lf  = (Get-Content -Raw (Join-Path $repo $localPath)) -replace "`r`n", "`n"
  $tmp = Join-Path $env:TEMP 'send_lf.sh'
  [System.IO.File]::WriteAllText($tmp, $lf)
  Get-Content -Raw $tmp | & $ssh -i $key -o StrictHostKeyChecking=no -o ConnectTimeout=25 root@72.61.245.204 "cat > $remotePath"
}

Send-Lf 'scripts\deploy_adr095.sh' '/tmp/deploy_adr095.sh'
Send-Lf 'scripts\deploy_launch.sh' '/tmp/deploy_launch.sh'
Get-Content -Raw (Join-Path $env:TEMP 'send_lf.sh') | Out-Null

& $ssh -i $key -o StrictHostKeyChecking=no -o ConnectTimeout=25 root@72.61.245.204 'sed -i "s/\r$//" /tmp/deploy_launch.sh; bash /tmp/deploy_launch.sh' 2>&1 | Out-String
