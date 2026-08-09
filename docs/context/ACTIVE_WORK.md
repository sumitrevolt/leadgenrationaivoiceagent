# ACTIVE_WORK - max 3 workstreams

---

## WS-SEC1 Vobiz credential rotation (OWNER BLOCKER)
- **ID:** WS-SEC1
- **Business outcome:** Rotate leaked `VOBIZ_AUTH_TOKEN` + `VOBIZ_SIP_PASS` (2026-08-07 settings-dump)
- **Current state:** `/root/rotate_vobiz.sh` ready (mode 700); `/root/vobiz_new.env` **missing**. Prod `a08dd5e9`. main `34836739` (#275) not required for rotate.
- **Next exact action:** Owner → Vobiz Console new token+SIP → `/root/vobiz_new.env` (0600) → Cursor `bash /root/rotate_vobiz.sh` → portal **revoke old**
- **Out of scope:** API half-rotate with leaked token · chat secrets · Postgres tonight · hangup GET “fix”

---

## WS-MORNING B1 D2 + B2 CRM (time-gated)
- **ID:** WS-MORNING
- **Business outcome:** Numbered PRODUCTION verdicts for D2 harvest budget + CRM lead sync
- **Current state:** D2 code LIVE on `a08dd5e9`; cron `03:48Z`/`03:50Z` armed. CRM flag ON; no answered-call proof yet. Midday 163 leads = **D1 only**.
- **Next exact action:** After 04:00Z/06:00Z `prospect` → read `/root/d2_morning_<date>.log` (B1 table). After ~11:30 dial → CRM prove only if answered (B2). Write verdicts into SESSION_HANDOFF + AUTOMATION_VERIFY_CHECKPOINTS.md
- **Out of scope:** LOOKUPS bump · extra canary dials tonight · declaring B13 broken on no-answer

---

## WS-DV1 Daily video producer - CODE READY, OWNER FLAGS PENDING
- **ID:** WS-DV1
- **Business outcome:** marketing customer ko ROZ 1 video (classic ab, HyperFrames-advanced toolchain deploy ke baad)
- **Current state:** **MERGED + DEPLOYED** — PR #294 → prod `/health`=`d1b106b2`, 5/5 zero skew, kill-fence closed, queues at baseline. All `DAILY_VIDEO_*` flags **unset** so the producer is INERT; deploy produced zero behaviour change by design.
- **Next exact action:** Stage 1 of `docs/runbooks/RUNBOOK_DAILY_VIDEO.md` — `DAILY_VIDEO_ENABLED=1`, `DAILY_VIDEO_CLIENTS=jiya-makeover`, `DAILY_VIDEO_ENGINE=classic`, then recreate **with `APP_VERSION=d1b106b2`**. Also clear the 32 pending reviews or the producer will (correctly) refuse that client.
- **Out of scope:** auto-publish · daily WA blast · pricing copy "daily" claim before a week of proven delivery

---

## WS-GTM1 Hot Queue → 2nd paid - REVENUE PENDING
- **ID:** WS-GTM1
- **Current state:** HQ empty; owner prospect pick
- **Next exact action:** Real ₹1999 UPI → LEDGER_PAID
- **Out of scope:** fake PAID

---

## Parked
- CP-A3 Postgres rotate · CP-A4 DATABASE_URL split · D3 cursor · LOOKUPS owner decision · trainer DLQ · `@example.com` domain-suffix
