# run_ship5.ps1 — stage + commit + push canonical deploy_vps.sh
$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\Ratanshila\Documents\leadgenrationaiagent'
Start-Transcript -Path 'ship5_run.log' -Force | Out-Null
$git = 'C:\PROGRA~1\Git\cmd\git.exe'

Copy-Item -Path CLAUDE.md -Destination AGENTS.md -Force
$a = (Get-FileHash CLAUDE.md).Hash
$b = (Get-FileHash AGENTS.md).Hash
if ($a -eq $b) { Write-Output 'AGENTS_SYNC=OK' } else { Write-Output 'AGENTS_SYNC=MISMATCH'; Stop-Transcript | Out-Null; exit 1 }

& $git add -- scripts/deploy_vps.sh CLAUDE.md AGENTS.md scripts/commit_msg.txt scripts/run_ship5.ps1 scripts/deploy_all.sh scripts/run_deploy_all.ps1 scripts/poll_all.sh

Write-Output '=== STAGED ==='
& $git diff --cached --name-only
Write-Output '=== NO APP CODE STAGED (must be empty) ==='
& $git diff --cached --name-only -- app/ tests/
Write-Output '--- end ---'
& $git diff --cached --check
Write-Output ('WS_RC=' + $LASTEXITCODE)

& $git commit -F scripts/commit_msg.txt
Write-Output ('COMMIT_RC=' + $LASTEXITCODE)
& $git rev-parse --short HEAD

& $git push origin main 2>&1 | Out-String
Write-Output ('PUSH_RC=' + $LASTEXITCODE)
& $git fetch origin main 2>&1 | Out-Null
Write-Output ('LOCAL =' + (& $git rev-parse --short HEAD))
Write-Output ('REMOTE=' + (& $git rev-parse --short origin/main))
Write-Output '=== SHIP5_DONE ==='
Stop-Transcript | Out-Null
