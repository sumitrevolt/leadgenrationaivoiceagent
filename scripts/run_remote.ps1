# run_remote.ps1 — ship a local .sh to the VPS with LF endings and run it.
# Usage: powershell -File scripts\run_remote.ps1 -Script scripts\launch_probe3.sh
param([Parameter(Mandatory=$true)][string]$Script)
$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\Ratanshila\Documents\leadgenrationaiagent'
$src  = if ([System.IO.Path]::IsPathRooted($Script)) { $Script } else { Join-Path $repo $Script }
$lf   = (Get-Content -Raw $src) -replace "`r`n", "`n"
$tmp  = Join-Path $env:TEMP 'remote_lf.sh'
[System.IO.File]::WriteAllText($tmp, $lf)
$ssh  = 'C:\PROGRA~1\Git\usr\bin\ssh.exe'
Get-Content -Raw $tmp | & $ssh -i C:\Users\Ratanshila\.ssh\id_rsa -o StrictHostKeyChecking=no -o ConnectTimeout=25 root@72.61.245.204 'cat > /tmp/remote.sh; bash /tmp/remote.sh' 2>&1 | Out-String
