# PILOT Learning Journal
(Created for Sep-11 IS-RUN cycles)

## IS-RUN Sep-11 02:32 — VCS Evidence Sweep
- Full VPS SSH evidence: call_loop DEAD 10d (mtime Aug-31, batch211 fail='from number not owned'), DID REVOKED, SIP env len=0, WAHA WORKING on 3111, auto_outreach.py 1959 lines grep=0 sendText
- Identified root cause: scheduler beat wiring stub (commit 94439e74 body), NOT field bug
- PIVOT to WAHA-only revenue rail identified

## IS-RUN Sep-11 06:30 — VCS Evidence Sweep #2
- 26 WA sends = 0 genuine replies. WoodenStreet bot class-1 spam rejector.
- hot-queue date-lock bug confirmed. Jiya UPI window expired.
- 7 GHANTIs dispatched, 0 ACK within 30-min

## IS-RUN Sep-11 08:30 — VCS Evidence Sweep #3 (latest)
- Re-verified ALL evidence via live SSH @08:28 IST
- Discovered: whatsapp_automation NOT scheduled in hourly loop (0 _run_job call sites)
- Pitch v2 PIVOT: no UPI in first msg → human handoff → UPI close (response to WoodenStreet spam-reject pattern)
- 8 fresh GHANTIs dispatched with HARD 30-min deadlines, evidence-first acceptance
