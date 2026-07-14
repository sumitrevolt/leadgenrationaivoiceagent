# run_verify.ps1 — local Definition-of-Done gate (prod_check + secrets + ruff)
# Writes verify_run.log; read the log rather than streaming (DC session drops on long output).
$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\Ratanshila\Documents\leadgenrationaiagent'
Start-Transcript -Path 'verify_run.log' -Force | Out-Null
$py = '.venv\Scripts\python.exe'

Write-Output '=== PROD_CHECK ==='
& $py scripts\prod_check.py 2>&1 | Select-Object -Last 8
Write-Output ('PRODCHECK_RC=' + $LASTEXITCODE)

Write-Output '=== SECRETS ==='
& $py scripts\check_secrets.py 2>&1 | Select-Object -Last 4
Write-Output ('SECRETS_RC=' + $LASTEXITCODE)

Write-Output '=== RUFF ==='
& $py -m ruff check app/marketing/customer_delivery.py app/agents/self_improve.py 2>&1 | Select-Object -Last 5
Write-Output ('RUFF_RC=' + $LASTEXITCODE)

Write-Output '=== DUP_DEF_GREP (no duplicate helper definitions) ==='
& 'C:\PROGRA~1\Git\usr\bin\grep.exe' -rn 'def has_paid_evidence\|def _payment_evidence' app/ 2>$null

Write-Output '=== VERIFY_DONE ==='
Stop-Transcript | Out-Null
