# NEXT todos READY — 2026-08-15T02:42Z (CURSOR)

Prod `/health` = `91958c23` · `healthy` · `production`. Dual probe (not cache): `02:37:40Z` uptime `4h 53m 14s` → `02:40:09Z` uptime `4h 55m 43s`.
Public activation: `payments_ready=true` · `blocker_count=1` · `ready_for_first_paid_customer=false`. Named blocker (SSH): **`upi_pending_unactioned`**. Ledger `paid_today=0` / `activations_today=0` IST 2026-08-15.
Inbox/admin/login HTTP **200**. Shell ≠ authenticated cards.

DSH used (this repo's governed runtime, **not** Harness.io): supply-chain verify EXIT 0; local Linux `dsh_runtime_smoke.py --image leadgen-dsh:smoke-a` **DSH_RUNTIME_SMOKE_OK** shutdown=0.719s cancel=3.875s; `scripts/dsh_next_todos_plan.py` Kavya MCP heartbeat + `gtm_ops_ready` + UPI proposal **403**. No `*` allowlist, no swara/ananya, no prod enqueue, no flag arm, no deploy.

| Todo | Status | Evidence |
|---|---|---|
| 1 Hot Queue blitz | OWNER-WAIT | [HOT_QUEUE_BLITZ_CHECKLIST.md](HOT_QUEUE_BLITZ_CHECKLIST.md) token-paste one-pager |
| 2 UPI Bind → Re-Approve | OWNER-WAIT | `/app/admin#sec-upi-selfserve` |
| 3 Bank-credit confirm | OWNER-WAIT | `owner_confirmed_upi`; do not fake paid |
| 4 Phase 0 exit | GATED | Jiya only |
| 5 Boss canary | OWNER-WAIT | `--dry-run` EXIT 0; [BOSS_HARNESS_CANARY.md](BOSS_HARNESS_CANARY.md) |
| 6 Comb Save | GATED | after Boss reply |
| 7 Flag mismatches | OWNER-WAIT | hub/dunning/UPI_AUTO/DSH_RUNTIME=1 observed |
| 8 Stay behind origin | READY | fetch done; no reset --hard |
| 9 Empty-cards debug | GATED | no owner paste |
| 10 2nd-tenant onboard | GATED | after 2nd paid |
| 11 Heavy jobs | READY | `self_improve_tick`, `run_staff_job`, kb-warmup ~96s; no DLQ flush |
| 12–17 Phase 1 | GATED | [PHASE1_GATED_RUNBOOK.md](PHASE1_GATED_RUNBOOK.md) |

Owner clicks (order): `/app/admin-login` → `/app/inbox` 15–30 min → UPI Bind/Approve → bank confirm → optional `python scripts/buzz_start_harness.py --agent Boss`.

One-command refresh: `.venv\Scripts\python.exe scripts\next_todos_ready.py --write`
