# run_ship3.ps1 — stage + commit + push ADR-097 (explicit paths only)
$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\Ratanshila\Documents\leadgenrationaiagent'
Start-Transcript -Path 'ship3_run.log' -Force | Out-Null
$git = 'C:\PROGRA~1\Git\cmd\git.exe'

Copy-Item -Path CLAUDE.md -Destination AGENTS.md -Force
$a = (Get-FileHash CLAUDE.md).Hash
$b = (Get-FileHash AGENTS.md).Hash
if ($a -eq $b) { Write-Output 'AGENTS_SYNC=OK' } else { Write-Output 'AGENTS_SYNC=MISMATCH'; Stop-Transcript | Out-Null; exit 1 }

& $git add -- `
  app/main.py `
  tests/test_image_provenance_guard.py `
  memory/decisions.md `
  CLAUDE.md `
  AGENTS.md `
  scripts/commit_msg.txt `
  scripts/run_ship3.ps1 `
  scripts/deploy_adr096.sh `
  scripts/deploy_launch2.sh `
  scripts/deploy_poll2.sh `
  scripts/deploy_poll3.sh `
  scripts/run_deploy2.ps1 `
  scripts/run_watch.ps1 `
  scripts/watch_sweep.sh `
  scripts/read_watch.sh `
  scripts/verify_voice_niches.sh `
  scripts/verify_sentry_live.sh

Write-Output '=== STAGED ==='
& $git diff --cached --name-only

Write-Output '=== EXCLUSION PROOF (must be empty) ==='
& $git diff --cached --name-only -- data/ scripts/activate_waha_vps.sh tests/test_signup_auto_login_signal.py tests/test_signup_rate_limit_ux.py tests/test_telecaller_brain.py
Write-Output '--- end ---'

Write-Output '=== WS CHECK ==='
& $git diff --cached --check
Write-Output ('WS_RC=' + $LASTEXITCODE)

& $git commit -F scripts/commit_msg.txt
Write-Output ('COMMIT_RC=' + $LASTEXITCODE)
& $git rev-parse --short HEAD

& $git push origin main 2>&1 | Out-String
Write-Output ('PUSH_RC=' + $LASTEXITCODE)
& $git fetch origin main 2>&1 | Out-Null
Write-Output ('LOCAL =' + (& $git rev-parse HEAD))
Write-Output ('REMOTE=' + (& $git rev-parse origin/main))
Write-Output '=== SHIP3_DONE ==='
Stop-Transcript | Out-Null
