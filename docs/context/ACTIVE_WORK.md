# ACTIVE_WORK - max 3 workstreams

---

## WS-BP3 Blueprint ship - MERGE+DEPLOY IN FLIGHT
- **ID:** WS-BP3
- **Business outcome:** Runtime/health honesty + typed flags + scheduler parity + Hot Queue SLA truth on prod
- **Current state:** PR #231 ship unit (blueprint + docs-ops merge); CI fix for inquiry-bridge day idempotency
- **Next exact action:** CI green → merge #231 → `deploy_vps.sh <main-sha>` → prove `/health.version`
- **Out of scope:** mass flag enable · fabricate Estique PAID · Dependabot mega-bumps

---

## WS-R1 Autopilot refill - ARMED LIVE
- **ID:** WS-R1
- **Business outcome:** Autopilot not idle-only; scored Maps prospects enter store + capped email
- **Current state:** `SALES_AUTOPILOT_REFILL=1` armed; email ON; **cold WA OFF**
- **Next exact action:** Observe hourly email outreach
- **Out of scope:** cold WhatsApp blast

---

## WS-R3 Pay-truth / Estique - FREE TRIAL (not paid)
- **ID:** WS-R3
- **Business outcome:** Ledger-proven 2nd paid customer
- **Current state:** Trial only; `payment_verified=false`
- **Next exact action:** Owner real ₹1999 → PAID
- **Out of scope:** mark-paid without ledger

---

## Closed / parked (not counting toward 3)
- **Buzz Admin Plane** — COMPLETE. Detail: `docs/integrations/BUZZ_ADMIN_PLANE.md`
- **WS-R4 Post-call WA** — armed live (`WHATSAPP_AUTO_SEND` / `POST_CALL_WHATSAPP` / `VOICE_CLOSE_WHATSAPP`); observe only
