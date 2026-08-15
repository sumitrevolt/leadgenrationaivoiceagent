# ACTIVE_WORK - max 3 workstreams

---

## WS-GTM1 Hot Queue → 2nd paid (CURSOR LANE B)
- **ID:** WS-GTM1
- **Business outcome:** 2nd paying Marketing customer this week via Hot Queue outreach execution
- **Current state:** LIVE on `07870e89` (re-probed 2026-08-15 14:09:45Z–14:10:20Z, uptime advanced from a fresh recreate) · `origin/main` `94ab3167` docs-only on top (not needed for runtime) · GitHub heads = `main` only · open PRs = 0 · `payments_ready=true` · `blocker_count=1` · audit `docs/gtm/REVENUE_BLOCKER_AUDIT.md`. **Technical money path = GO; REVENUE GENERATED = WAIT** until owner-confirmed UPI bank credit. Hot Queue `callflag:` from #368 is **in the live SHA**. `HQ_AUTO_CHASE` remains INERT — do not arm.
- **Next exact action:** Owner authenticated `/app/inbox` 15–30 min + UPI Bind/Re-Approve + bank confirm. No further code merge required for that path.
- **Out of scope:** Flag arm · cold WA auto · ads (see WS-REV50)

---

## WS-BUZZ Agent-chat coordination (CURSOR LANE B)
- **ID:** WS-BUZZ
- **Business outcome:** Coding tools + Boss coordinate in Buzz without ping-pong; not a 32nd STAFF
- **Current state:** Local relay LIVE `ws://127.0.0.1:3100` `/_liveness=ok` · `buzzlock handoff` shipped · `#staff-pulse` posted 31/31 (footer `@` mention bug fixed) · Boss harness **dry-run EXIT 0** (canonical `1b13cecc`) · owner one-pager `docs/gtm/BOSS_HARNESS_CANARY.md`
- **Next exact action:** Owner runs `python scripts/buzz_start_harness.py --agent Boss` then `@Boss` canary ≥600s in `#admin`. Comb only after that.
- **Out of scope:** Buzz as production control plane · agent cross-allowlist · using hub as 32nd STAFF (live env already `COORDINATION_HUB_ENABLED=1` — do not treat as control plane)

---

## WS-REV50 Product-1 → 50 paid/day capacity (90d)
- **ID:** WS-REV50
- **Business outcome:** Backend factory toward 50 new ₹1,999/mo Marketing subscribers / day (not claimed live)
- **Current state:** Plan `docs/gtm/PRODUCT1_50_PAID_DAY_90D.md` · Phase 0 via WS-GTM1 · **PR #363 LIVE on `91958c23`:** ledger-backed `paid_today` / `activations_today` / `paid_gross_today_inr` (invoice + UPI ledgers, IST day, client+day dedupe, read-only; baseline 0/0 honest). `CELERY_ONBOARD_QUEUE` UNSET/INERT · 50 fake onboard tests green · loadtest `/` 429 at 5 concurrent · heavy **0.46% CPU at 02:41Z** after kb-warmup (was 155% 01:16Z) · sheet `docs/gtm/CAPACITY_50_DAY.md` · live flag mismatches in `docs/gtm/NEXT42_EVIDENCE.md`
- **Next exact action:** After 2nd paid, owner ads/GSC. Do **not** arm onboard→heavy while kb-warmup still recurs on heavy. Owner to confirm dunning/UPI_AUTO_ACTIVATE/hub live=1.
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
