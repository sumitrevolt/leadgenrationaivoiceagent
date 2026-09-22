# run_ship4.ps1 — stage + commit + push ADR-097 retraction (docs only)
$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\Ratanshila\Documents\leadgenrationaiagent'
Start-Transcript -Path 'ship4_run.log' -Force | Out-Null
$git = 'C:\PROGRA~1\Git\cmd\git.exe'

# 2026-09-22 (M05): AGENTS.md is the SINGLE canonical agent-instruction file.
# CLAUDE.md is now a redirect stub. Byte-equality rule retired.
if (-not (Test-Path AGENTS.md -ErrorAction SilentlyContinue)) { Write-Output 'AGENTS_MD=MISSING'; Stop-Transcript | Out-Null; exit 1 }
if ((Get-Item AGENTS.md -ErrorAction SilentlyContinue).Length -lt 1000) { Write-Output 'AGENTS_MD=TOO_LEAN'; Stop-Transcript | Out-Null; exit 1 }
Write-Output 'AGENTS_MD=CANONICAL (CLAUDE.md is a deprecated redirect stub per M05)'
& $git add -- memory/decisions.md CLAUDE.md AGENTS.md scripts/commit_msg.txt scripts/run_ship4.ps1 scripts/check_skew.sh scripts/poll097.sh scripts/deploy_adr097.sh scripts/run_deploy3.ps1

Write-Output '=== STAGED ==='
& $git diff --cached --name-only
Write-Output '=== NO CODE/TEST STAGED (docs-only proof, must be empty) ==='
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
Write-Output '=== SHIP4_DONE ==='
Stop-Transcript | Out-Null
