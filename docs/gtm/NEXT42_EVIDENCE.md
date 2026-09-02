# Next42 execution evidence — 2026-08-15

Agent session implemented the **agent-side** of the 42-task plan. Owner-gated
clicks (inbox blitz, bank confirm, Boss Desktop spawn, Comb create, ads spend)
are recorded as remaining human work, not faked.

## Same-day probes

| Item | Result | Label |
|---|---|---|
| Prod `/health` | `91958c23` healthy production (re-probed 01:16Z, uptime 3h32m) | DIRECT_HOST_VERIFIED |
| `/api/activation/summary` | `blocker_count=1`, `payments_ready=true`, `warn_count=1` | DIRECT_HOST_VERIFIED |
| Named blocker | **`upi_pending_unactioned`** | DIRECT_HOST_VERIFIED |
| `paid_today` | 0 / 0 on IST 2026-08-15 — honest empty day | DIRECT_HOST_VERIFIED |
| T31 code locks in **running** app | `_notify_owner_once=True` · `list_actionable=True` | DIRECT_HOST_VERIFIED |
| DB path | `via_pgbouncer True` · `direct_db_5432 False` | DIRECT_HOST_VERIFIED |
| Buzz relay | `127.0.0.1:3100/_liveness` 200 `ok` | LOCAL-ONLY |
| Staff pulse | posted 31/31 to `#staff-pulse` (footer `@` tokens removed) | LOCAL-ONLY |
| `#build` HANDOFF | `buzzlock.py handoff` posted with Evidence line | LOCAL-ONLY |
| DLQ | `dlq:dead=23` trainer TimeLimitExceeded; failed_tasks now 0. Do not flush. | DIRECT_HOST_VERIFIED |
| Loadtest | `/health` 129×200; `/` 100×200 + 43×429 at 5 concurrent | DIRECT_HOST_VERIFIED |
| `/app/inbox` | HTTP 200 shell; cards need admin token | DIRECT_HOST_VERIFIED |
| PR #364 | MERGED `c35edb4d` docs-only | GIT_VERIFIED |

## T29 live flags vs intended (booleans only, prod `91958c23`)

Live `printenv` inside `leadgen_app` — **do not assume code defaults**.

| Flag | Intended (plan) | Live | Notes |
|---|---|---|---|
| AUTO_ONBOARD | observable ON ok | 1 | idempotent `setup_done` |
| SIGNUP_AUTO_ONBOARD | observable ON ok | 1 | |
| REPLY_AGENT | drafts, not auto-send | 1 | |
| JOURNEY_ENGINE | verify | 1 | |
| CADENCE_ENGINE | verify | 1 | |
| SALES_ENGINE | verify | 1 | |
| OPS_WATCHDOG | verify | 1 | |
| AUTO_EMAIL_OUTREACH | cap 50/day | 1 | default cap 50 (PR #365), do not raise further |
| HOT_QUEUE_BRIEF_DAILY | ntfy loop | 1 | T31 path armed |
| WEB_CONCURRENCY | 2 | 2 | do not raise |
| VOICE_LAUNCH_KILL | 0 (calling live) | 0 | voice code still FROZEN |
| SALES_AUTOPILOT_WHATSAPP_ENABLED | never-arm 0 | 0 | OK |
| GSC_ENABLED | never without creds | UNSET | OK |
| HARNESS_SESSION_EVENTS | never-arm | UNSET | OK |
| CELERY_ONBOARD_QUEUE | INERT | UNSET | OK |
| DSH_SHADOW_ENABLED | OFF | 0 | OK |
| DSH_RUNTIME_ENABLED | watch; kill=`0` | **1** | no executor delete; kill remains env |
| COORDINATION_HUB_ENABLED | stay 0 until HMAC canary | **1** | live ≠ intended; do not use as 32nd STAFF / control plane |
| DUNNING_ENGINE | never-arm | **1** | live ≠ CLAUDE.md “OFF”; do not flip from this session |
| UPI_AUTO_ACTIVATE | containment 0 | **1** | live ≠ memory; do not flip from this session |

Agent did **not** change prod `.env`. Mismatches are owner decisions.

### Re-probe 2026-08-15 02:40–02:42Z (NEXT todos READY, no flag flip)

Same SHA `91958c23`, timestamp/uptime advanced (not cache). Flag booleans **unchanged** vs table above (`capacity_baseline.py --dry-run`). `paid_today=0` / `activations_today=0`. `dlq:dead` 23→24 (do not flush). Heavy CPU 155%→0.46% after kb-warmup; still do not arm onboard. DSH local smoke OK; prod DSH queue llen=0.

## Code shipped this session

- `scripts/buzz_start_harness.py` honours `BUZZ_RELAY` (http→ws map)
- `scripts/buzzlock.py handoff` — Evidence line required
- `CELERY_ONBOARD_QUEUE` INERT → existing `heavy` worker (no orphan queue)
- `scripts/capacity_baseline.py` now keeps docker stats (no hard-coded missing `pgbouncer` name)
- Watch/load scripts under `scripts/`
- Docs: `CAPACITY_50_DAY.md`, `PHASE1_GATED_RUNBOOK.md`

## Tests

`pytest` tests/test_capacity_baseline.py tests/test_next42_plan_gates.py
tests/test_onboard_client_burst.py tests/test_buzz_start_harness.py
tests/test_celery_queue_routing.py tests/test_buzz_staff_pulse.py → EXIT 0 (42 passed).
ruff changed files clean. check_secrets OK.

## Owner remaining (not agent-completable)

1. Authenticated `/app/inbox` 15–30 min blitz (token on the page)
2. Bind/Re-Approve + bank confirm when a real UPI arrives
3. `python scripts/buzz_start_harness.py --agent Boss` (sandbox blocks agents)
4. `#admin` `@Boss` canary ≥600s after harness
5. Comb Desktop Save only after Boss replies
6. Phase 1 ads/GSC only after 2nd paid
7. Decide whether live `DUNNING_ENGINE` / `UPI_AUTO_ACTIVATE` / `COORDINATION_HUB_ENABLED` =1 should stay
