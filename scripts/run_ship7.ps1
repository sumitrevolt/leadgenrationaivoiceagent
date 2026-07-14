$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\Ratanshila\Documents\leadgenrationaiagent'
Start-Transcript -Path 'ship7_run.log' -Force | Out-Null
$git = 'C:\PROGRA~1\Git\cmd\git.exe'
& $git add -- scripts/deploy_vps.sh scripts/incident_state.sh scripts/commit_msg.txt scripts/run_ship7.ps1
Write-Output '=== STAGED ==='
& $git diff --cached --name-only
Write-Output '=== NO APP CODE (must be empty) ==='
& $git diff --cached --name-only -- app/ tests/
Write-Output '--- end ---'
& $git commit -F scripts/commit_msg.txt
Write-Output ('COMMIT_RC=' + $LASTEXITCODE)
& $git push origin main 2>&1 | Out-String
Write-Output ('PUSH_RC=' + $LASTEXITCODE)
& $git fetch origin main 2>&1 | Out-Null
Write-Output ('LOCAL =' + (& $git rev-parse --short HEAD))
Write-Output ('REMOTE=' + (& $git rev-parse --short origin/main))
Stop-Transcript | Out-Null
