# ACTIVE_WORK - max 3 workstreams

---

## WS-SEC1 Vobiz credential rotation (OWNER BLOCKER)
- **ID:** WS-SEC1
- **Business outcome:** Rotate leaked `VOBIZ_AUTH_TOKEN` + `VOBIZ_SIP_PASS` (2026-08-07 settings-dump)
- **Current state:** `/root/rotate_vobiz.sh` ready (mode 700); `/root/vobiz_new.env` **missing**. Prod `/health`=`d1b106b2` (2026-08-10 probe).
- **Next exact action:** Owner → Vobiz Console new token+SIP → `/root/vobiz_new.env` (0600) → Cursor `bash /root/rotate_vobiz.sh` → portal **revoke old**
- **Out of scope:** API half-rotate with leaked token · chat secrets · Postgres tonight · hangup GET “fix”

---

## WS-LAUNCH1 Launch+revenue+automation certification (CURSOR)
- **ID:** WS-LAUNCH1
- **Business outcome:** Evidence-backed GO/WAIT for Marketing launch / revenue / automation / architecture; safe source fixes only
- **Current state:** Worktree `C:\Users\Ratanshila\Documents\leadgen-launch-ready-20260810` · branch `cursor/launch-revenue-automation-ready-20260810` · Draft PR **#305** (`fe8eb9fe`) · Graphify refreshed on `64bbe869` · product-truth Advanced rename + REPLY_AUTO_SEND `effective_on` shipped in PR · issues #304/#306/#307 opened · deploy WAIT
- **Next exact action:** CI green → ready-for-review → normal merge #305 → owner Hot Queue / 2nd UPI (WS-GTM1) · no deploy until owner says
- **Out of scope:** Production deploy · `.env`/runtime flag flips · real outbound · Swara/voice edits · force-push

---

## WS-GTM1 Hot Queue → 2nd paid - REVENUE PENDING
- **ID:** WS-GTM1
- **Current state:** HQ empty / owner prospect pick; activation summary `ready_for_first_paid_customer:true` but **revenue-generated = WAIT** without owner-confirmed UPI ledger for customer #2
- **Next exact action:** Real ₹1999 UPI → owner confirm → LEDGER_PAID
- **Out of scope:** fake PAID · auto-activate outside allowlist

---

## Parked (not in active 3)
- **WS-MORNING** B1 D2 + B2 CRM — time-gated; park until owner reopens
- **WS-DV1** Daily video — CODE READY on prod `d1b106b2`; owner flags still pending (`DAILY_VIDEO_*` unset = INERT)
- CP-A3 Postgres rotate · CP-A4 DATABASE_URL split · D3 cursor · LOOKUPS owner decision · trainer DLQ · `@example.com` domain-suffix
- WS-AM1 Safe Pack (after LEDGER_PAID)
- Estique `removed`
- **ADR-172 Agent Teams C1 — canary needs RE-BASELINE.**
- **ADR-173 claw-orchestrator** — REJECT full vendor; patterns-only.
- **ADR-174 candidate (parked)** — Cloudflare OS vendor REJECT · Gatekeeper deferred-approval + capability-intro patterns.
