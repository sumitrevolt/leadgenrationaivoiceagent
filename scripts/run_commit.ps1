# run_commit.ps1 — commit already-staged set with -F (avoids PS quote mangling) + push
$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\Ratanshila\Documents\leadgenrationaiagent'
Start-Transcript -Path 'commit_run.log' -Force | Out-Null
$git = 'C:\PROGRA~1\Git\cmd\git.exe'

Write-Output '=== STAGED (re-confirm) ==='
& $git diff --cached --name-only

Write-Output '=== COMMIT ==='
& $git commit -F scripts/commit_msg.txt
Write-Output ('COMMIT_RC=' + $LASTEXITCODE)

Write-Output '=== NEW SHA ==='
& $git rev-parse HEAD

Write-Output '=== PUSH ==='
& $git push origin main 2>&1 | Out-String
Write-Output ('PUSH_RC=' + $LASTEXITCODE)

Write-Output '=== LOCAL vs REMOTE (must match) ==='
& $git fetch origin main 2>&1 | Out-Null
Write-Output ('LOCAL =' + (& $git rev-parse HEAD))
Write-Output ('REMOTE=' + (& $git rev-parse origin/main))
Write-Output '=== COMMIT_DONE ==='
Stop-Transcript | Out-Null
