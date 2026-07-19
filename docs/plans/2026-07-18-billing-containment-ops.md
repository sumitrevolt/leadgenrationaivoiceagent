# Billing Containment Ops Plan — 2026-07-18

**Code shipped (this session):** test-store isolation + accountant-safe `void_invoice` + prospect time-budget + soft-timeout no-retry + voice fallback hardening + CI lock pins.
**Prod:** containment + voice fixes LIVE on `f8a5f6e9` (2026-07-18 deploy). Ledger voids (C) ✅ DONE 15:16 UTC. Disposable reconcile (D) ✅ DONE 15:30 UTC. DLQ purge (E) still pending (needs one successful prospect run first).

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

### B. Deploy containment code (this branch) — ✅ DONE 2026-07-18 ~15:07 UTC

Merged PR #53 (`09e250d` containment+voice) + PR #54 (`c4faf9f` CI lock/route tests) → `main` `f8a5f6e9`.
Canonical `scripts/deploy_vps.sh` on VPS: BUILD_RC=0, UP_RC=0, `/health`=`f8a5f6e9`, all 5 app-image containers skewed-clean, smoke `/health` `/api/voice/niches` `/api/billing/plans` `/api/public/pay-info` → 200, queues `celery=0` / `dlq:failed_tasks=0` (`dlq:dead=7` preserved intentionally).

### C. Void contaminated invoices (AFTER B deploy) — ✅ DONE 2026-07-18 15:16 UTC

USER-approved ("voids chalao"); executed via `scripts/_tmp_void_invoices_c.sh` inside
`leadgen_app` (APP_VERSION `f8a5f6e9`) calling shipped `gst_invoice.void_invoice` —
same code path as the admin route, append-only markers only. Ledger backup taken
first: `data/invoices.jsonl.bak-voidC-20260718_151618` (13 lines).

Proof: all 12 (INV/0002..0013) → OK; guard check INV/0001 (Jiya, `d79d690f61b3`,
₹1,999) `voided:false`; `stats` after = `fy_gross_inr: 1999.0`,
`fy_voided_count: 12`, `fy_voided_gross_inr: 61988.0`. No JSONL line deleted.
Next real invoice = `INV/2026-27/0014`. Idempotent — re-run = `deduped:True`.

### D. Reconcile disposable tenant — ✅ DONE 2026-07-18 15:30 UTC

USER-approved ("reconcile chalao"); executed via `scripts/_tmp_reconcile_d_read.sh` /
`_read2.sh` (read-first) + `scripts/_tmp_reconcile_d_write.sh` (surgical write, operator
approval card).

- Read-first proof: clients row `041a2fb0ca1e` = "LAUNCH E2E Disposable 20260718101104"
  status=active; 1 subscription `bae85f1a…` starter/upi active; payments=0, campaigns=0;
  clients_store + customer_auth JSONL already clean (0 hits).
- Write: NO DELETE — transactional `status='cancelled'` on both rows (status columns are
  varchar), subscription `cancelled_at`/`ended_at`/`cancel_reason` set. Pre-write CSV
  backup: `/root/reconcileD_20260718_153030.csv` on VPS.
- Verify: both rows `cancelled` @15:30:31; guard check Jiya `d79d690f61b3` client+sub
  still `active`. UPI record + voided INV/0002 kept as audit (per plan).

### E. DLQ dead closure (AFTER B deploy + one successful prospect run)

1. Preserve already done (`forensics_billing_dlq.txt`).
2. Confirm next `prospect` run succeeds (automation_health).
3. Admin: `POST /api/growth/infra/dlq/purge?key=dead` — clears historical poison ONLY after root-cause fix is live.
4. Confirm automation health green (`dead=0`).

### F. Voice HOLD unchanged

No changes to `PLATFORM_DIAL_DAILY=0`, WhatsApp autosend, OmniRoute durability, Vobiz balance — out of this containment scope.

## Verification checklist post-ops

- [x] `UPI_AUTO_ACTIVATE=0` in running app env
- [x] `GET /api/growth/revenue/invoices` → Jiya live, 0002–0013 voided (verified via stats + ledger tail 15:16 UTC)
- [x] `stats.fy_gross_inr == 1999`
- [ ] Customer portal for Jiya still shows INV/0001
- [ ] `dlq:dead == 0` after purge
- [ ] Fresh prospect run `ok` + no new SoftTimeLimit in worker logs
- [ ] Local pytest no longer grows `data/invoices.jsonl` (isolation contract)
