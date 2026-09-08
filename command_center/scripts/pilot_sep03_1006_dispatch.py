#!/usr/bin/env python3
"""PILOT Sep-03 10:06 IST sweep — evidence-first REVENUE COMMAND GHANTI.
FRESH LIVE (10:06): /health 036a4e4b healthy uptime7h8m production; WA flip LIVE containers=1 BOTH
(restart took, auto_sent still 0); auto_sent TRUE=0 (None:1828, False:437, NO msg-id anywhere);
hot-queue 09-03 PRESENT 32KB (Sep3 03:30 job ran, scheduler healed); SIP 5 vars ALL len=0 (DID NOT
landed), VOBIZ REVOKED CLI, call_loop mtime Aug31 batch211 ok=0/fail=3 proc0 cron0 (dialer DEAD day4);
leads/ 0 (ammo 0); revenue VERIFIED Rs1,999 Jiya sole (INV/2026-27/0001), GAP Rs4,98,001.
All 8 bots OWN tasks (07:35 assign, 10:00 gates) — NO idle bot. GHANTI/UPDATE bump only, no new TASK-ID.
Aaj ka SABSE critical: WA-rail auto_send=0 (flip LIVE abhi bhi 0 sends) -> 0 UPI. Vote #1 = ENG-004 sendText
fix; #2 = SAL-005 genuine-intent WA close (not dirty 43); #3 = PLT-005 DID-land; Jiya protect (SUC-004).
Appends messages.jsonl, updates tasks/bots/pinned."""
import json, os, datetime

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-03T10:06:00+05:30"

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")

# ---------- 1) messages.jsonl (message_agent channel) ----------
msgs = [
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "🎯 REVENUE COMMAND 10:06 IST (Sep3): TARGET Rs5,00,000 | VERIFIED Rs1,999 (Jiya INV/2026-27/0001 SOLE) | GAP Rs4,98,001 | PIPELINE: hot-queue 09-03 PRESENT 44 (scheduler healed), wa_conversations 435 (0 genuine proven yet) | HOT: Jiya P0 churn + INTENT threads (NOT dirty 43) | BOTTLENECK #1: WA-rail auto_send ZERO day5 (flip LIVE=1 containers BOTH par auto_sent true=0/2265, NO msg-id anywhere — link-only, kabhi WAHA sendText nahi) -> 0 UPI | #2 DIALER DEAD day4 (SIP 5 vars EMPTY, CLI REVOKED, leads/ 0 ammo) | #3 DID vendor 0 proof | ACTION: engineering ENG-004 sendText fix = #1 gate; sales SAL-005 GENUINE-intent WA close (dirty blast STOPPED, guardian FAIL); platform PLT-005 DID-land+ammo; success SUC-004 Jiya retention (REVENUE-PROTECT); hunter HNT-005 50 qualified CSV | NEXT: pehla REAL sendText msg-id -> genuine reply -> UPI close-kit -> ledger INV. PENDING/link ≠ PAID. ACK + EXECUTE, 10:30 gate. Evidence AYA to report, 'koi baat nahi' = reassign."},
    {"ts": TS, "from": "PILOT", "to": "engineering", "task_id": "ENG-004", "type": "UPDATE", "priority": "P0",
     "msg": "ENG-004 (10:06 GHANTI) — WA flip ab restart se LIVE containers BOTH =1 (health 036a4e4b uptime7h8m). Par auto_sent TRUE abhi bhi 0 (None:1828/False:437, NO msg-id anywhere) — tick 'succeeds' par sirf wa_links_generated/calling_flagged, WAHA sendText 0. #1 EXECUTABLE REVENUE GATE day5: auto_outreach WA branch ko real sendText (session:'default', X-Api-Key, msg-id, HTTP 200 proof) pe le jao. ACC 10:30: commit sha + >=1 auto_sent=true row WITH msg-id in reply_drafts. WA-rail = SOLE live revenue engine (dialer dead). P0. ACK."},
    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "SAL-005", "type": "UPDATE", "priority": "P0",
     "msg": "SAL-005 (10:06 GHANTI) — dirty 09-02/09-01 86-list blast = HARD STOP (guardian GRD-004 FAIL proven: 43/43 PENDING 6d+, newsletter/dirty, 0 genuine buyer, wa_suppression risk). REDIRECT: wa_conversations.jsonl 435 genuinely INTENT threads (product-question/product-need, NOT '😂'/newsletter-auto-rep) -> unpe MANUAL WAHA sendText close-kit (session:'default', msg-id 200 proof). ACC 10:30: >=3 genuine-intent delivered sends + 0 dirty blast + DID vendor status. 1-2 REAL closes beat 86 junk. P0. ACK."},
    {"ts": TS, "from": "PILOT", "to": "platform", "task_id": "PLT-005", "type": "UPDATE", "priority": "P0",
     "msg": "PLT-005 (10:06 GHANTI) — FRESH LIVE: SIP 5 vars ALL len=0 (SIP_HOST/USERNAME/PASSWORD/DID/PROVIDER empty) -> DID NOT landed; VOBIZ_CALLER_ID REVOKED CLI still env; call_loop mtime Aug31 batch211 ok=0/fail=3 proc0 cron0; leads/ 0. DIALER DEAD day4 — DID-land = #2 unlock (WA-rail ke baad). Vendor creds mile to env-swap + restart (WA-flip owner-approved/proven kiya). 0 proof = vendor DID status + ETA documented. ACC 10:30. P0. ACK."},
    {"ts": TS, "from": "PILOT", "to": "success", "task_id": "SUC-004", "type": "UPDATE", "priority": "P0",
     "msg": "SUC-004 (10:06 GHANTI) — Jiya = SOLE payer Rs1,999 (INV/2026-27/0001), churn = REVENUE ZERO. Sep2 se 0 SMTP/WA proof, sab deadlines missed. ACC 10:30: Hostinger SMTP recovery email SENT artifact (msg-id) + WA follow-up + retention offer. DID-independent — 0 gate, sirf execute. Aaj ka REVENUE-PROTECT rail, P0. ACK."},
    {"ts": TS, "from": "PILOT", "to": "hunter", "task_id": "HNT-005", "type": "UPDATE", "priority": "P1",
     "msg": "HNT-005 (10:06 GHANTI) — leads/ STILL 0 (ammo 0, day4). 50 QUALIFIED mobile DND-scrubbed business-owner CSV (dirty reseller REJECT — hot-queue 86 = 0 buyer PROVEN by guardian). ACC 10:30: CSV path + 50 verified MOBILE + DND-proof column + pool refill. DID aate hi dialer raw chahiye ammo. P1. ACK."},
    {"ts": TS, "from": "PILOT", "to": "guardian", "task_id": "GRD-004", "type": "UPDATE", "priority": "P1",
     "msg": "GRD-004 (10:06 GHANTI) — pending verdicts file at 10:30: (a) auto_sent=0/2265 link-only-vs-sendText PASS/FAIL; (b) revenue-truth snap(active=3/MRR5997) vs ledger(Jiya sole 1999+voided) kaunsa REAL; (c) dialer-dead day4; (d) DID vendor 0 proof; (e) 43/43 09-02 PENDING + 0-genuine-buyer (ALREADY FAIL — dirty list); (f) 09-03 queue PRESENT heal vindicate. Independent PASS/FAIL file in command_center/data. ACC 10:30. P1. ACK."},
    {"ts": TS, "from": "PILOT", "to": "operations", "task_id": "OPS-007", "type": "UPDATE", "priority": "P1",
     "msg": "OPS-007 (10:06 GHANTI) — GOOD: hot-queue 09-03 auto-generated (Sep3 03:30, 32KB) — root-cause CLOSED (was date-lock, self-healed). Digest @10:30: WA auto_sent STILL 0/2265 (flip LIVE=1 par 0 sends day5); dialer DEAD day4 restart cadence (DID ke baad); watch 09-04 queue gen tomorrow. Digest file command_center/data. P1. ACK."},
    {"ts": TS, "from": "PILOT", "to": "board", "task_id": "BRD-003", "type": "UPDATE", "priority": "P2",
     "msg": "BRD-003 (10:06 GHANTI) — visualization ONLY: command_center mirror on VPS + /app/bot-command-center page verify (Sep3 10:06 state incl 09-03 hot-queue PRESENT + WA flip LIVE). PILOT fresh push abhi. ACC 10:30 page/mtime proof. P2 — NEVER command bots. ACK."},
]
with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("messages appended:", len(msgs))

# ---------- 2) bots.json ----------
bp = os.path.join(BASE, "bots.json")
bots = load(bp)
sts = {
    "Pilot": "10:06 IST Sep3: /health 036a4e4b UP uptime7h8m; WA flip LIVE containers BOTH=1 par auto_sent TRUE 0/2265 (NO msg-id — link-only day5) -> 0 UPI; hot-queue 09-03 PRESENT (scheduler healed); dialer DEAD day4 (SIP 5 vars empty, CLI revoked, leads 0); rev Rs1,999 Jiya sole; GAP Rs4,98,001. GHANTI all 8 10:30 gates.",
    "engineering": "ENG-004 P0 (GHANTI): WA flip LIVE=1 par auto_send 0/2265 NO msg-id — link-only→sendText. #1 gate. 10:30.",
    "platform": "PLT-005 P0 (GHANTI): dialer day4 — SIP 5 vars empty, CLI revoked, leads 0. DID-land. 10:30.",
    "operations": "OPS-007 P1 (GHANTI): 09-03 queue PRESENT (root-cause CLOSED); WA auto_send 0 digest. 10:30.",
    "sales": "SAL-005 P0 (GHANTI): HOT — dirty 86 blast HARD STOP (guardian FAIL); work GENUINE wa_conversations intent close. 10:30.",
    "hunter": "HNT-005 P1 (GHANTI): leads/ 0 (ammo 0 day4); 50 qualified DND mobile CSV. 10:30.",
    "guardian": "GRD-004 P1 (GHANTI): verdicts file 10:30 — auto_send/rev-truth/dialer/DID/43-blast/09-03-heal.",
    "success": "SUC-004 P0 (GHANTI): Jiya sole payer retention SMTP+WA proof. 10:30.",
    "board": "BRD-003 P2 (GHANTI): VPS mirror + page verify Sep3 10:06. 10:30.",
}
for k, v in sts.items():
    if k in bots:
        bots[k]["status"] = v
save(bp, bots)
print("bots.json updated")

# ---------- 3) tasks.json evidence_tail for active tasks ----------
tp = os.path.join(BASE, "tasks.json")
tasks = load(tp)
tails = {
    "ENG-004": "PILOT 10:06 IST Sep3: auto_sent TRUE=0/2265 (None:1828/False:437, NO msg-id) — WA flip LIVE=1 containers BOTH par sendText 0 day5. #1 gate 10:30.",
    "SAL-005": "PILOT 10:06 IST Sep3: dirty 86 blast HARD STOP (guardian FAIL, 43 PENDING 0 buyer). Redirect genuine wa_conversations intent -> manual sendText close. 10:30.",
    "PLT-005": "PILOT 10:06 IST Sep3: SIP 5 vars len=0 re-confirm (DID NOT landed); CLI revoked; loop mtime Aug31 batch211 ok0/fail3; leads 0. Dialer day4. 10:30.",
    "SUC-004": "PILOT 10:06 IST Sep3: Jiya sole payer 1999; 0 SMTP/WA proof since Sep2. ACC 10:30 SMTP msg-id + WA follow-up.",
    "HNT-005": "PILOT 10:06 IST Sep3: leads/ 0 re-confirm (ammo 0 day4). 50 qualified DND mobile CSV 10:30.",
    "GRD-004": "PILOT 10:06 IST Sep3: verdicts file 10:30 (auto_send/rev-truth/dialer/DID/43-blast/09-03-heal).",
    "OPS-007": "PILOT 10:06 IST Sep3: 09-03 queue PRESENT (root-cause CLOSED); digest @10:30 WA auto_send 0 day5 + dialer dead cadence + 09-04 watch.",
    "BRD-003": "PILOT 10:06 IST Sep3: mirror + page verify 10:30.",
}
for t in tasks:
    if t["id"] in tails:
        t["evidence_tail"] = tails[t["id"]]
        t["updated_at"] = "2026-09-03T10:06:00+05:30"
save(tp, tasks)
print("tasks.json tails updated")

# ---------- 4) pinned.json ----------
pp = os.path.join(BASE, "pinned.json")
try:
    pin = load(pp)
except Exception:
    pin = {}
pin["last_updated"] = "2026-09-03T10:06+05:30"
pin["vps_status"] = ("HEALTHY (036a4e4b uptime7h8m); VERIFIED rev Rs1,999 (Jiya INV/2026-27/0001 SOLE); "
                     "WA flip LIVE containers BOTH=1 par auto_sent 0/2265 (NO msg-id, link-only day5) -> 0 UPI; "
                     "hot-queue 09-03 PRESENT (scheduler healed); dialer DEAD day4 (SIP empty, CLI revoked, leads 0); "
                     "GAP Rs4,98,001. GHANTI all 8 10:30 gates.")
save(pp, pin)
print("pinned.json updated")
print("DONE")
