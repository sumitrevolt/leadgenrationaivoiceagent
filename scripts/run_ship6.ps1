# run_ship6.ps1 — stage + commit + push deploy retention
$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\Ratanshila\Documents\leadgenrationaiagent'
Start-Transcript -Path 'ship6_run.log' -Force | Out-Null
$git = 'C:\PROGRA~1\Git\cmd\git.exe'

& $git add -- scripts/deploy_vps.sh scripts/disk_plan.sh scripts/disk_reclaim.sh scripts/disk_after.sh scripts/check_resources.sh scripts/check_latest_regression.sh scripts/check_skew.sh scripts/poll_dep.sh scripts/run_deploy_canonical.ps1 scripts/run_full_tests.ps1 scripts/run_ship6.ps1 scripts/commit_msg.txt

Write-Output '=== STAGED ==='
& $git diff --cached --name-only
Write-Output '=== NO APP CODE (must be empty) ==='
& $git diff --cached --name-only -- app/ tests/
Write-Output '--- end ---'
& $git diff --cached --check
Write-Output ('WS_RC=' + $LASTEXITCODE)

& $git commit -F scripts/commit_msg.txt
Write-Output ('COMMIT_RC=' + $LASTEXITCODE)
& $git push origin main 2>&1 | Out-String
Write-Output ('PUSH_RC=' + $LASTEXITCODE)
& $git fetch origin main 2>&1 | Out-Null
Write-Output ('LOCAL =' + (& $git rev-parse --short HEAD))
Write-Output ('REMOTE=' + (& $git rev-parse --short origin/main))
Write-Output '=== SHIP6_DONE ==='
Stop-Transcript | Out-Null
