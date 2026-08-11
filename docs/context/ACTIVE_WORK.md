# ACTIVE_WORK - max 3 workstreams

---

## WS-SEC1 Vobiz credential rotation (OWNER BLOCKER)
- **ID:** WS-SEC1
- **Business outcome:** Rotate leaked `VOBIZ_AUTH_TOKEN` + `VOBIZ_SIP_PASS` (2026-08-07 settings-dump)
- **Current state:** `/root/rotate_vobiz.sh` ready (mode 700); `/root/vobiz_new.env` **missing**. Prod SHA: re-probe `/health` (docs previously `d1b106b2` / recovery note `6052b533` — do not quote without fresh curl).
- **Next exact action:** Owner → Vobiz Console new token+SIP → `/root/vobiz_new.env` (0600) → Cursor `bash /root/rotate_vobiz.sh` → portal **revoke old**
- **Out of scope:** API half-rotate with leaked token · chat secrets · Postgres tonight · hangup GET “fix”

---

## WS-GTM1 Hot Queue → 2nd paid - REVENUE PENDING
- **ID:** WS-GTM1
- **Current state:** HQ empty / owner prospect pick; activation historically `ready_for_first_paid_customer:true` but **revenue-generated = WAIT** without owner-confirmed UPI ledger for customer #2. Guest UPI `#304` bind path **CODE-PRESENT** this session (bind API + admin UI) — not deployed.
- **Next exact action:** Real ₹1999 UPI → owner confirm → bind client if guest → LEDGER_PAID
- **Out of scope:** fake PAID · auto-activate outside allowlist

---

## WS-UPI304 Guest UPI bind (#304) - CODE READY (deploy WAIT)
- **ID:** WS-UPI304
- **Business outcome:** Approved guest UPI no longer dead-ends; owner can bind `client_id` and activate without “re-approve” fiction
- **Current state:** bind API/UI + `list_actionable` (pending + any approved-not-live: unbound legacy + failed activate) + Admin Office/digest + God Mode/Self-Serve Bind/Retry UI. Branch `cursor/split-B-buzz-local-relay-20260810`. PR #305 already MERGED.
- **Next exact action:** pytest green (shell still blocked) → owner commit/PR when asked → deploy WAIT
- **Out of scope:** deploy · `.env` flips · fake PAID

---

## Parked (not in active 3)
- **WS-LAUNCH1** — DONE merged #305 (`098c0da4`); deploy of that tip still owner-gated / may already be superseded by later deploys — re-probe `/health`
- **WS-MORNING** B1 D2 + B2 CRM — time-gated; park until owner reopens
- **WS-DV1** Daily video — CODE READY; owner flags still pending (`DAILY_VIDEO_*` unset = INERT)
- CP-A3 Postgres rotate · CP-A4 DATABASE_URL split · D3 cursor · LOOKUPS owner decision · trainer DLQ · `@example.com` domain-suffix
- WS-AM1 Safe Pack (after LEDGER_PAID)
- Estique `removed`
- **ADR-172 Agent Teams C1 — canary needs RE-BASELINE.**
- **ADR-173 claw-orchestrator** — REJECT full vendor; patterns-only.
- **ADR-174 candidate (parked)** — Cloudflare OS vendor REJECT · Gatekeeper deferred-approval + capability-intro patterns.
