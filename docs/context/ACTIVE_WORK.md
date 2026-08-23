# ACTIVE_WORK - max 3 workstreams

---

## WS-GTM1 Hot Queue → 2nd paid (REVISED 2026-08-20)
- **ID:** WS-GTM1
- **Business outcome:** 2nd paying Marketing customer via Hot Queue outreach execution
- **Current state:** Prod `658fc20a` (DIRECT_HOST_VERIFIED 2026-08-20 12:58Z). `blocker_count=0` · `ready_for_first_paid_customer=true` · `payments_ready=true`. Technical money path = GO. REVENUE GENERATED = WAIT (owner-confirmed UPI bank credit required). Automation LIVE (growth/email/sales-autopilot fresh).
- **Next exact action:** Owner authenticated `/app/inbox` 15–30 min + UPI Bind/Re-Approve + bank confirm.
- **Out of scope:** Flag arm · cold WA auto · ads

---

## WS-BUZZ Agent-chat coordination (CURSOR LANE B)
- **ID:** WS-BUZZ
- **Business outcome:** Coding tools + Boss coordinate in Buzz without ping-pong; not a 32nd STAFF
- **Current state:** Local relay LIVE `http://127.0.0.1:3100/_liveness=ok` (2026-08-23 re-proved after outage: relay rides **Docker Desktop** — DD down = relay down; fix = start Docker Desktop, stack auto-starts, poll `/_liveness`). OmniRoute `:20128` timeout this machine. Boss harness **dry-run ≠ LIVE**. Canonical Boss `1b13cecc`. Comb gated until correlated `#admin` canary ≥600s.
- **Next exact action:** Owner runs `python scripts/buzz_start_harness.py --agent Boss` then `@Boss` canary ≥600s in `#admin`.
- **Out of scope:** Buzz as production control plane · using hub as 32nd STAFF

---

## WS-REV50 Product-1 → 50 paid/day capacity (90d)
- **ID:** WS-REV50
- **Business outcome:** Backend factory toward 50 new ₹1,999/mo Marketing subscribers / day (not claimed live)
- **Current state:** Plan `docs/gtm/PRODUCT1_50_PAID_DAY_90D.md`. Runtime flags now ON (CRM_SYNC=1, DAILY_VIDEO_CLIENTS=*, COORD_PLAN_NODE=1). Provider creds PRESENT (Zoho/HubSpot/GSC/Meta/Postiz/WAHA). GSC_ENABLED still UNSET (creds ready, flag off). Do NOT claim 50/day live. Do NOT arm onboard→heavy without measured saturation.
- **Next exact action:** Owner 2nd paid via WS-GTM1 → then flip `GSC_ENABLED=1` (creds present) + social/video publish canary.
- **Out of scope:** Claiming 50/day live · paid LLM · Stripe/Razorpay return · inventing metrics

---

## Parked (not in active 3)
- **WS-SEC** voice FROZEN, DND/TRAI/DPDP fail-closed. Kill fence practiced (VLK=0 restored).
- **WS-DSH** DSH_RUNTIME_ENABLED=0 (fail-closed); dsh-worker container running but runtime flag off.
- **WS-UPI304** Guest bind + approved-unactivated admin queue.
- **WS-AMAX** DUNNING_ENGINE=1 (observe, do not flip).
- **WS-GOV** BOSS_FULL_AUTONOMY=1 + BOSS_DECISION_GOVERNANCE=1 but agents UNARMED 30/30 (rollout held).
- Creative OS · Swara/voice (FROZEN) · Stage B AMBER OpenClaw
