# ACTIVE_WORK - max 3 workstreams

---

## WS-GTM1 Hot Queue → 2nd paid (REVISED 2026-08-19)
- **ID:** WS-GTM1
- **Business outcome:** 2nd paying Marketing customer this week via Hot Queue outreach execution
- **Current state:** Prod `28ba5d4e` (DIRECT_HOST_VERIFIED 2026-08-19 13:23Z). `blocker_count=0` · `ready_for_first_paid_customer=true` · `payments_ready=true`. Technical money path = GO. REVENUE GENERATED = WAIT (owner-confirmed UPI bank credit required). SESSION_HANDOFF 2026-08-17 claimed 2nd paid via synthetic Test Hotel Spa bind — UNVERIFIED from this session.
- **Next exact action:** Owner authenticated `/app/inbox` 15–30 min + UPI Bind/Re-Approve + bank confirm.
- **Out of scope:** Flag arm · cold WA auto · ads (see WS-REV50)

---

## WS-BUZZ Agent-chat coordination (CURSOR LANE B)
- **ID:** WS-BUZZ
- **Business outcome:** Coding tools + Boss coordinate in Buzz without ping-pong; not a 32nd STAFF
- **Current state:** Local relay LIVE `http://127.0.0.1:3100/_liveness=ok` (2026-08-16 re-probe). OmniRoute `:20128` timeout this machine. Boss harness **dry-run ≠ LIVE**. Canonical Boss still `1b13cecc`. Comb gated until correlated `#admin` canary ≥600s.
- **Next exact action:** Owner runs `python scripts/buzz_start_harness.py --agent Boss` then `@Boss` canary ≥600s in `#admin`. Comb only after that.
- **Out of scope:** Buzz as production control plane · agent cross-allowlist · using hub as 32nd STAFF (live env already `COORDINATION_HUB_ENABLED=1` — do not treat as control plane)

---

## WS-REV50 Product-1 → 50 paid/day capacity (90d)
- **ID:** WS-REV50
- **Business outcome:** Backend factory toward 50 new ₹1,999/mo Marketing subscribers / day (not claimed live)
- **Current state:** Plan `docs/gtm/PRODUCT1_50_PAID_DAY_90D.md`. Ledger KPIs exist on live `520e90eb` ancestry. Uncommitted Cursor stack: ratchet+inert flags + admin marketing ledger tiles (review requests / drip sent-opened / forms / proposals / reminders / health at-risk) on `/api/growth/overview/today`. `CELERY_ONBOARD_QUEUE` UNSET/INERT. Do **not** claim 50/day live. Do **not** arm onboard→heavy or builder flags. Do **not** treat tile zeros as live automation.
- **Next exact action:** Owner 2nd paid via WS-GTM1. Then ads/GSC. Keep onboard queue INERT. Optional later: AUTH-DEPLOY this uncommitted slice after Owner ask. Customer forms/proposals pages = parked until Owner picks that slice.
- **Out of scope:** Claiming 50/day live · paid LLM · raising WEB_CONCURRENCY off 429s · Stripe/Razorpay return · inventing metrics

---

## Parked (not in active 3)
- **WS-SEC** Constraints inside all three (voice FROZEN, DND/TRAI/DPDP fail-closed; DSH kill = `DSH_RUNTIME_ENABLED=0`). Not a 4th stream. Kill fence practiced on PR #363 deploy (VLK TRUE mid-deploy, back to 0).
- **WS-DSH** Armed ADR-183 on `c4fc0087` ancestry; retirement still blocked.
- **WS-UPI304** Guest bind CODE-LIVE + approved-unactivated stays in admin queue on `c4fc0087`
- **WS-HYG** COMPLETE in ancestry
- **WS-DSH180** HARNESS_SESSION_EVENTS UNSET — do not arm with AGENT_HARNESS
- **WS-AMAX** Docs said dunning OFF; live `DUNNING_ENGINE=1` — observe, do not flip from this stream
- **WS-GOV** Boss governance flag OFF
- **WS-DEP329** Rollback retention lineage
- **WS-REV** #306 after #304 live proof
- **WS-SEC1** Vobiz rotation
- Creative OS · Swara/voice (FROZEN) · Stage B AMBER OpenClaw
