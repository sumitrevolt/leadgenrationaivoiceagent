$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\Ratanshila\Documents\leadgenrationaiagent'
Start-Transcript -Path 'ship8_run.log' -Force | Out-Null
$git = 'C:\PROGRA~1\Git\cmd\git.exe'
Copy-Item -Path CLAUDE.md -Destination AGENTS.md -Force
$a = (Get-FileHash CLAUDE.md).Hash; $b = (Get-FileHash AGENTS.md).Hash
if ($a -eq $b) { Write-Output 'AGENTS_SYNC=OK' } else { Write-Output 'AGENTS_SYNC=MISMATCH'; Stop-Transcript | Out-Null; exit 1 }
& $git add -- app/social_engine/engine.py tests/test_social_dry_run_visibility.py memory/decisions.md CLAUDE.md AGENTS.md scripts/commit_msg.txt scripts/run_ship8.ps1 scripts/check_posting.sh scripts/check_social_engine.sh scripts/check_providers.sh scripts/fix_dry_run.sh
Write-Output '=== STAGED ==='
& $git diff --cached --name-only
Write-Output '=== EXCLUSION PROOF (data/ must be empty) ==='
& $git diff --cached --name-only -- data/
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
Stop-Transcript | Out-Null
