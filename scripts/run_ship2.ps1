# run_ship2.ps1 — stage + commit + push ADR-096 (explicit paths only, never add -A)
$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\Ratanshila\Documents\leadgenrationaiagent'
Start-Transcript -Path 'ship2_run.log' -Force | Out-Null
$git = 'C:\PROGRA~1\Git\cmd\git.exe'

# 2026-09-22 (M05): AGENTS.md is the SINGLE canonical agent-instruction file.
# CLAUDE.md is now a redirect stub. Byte-equality rule retired.
if (-not (Test-Path AGENTS.md -ErrorAction SilentlyContinue)) { Write-Output 'AGENTS_MD=MISSING'; Stop-Transcript | Out-Null; exit 1 }
if ((Get-Item AGENTS.md -ErrorAction SilentlyContinue).Length -lt 1000) { Write-Output 'AGENTS_MD=TOO_LEAN'; Stop-Transcript | Out-Null; exit 1 }
Write-Output 'AGENTS_MD=CANONICAL (CLAUDE.md is a deprecated redirect stub per M05)'
& $git add -- `
  app/integrations/whatsapp_selfhost.py `
  app/platform/infra_handler.py `
  tests/test_whatsapp_selfhost.py `
  memory/decisions.md `
  CLAUDE.md `
  AGENTS.md `
  scripts/commit_msg.txt `
  scripts/run_commit.ps1 `
  scripts/run_ship2.ps1 `
  scripts/deploy_adr095.sh `
  scripts/deploy_launch.sh `
  scripts/deploy_poll.sh `
  scripts/deploy_status.sh `
  scripts/run_deploy_detached.ps1 `
  scripts/verify_adr095.sh `
  scripts/verify_isolation.sh `
  scripts/verify_jiya.sh `
  scripts/verify_integ.sh `
  scripts/verify_whatsapp.sh

Write-Output '=== STAGED ==='
& $git diff --cached --name-only

Write-Output '=== EXCLUSION PROOF (must be empty) ==='
& $git diff --cached --name-only -- data/ scripts/activate_waha_vps.sh tests/test_signup_auto_login_signal.py tests/test_telecaller_brain.py
Write-Output '--- end ---'

Write-Output '=== WS CHECK ==='
& $git diff --cached --check
Write-Output ('WS_RC=' + $LASTEXITCODE)

& $git commit -F scripts/commit_msg.txt
Write-Output ('COMMIT_RC=' + $LASTEXITCODE)
& $git rev-parse HEAD

& $git push origin main 2>&1 | Out-String
Write-Output ('PUSH_RC=' + $LASTEXITCODE)
& $git fetch origin main 2>&1 | Out-Null
Write-Output ('LOCAL =' + (& $git rev-parse HEAD))
Write-Output ('REMOTE=' + (& $git rev-parse origin/main))
Write-Output '=== SHIP2_DONE ==='
Stop-Transcript | Out-Null
