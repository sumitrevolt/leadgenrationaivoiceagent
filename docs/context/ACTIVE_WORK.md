# ACTIVE_WORK - max 3 workstreams

---

## WS-GTM1 Hot Queue → 2nd paid (CURSOR LANE B)
- **ID:** WS-GTM1
- **Business outcome:** 2nd paying Marketing customer this week via Hot Queue outreach execution
- **Current state:** LIVE on `91958c23` · inbox shell 200 · named blocker `upi_pending_unactioned` · `paid_today=0` honest empty day · T31 ntfy+UPI actionable True in running app · one-pager `docs/gtm/HOT_QUEUE_BLITZ_CHECKLIST.md` · READY board `docs/gtm/NEXT_TODOS.md` §6
- **Next exact action:** Owner authenticated `/app/inbox` 15–30 min + UPI Bind/Re-Approve + bank confirm
- **Out of scope:** Flag arm · cold WA auto · ads (see WS-REV50)

---

## WS-BUZZ Agent-chat coordination (CURSOR LANE B)
- **ID:** WS-BUZZ
- **Business outcome:** Coding tools + Boss coordinate in Buzz without ping-pong; not a 32nd STAFF
- **Current state:** Local relay LIVE `ws://127.0.0.1:3100` `/_liveness=ok` · `buzzlock handoff` shipped · `#staff-pulse` posted 31/31 (footer `@` mention bug fixed) · Boss harness **dry-run EXIT 0** (canonical `1b13cecc`) · owner one-pager `docs/gtm/BOSS_HARNESS_CANARY.md`
- **Next exact action:** Owner runs `python scripts/buzz_start_harness.py --agent Boss` then `@Boss` canary ≥600s in `#admin`. Comb only after that.
- **Out of scope:** Buzz as production control plane · agent cross-allowlist · using hub as 32nd STAFF (live env already `COORDINATION_HUB_ENABLED=1` — do not treat as control plane)

---

## WS-REV50 Product-1 → 50 paid/day capacity
- **ID:** WS-REV50
- **Business outcome:** Backend factory toward 50 new ₹1,999/mo / day (not claimed live)
- **Current state:** `CELERY_ONBOARD_QUEUE` UNSET · 50 fake onboard tests green · loadtest `/` 429 at 5 concurrent · heavy **0.46% CPU at 02:41Z** after kb-warmup (was 155% 01:16Z) · jobs `self_improve_tick` / `run_staff_job` / FastEmbed warmup · sheet `docs/gtm/CAPACITY_50_DAY.md` · live flag mismatches documented in `docs/gtm/NEXT42_EVIDENCE.md`
- **Next exact action:** After 2nd paid, owner ads/GSC. Do **not** arm onboard→heavy while kb-warmup still recurs on heavy. Owner to confirm dunning/UPI_AUTO_ACTIVATE/hub live=1.
- **Out of scope:** Claiming 50/day live · paid LLM · raising WEB_CONCURRENCY off 429s

---

## Parked (not in active 3)
- **WS-SEC** Constraints inside all three (voice FROZEN, DND/TRAI/DPDP fail-closed). Not a 4th stream.
- **WS-DSH** Armed ADR-183; retirement still blocked.
- **WS-DSH180** HARNESS_SESSION_EVENTS UNSET — do not arm
- **WS-AMAX** Docs said dunning OFF; live `DUNNING_ENGINE=1` — observe, do not flip from this stream
- **WS-GOV** Boss governance flag OFF
- Creative OS · Swara/voice (FROZEN) · Stage B AMBER OpenClaw
