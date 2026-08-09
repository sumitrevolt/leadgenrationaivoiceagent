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

## WS-VERIFY Automation ladder CP0–CP8
- **ID:** WS-VERIFY
- **Business outcome:** Gated inventory + verify-only automation coverage; CP8 only for proven FAILs
- **Current state:** Peer review **CLEAR** on `fix/reply-auto-send-interaction-log` (`7d3b1448`+`72d772be`). Merge-ready; **WI-CP2 stays CLAIMED** until deploy + prod `interactions` out+`source=reply_agent`. B+C UNPROVEN. Sequence: **D2/CRM before** this PR (revenue + wall-clock).
- **Next exact action:** Hold merge until morning O2/B1 + O3/B2 (or owner says merge now). Owner: Vobiz portal. No deploy of WI-CP2 ahead of D2/CRM without haan.
- **Out of scope:** full-repo rewrite · Swara/voice edits · bundling D3/LOOKUPS/trainer/example.com into one PR

---

## Parked
- CP-A3 Postgres rotate · CP-A4 DATABASE_URL split · D3 cursor · LOOKUPS owner decision · trainer DLQ · `@example.com` domain-suffix
