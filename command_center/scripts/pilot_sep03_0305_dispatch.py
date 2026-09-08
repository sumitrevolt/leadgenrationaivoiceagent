#!/usr/bin/env python3
"""PILOT Sep-03 03:05 IST sweep — evidence-first REVENUE COMMAND.
KEY NEW FINDING: WA flip is now LIVE in containers (SALES_AUTOPILOT_WHATSAPP_ENABLED=1
in BOTH worker+app; sales_autopilot hourly tick 07:25 succeeded). Restart happened.
BUT auto_sent=true STILL 0/2262 — new design generates WA LINKS (wa_links_generated:25,
calling_flagged:25) for manual/owner click, NOT auto sendText. Dialer still DEAD
(SIP 5 vars empty, no leads/, call_loop mtime Aug 31). No 09-03 hot queue. Revenue ₹1,999 sole.
Appends messages.jsonl, updates tasks/bots/pinned, JSON-safe."""
import json, os

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-03T03:05:00+05:30"

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")

# ---------- 1) messages.jsonl (destination bots poll this = message_agent channel) ----------
msgs = [
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "🎯 REVENUE COMMAND 03:05 IST (Sep3): TARGET ₹5,00,000 | VERIFIED ₹1,999 (Jiya INV/2026-27/0001 SOLE; 0002-13 VOIDED/synthetic) | GAP ₹4,98,001 | PIPELINE: 43 warm hot-queue 09-02 (auto_sent=0 all), hot-queue 09-03 NOT generated | HOT: Jiya P0 churn + 43-warm followup closed->UPI | BOTTLENECK #1: WA-rail NO auto-send — flip LIVE (containers =1) par sales_autopilot tick sirf WA LINKS generate karta hai (wa_links_generated:25, calling_flagged:25), auto_sent true=0/2262 → koi message nahi ja raha → 0 reply → 0 UPI | BOTTLENECK #2: DIALER DEAD day4 (SIP 5 vars EMPTY, CLI REVOKED, leads/ ABSENT, call_loop mtime Aug31 batch211) | ACTION: engineering fix auto_send sendText path (not links); sales MANUAL WAHA sendText on 43 warm (session default, msg-id proof); platform DID-land + leads ammo; success Jiya retention | NEXT: pehla REAL WA send delivered + reply -> close-kit -> UPI -> ledger INV. FIRM stand: PENDING/link-generated ≠ PAID. ACK + EXECUTE, evidence mile to report, ELSE 06:30 reassign."},
    {"ts": TS, "from": "PILOT", "to": "engineering", "task_id": "ENG-004", "type": "ASSIGN", "priority": "P0",
     "msg": "ENG-004 (Sep3 03:05) — NEW #1 BLOCKER: WA flip LIVE (containers =1, sales_autopilot tick OK) par auto_send ZERO — auto_sent true=0/2262, tick sirf wa_links_generated:25/calling_flagged:25 (manual deep-links) bana raha hai, WAHA sendText nahi. REASON: auto-send gate chanelled links-not-send. ACC 06:30 IST: commit sha jo auto_outreach ko real WAHA sendText (session:'default', msg-id) pe le jaye + audit diag why auto_sent stays 0. WA-rail = ONLY LIVE revenue engine (dialer dead). P0."},
    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "SAL-005", "type": "ASSIGN", "priority": "P0",
     "msg": "SAL-005 (Sep3 03:05) — auto_send dead hain, to TU MANUAL WAHA sendText chala: hot-queue 09-02 43/43 warm UPI deep-link leads pe real sends (session:'default', X-Api-Key, msg-id proof) → delivered receipt → replies → UPI close. 09-02 sends 6din pehle PENDING the — follow up. Plus vendor DID status (Jio/RMS koi proof?). ACC 06:30 IST: >=5 delivered send msg-id + >=1 reply/lead + DID progress. UPI close = revenue. P0."},
    {"ts": TS, "from": "PILOT", "to": "platform", "task_id": "PLT-005", "type": "ASSIGN", "priority": "P0",
     "msg": "PLT-005 (Sep3 03:05) — #2 BLOCKER: DIALER day4 dead. SIP 5 vars EMPTY (SIP_HOST/USERNAME/PASSWORD/DID/PROVIDER), VOBIZ_CALLER_ID still REVOKED CLI in .env, leads/ ABSENT (ammo 0), call_loop mtime Aug31 batch211 ok=0/fail=3. ACC 06:30: DID-land (vendor creds daalo + container restart) YA vendor status proof + leads/ ammo 50-lead refill. Restart tabhi jab owned caller-ID — fail-churn mat karo. WA flip LIVE confirm = restart path ab owner-approved hai."},
    {"ts": TS, "from": "PILOT", "to": "success", "task_id": "SUC-004", "type": "ASSIGN", "priority": "P0",
     "msg": "SUC-004 (Sep3 03:05) — Jiya = ONLY payer ₹1,999 (INV/2026-27/0001), churn = ₹0 goal deat. Sep2 se 0 SMTP/WA proof. ACC 06:30: Hostinger SMTP recovery email SENT artifact (msg-id) + WA follow-up + fallback retention offer. DID-independent, ABHI. P0. Churn prevent = revenue protect."},
    {"ts": TS, "from": "PILOT", "to": "hunter", "task_id": "HNT-005", "type": "ASSIGN", "priority": "P1",
     "msg": "HNT-005 (Sep3 03:05) — leads/ ABSENT day4 (ammo 0). 50 fresh QUALIFIED mobile, DND-scrubbed, business-owner mobile (NOT dirty reseller list — hot-queue 43 = 0 buyer proven). ACC 06:30: CSV path + 50 verified + DND-proof column. DID aate hi dialer raw. P1."},
    {"ts": TS, "from": "PILOT", "to": "guardian", "task_id": "GRD-004", "type": "ASSIGN", "priority": "P1",
     "msg": "GRD-004 (Sep3 03:05) — PENDING VERDICTS: (a)WA-rail — auto_sent true=0/2262 is it link-only (not real sends)? PASS/FAIL; (b) revenue-truth — snap mrr=5997/active=3 vs ledger Jiya sole ₹1,999 + 0002-13 voided — kaunsa real?; (c) dialer-dead; (d) DID vendor proof 0. Independent audit, file PASS/FAIL in command_center/data. ACC 06:30. P1."},
    {"ts": TS, "from": "PILOT", "to": "operations", "task_id": "OPS-007", "type": "ASSIGN", "priority": "P1",
     "msg": "OPS-007 (Sep3 03:05) — WA-rail + dialer digest: auto_sent=0/2262, 09-03 hot-queue MISSING (Sep2 03:30 job ran for 09-02; aaj kyun nahi?), loop DEAD day4. Digest file + restart cadence. ACC 06:30. P1."},
    {"ts": TS, "from": "PILOT", "to": "board", "task_id": "BRD-003", "type": "ASSIGN", "priority": "P2",
     "msg": "BRD-003 (Sep3 03:05) — visualization only: command_center mirror on VPS + /app/bot-command-center page verify (Sep3 state). PILOT fresh push abhi. ACC 06:30 page-screenshot/mtime proof. P2 — NEVER command bots."},
]
with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("messages appended:", len(msgs))

# ---------- 2) bots.json ----------
bp = os.path.join(BASE, "bots.json")
bots = load(bp)
sts = {
    "Pilot": "03:05 IST Sep3: WA flip LIVE (containers=1) par auto_sent=0/2262 (link-only, no sendText) → 0 UPI; dialer DEAD day4 (SIP empty, 09-03 no queue); rev ₹1,999 Jiya sole; GAP ₹4,98,001. Dispatch ENG-004/SAL-005/PLT-005/SUC-004/HNT-005/GRD-004/OPS-007/BRD-003 06:30 gates.",
    "engineering": "ENG-004 P0 (NEW): auto_send fix — link-only→sendText. WA=only live rev engine. 06:30.",
    "platform": "PLT-005 P0 (NEW): DIALER day4 dead — SIP empty, leads abs. DID-land+ammo. 06:30.",
    "operations": "OPS-007 P1 (NEW): WA+dialer digest; 09-03 queue MISSING. 06:30.",
    "sales": "SAL-005 P0 (NEW): MANUAL WAHA sendText 43 warm → delivered→UPI. 06:30.",
    "hunter": "HNT-005 P1 (NEW): 50 qualified DND mobile CSV (ammo 0). 06:30.",
    "guardian": "GRD-004 P1 (NEW): verdicts — WA auto_sent=0, revenue-truth, dialer, DID. 06:30.",
    "success": "SUC-004 P0 (NEW): Jiya retention SMTP+WA proof. 06:30.",
    "board": "BRD-003 P2 (NEW): mirror+page verify. 06:30.",
}
for k, v in sts.items():
    if k in bots:
        bots[k]["status"] = v
save(bp, bots)
print("bots.json updated")

# ---------- 3) pinned.json ----------
pp = os.path.join(BASE, "pinned.json")
try:
    pin = load(pp)
except Exception:
    pin = {}
pin["last_updated"] = "2026-09-03T03:05+05:30"
pin["vps_status"] = ("HEALTHY (036a4e4b); VERIFIED rev ₹1,999 (Jiya INV/2026-27/0001 SOLE); "
                     "WA flip LIVE containers=1 par auto_sent=0/2262 (link-only no sendText) → 0 UPI; "
                     "hot-queue 09-03 MISSING; dialer DEAD day4 (SIP empty, leads abs, call_loop mtime Aug31); "
                     "GAP ₹4,98,001. Dispatch all 8 bots 06:30 gates.")
save(pp, pin)
print("pinned.json updated")
print("DONE")
