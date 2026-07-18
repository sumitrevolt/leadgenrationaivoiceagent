# Billing Containment Ops Plan — 2026-07-18

**Code shipped (this session):** test-store isolation + accountant-safe `void_invoice` + prospect time-budget + soft-timeout no-retry.
**Prod mutations:** NONE yet. Production stays on `1803f819` until user asks deploy/flip.

## Forensic truth (read-only, preserved in `forensics_billing_dlq.txt`)

| Number | Client | Plan | Gross | Source |
|---|---|---|---|---|
| INV/2026-27/0001 | `d79d690f61b3` (jiya makeover) | starter | ₹1,999 | REAL paying |
| INV/2026-27/0002 | `041a2fb0ca1e` | starter | ₹1,999 | launch E2E disposable |
| INV/2026-27/0003..0013 | `cli_*` (cli_9, cli_auto, cli_ob, cli_auto_ob, cli_nudge, cli_nudge_fail, cli_reset, cli_real, cli_zero, cli_voice, cli_voice2) | advanced/growth | ₹2,999–5,999 | **pytest contamination** (test_upi_payments.py fixtures, 2026-07-18 10:22:08–13 UTC on VPS) |

- FY gross contaminated: ₹63,987 · real only: ₹1,999 (Jiya).
- Root cause: tests patched `upi_payments._STORE` but NOT `gst_invoice._STORE`; `UPI_AUTO_ACTIVATE=1` + `_fire_gst_invoice` wrote to cwd `data/invoices.jsonl`.
- `UPI_AUTO_ACTIVATE=1` + `AUTO_INVOICE=1` still LIVE in prod (env).
- Disposable `041a2fb0ca1e` still `active` in Postgres clients table; UPI record `upi_2_53b383f5` status=approved.
- `dlq:dead=7` all `['prospect']` SoftTimeLimit/TimeLimit (2026-07-17); forensic dump preserved.

## Operator actions (USER must approve each — not auto-run)

### A. Flip payment review gate (immediate, no deploy) — ✅ DONE 2026-07-18 11:56 UTC

USER-approved; executed via `scripts/_tmp_flip_upi_auto_activate.sh`:
`.env` line 546 `1→0` (backup `.env.bak-upiflip-20260718_115606`), app recreated with
pinned `APP_VERSION=1803f819` + `-f docker-compose.vps.yml`. Proof: container env
`UPI_AUTO_ACTIVATE=0`, `/health` 200 `version=1803f819 environment=production`
(host + public). UPI submits now stay `pending` → admin approve required.

Rollback: `UPI_AUTO_ACTIVATE=1` + same recreate.

### B. Deploy containment code (this branch)

Deploy via `scripts/deploy_vps.sh` with `APP_VERSION=<new sha>` after commit/push. Ships:
- autouse test isolation (prevents future ledger writes)
- `POST /api/growth/revenue/invoice-void` + UI Void button
- `PROSPECT_TIME_BUDGET_S` (default 420s) + soft-timeout no-retry

### C. Void contaminated invoices (AFTER B deploy)

Admin JWT → for each of INV/0002..0013:

```bash
curl -X POST https://leadsgenai.in/api/growth/revenue/invoice-void \
  -H "Authorization: Bearer $ADMIN_JWT" -H "Content-Type: application/json" \
  -d '{"number":"INV/2026-27/0003","reason":"synthetic test data — pytest contamination 2026-07-18; never a real payment"}'
```

Or use `/app/automation` → GST Invoices → ❌ Void.
**Do NOT delete JSONL lines. Do NOT void INV/0001 (Jiya).**

Expected after voids: `stats.fy_gross_inr == 1999`, `fy_voided_count == 12`, next real invoice = `INV/2026-27/0014`.

### D. Reconcile disposable tenant

- Confirm clients_store already deleted (`scripts/_tmp_launch_cleanup.py` ran earlier).
- Postgres: deactivate/delete client+subscription for `041a2fb0ca1e` (read first; then surgical).
- Keep UPI + invoice rows as audit (void invoice per C).

### E. DLQ dead closure (AFTER B deploy + one successful prospect run)

1. Preserve already done (`forensics_billing_dlq.txt`).
2. Confirm next `prospect` run succeeds (automation_health).
3. Admin: `POST /api/growth/infra/dlq/purge?key=dead` — clears historical poison ONLY after root-cause fix is live.
4. Confirm automation health green (`dead=0`).

### F. Voice HOLD unchanged

No changes to `PLATFORM_DIAL_DAILY=0`, WhatsApp autosend, OmniRoute durability, Vobiz balance — out of this containment scope.

## Verification checklist post-ops

- [ ] `UPI_AUTO_ACTIVATE=0` in running app env
- [ ] `GET /api/growth/revenue/invoices` → Jiya live, 0002–0013 voided
- [ ] `stats.fy_gross_inr == 1999`
- [ ] Customer portal for Jiya still shows INV/0001
- [ ] `dlq:dead == 0` after purge
- [ ] Fresh prospect run `ok` + no new SoftTimeLimit in worker logs
- [ ] Local pytest no longer grows `data/invoices.jsonl` (isolation contract)
