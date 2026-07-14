# run_ship.ps1 — surgical stage + commit + push (ADR-095 + self_improve TTL + docs)
# NEVER `git add -A` (parallel Cursor edits share this tree). Explicit paths only.
$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\Ratanshila\Documents\leadgenrationaiagent'
Start-Transcript -Path 'ship_run.log' -Force | Out-Null
$git = 'C:\PROGRA~1\Git\cmd\git.exe'

# AGENTS.md must be a byte-copy of CLAUDE.md
Copy-Item -Path CLAUDE.md -Destination AGENTS.md -Force
$a = (Get-FileHash CLAUDE.md).Hash
$b = (Get-FileHash AGENTS.md).Hash
if ($a -eq $b) { Write-Output 'AGENTS_SYNC=OK' } else { Write-Output 'AGENTS_SYNC=MISMATCH'; Stop-Transcript | Out-Null; exit 1 }

Write-Output '=== STAGING (explicit paths only) ==='
& $git add -- `
  app/marketing/customer_delivery.py `
  tests/test_customer_delivery_2026_07_05.py `
  app/agents/self_improve.py `
  tests/test_self_improve.py `
  memory/decisions.md `
  memory/playbooks.md `
  CLAUDE.md `
  AGENTS.md `
  scripts/launch_probe.sh `
  scripts/launch_probe2.sh `
  scripts/launch_probe3.sh `
  scripts/run_remote.ps1 `
  scripts/run_verify.ps1 `
  scripts/run_ship.ps1

Write-Output '=== STAGED FILES ==='
& $git diff --cached --name-only

Write-Output '=== EXCLUSION PROOF (must be empty / unstaged) ==='
& $git diff --cached --name-only -- tests/test_signup_auto_login_signal.py tests/test_signup_rate_limit_ux.py tests/test_telecaller_brain.py scripts/activate_waha_vps.sh data/
Write-Output '--- end exclusion proof ---'

Write-Output '=== WHITESPACE CHECK ==='
& $git diff --cached --check
Write-Output ('WS_RC=' + $LASTEXITCODE)

Write-Output '=== COMMIT ==='
$msg = @'
fix(delivery): require invoice evidence for the paid dead-man alert (ADR-095)

A plan is SELECTED at signup before any money moves, so plan name alone is not
payment proof. `find_undelivered_paid_clients()` gated on `is_paid_client()`
(plan-based), so synthetic tenant "Test Biz" (1f89031d621a, plan=growth, zero
invoices) fired the founder-paging `PAID customer undelivered` alert every hour
on the hour (08:20->12:20 in data/delivery_stuck.jsonl) and wrote a
delivery_gated ledger event for a customer who never paid.

Live truth table: invoice_rows=1 client_ids=['d79d690f61b3'];
jiya-makeover plan_paid=True/has_inv=True, Test Biz plan_paid=True/has_inv=False.

- add tri-state `_payment_evidence()` (True / False / None=UNKNOWN), identity
  resolution mirrors activation._client_has_payment_evidence incl. the
  `billing_client_ids` alias that preserves a recreated client's invoice.
- add `has_paid_evidence()` = eligible AND not contradicted by a functioning
  ledger; fails OPEN on UNKNOWN so a real paying customer is never silently
  dropped from the dead-man detector (the ghosting incident this module exists
  to prevent).
- gate only the detector. Delivery-send eligibility is unchanged, keeping the
  blast radius on the alert path.
- `is_paid_client()` behaviour unchanged, now documented as ELIGIBILITY.

Also: self_improve queue TTL guard (stale pending work is skipped, never
auto-run or deleted) + its tests, and memory/doc write-back.

Tests: 72 passed (customer_delivery + self_improve + billing_truth +
customer_tenant_isolation_authenticated). prod_check ALL CHECKS PASSED
(1102 routes). check_secrets clean.
'@
& $git commit -m $msg
Write-Output ('COMMIT_RC=' + $LASTEXITCODE)

Write-Output '=== NEW SHA ==='
& $git rev-parse HEAD
Write-Output '=== SHIP_DONE ==='
Stop-Transcript | Out-Null
