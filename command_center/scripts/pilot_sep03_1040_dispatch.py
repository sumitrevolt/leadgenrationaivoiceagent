#!/usr/bin/env python3
"""PILOT Sep-03 10:40 IST sweep — FRESH LIVE-verification + 11:00 escalation gate.
Evidence-first re-verify (10:40): /health 200 UP; WA flip LIVE containers BOTH=1 par
auto_sent TRUE=0 (NO msg-id — WA rail 0 real send day5); SIP 5 vars ALL len=0 (SIP_HOST/
USERNAME/PASSWORD/DID/PROVIDER) -> DID NOT landed, VOBIZ_CALLER_ID len13 REVOKED CLI still;
call_loop proc0 mtime Aug31 08:39Z (dialer DEAD day5); leads/ =0 (ammo 0); hot-queue 09-03
PRESENT (scheduler healed). Rev VERIFIED Rs1,999 Jiya sole; GAP Rs4,98,001.
10:30 FINAL GHANTI all 8 already fired (10:45 gates). This run = FRESH proof + 11:00 gate.
NO new TASK-ID (anti-spam, max 1/bot/run already honoured at 10:30).
Apex bottleneck #1 WA-rail auto_send=0 (ENG-004); #2 genuine-intent close (SAL-005);
#3 DID-land (PLT-005); Jiya protect (SUC-004).
Appends messages.jsonl, updates bots/tasks/pinned."""
import json, os, datetime

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-03T10:40:00+05:30"

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")

# ---------- 1) messages.jsonl (message_agent channel) — single REV-COMMAND update ----------
msgs = [
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "🎯 REVENUE COMMAND 10:40 IST (Sep3) FRESH-LIVE: TARGET Rs5,00,000 | VERIFIED Rs1,999 (Jiya INV/2026-27/0001 SOLE) | GAP Rs4,98,001 | PIPELINE wa_conversations 435 (0 genuine proven) + hot-queue 09-03 PRESENT (dirty!) | HOT: Jiya retention + GENUINE-intent close | BOTTLENECK #1 WA-rail auto_send ZERO day5 (flip LIVE=1 par auto_sent true=0, NO msg-id — link-only, sendText 0) -> 0 UPI | #2 DIALER DEAD day5 (SIP 5 vars ALL len=0, CLI len13 REVOKED, leads 0) | #3 DID vendor 0 proof | ACTION: engineer ENG-004 sendText fix = #1 gate | sales SAL-005 genuine-intent WA close (dirty HARD STOP) | platform PLT-005 DID-land+ammo | success SUC-004 Jiya retention (REVENUE-PROTECT) | hunter HNT-005 50 qualified DND CSV | ops/guardian digest+verdict | NEXT: pehla REAL sendText msg-id -> genuine reply -> UPI close-kit -> ledger INV. PENDING/link NEHI PAID. 10:30 FINAL GHANTI gates 10:45 = ABHI OVERDUE; 11:00 IST = OWNER ESCALATION. Pehla evidence lao abhi, nahi to aage badho. ACK + EXECUTE. 🐦" },
]
with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("messages appended:", len(msgs))

# ---------- 2) bots.json status bump ----------
bp = os.path.join(BASE, "bots.json")
bots = load(bp)
sts = {
    "Pilot": "10:40 IST Sep3 FRESH-LIVE: /health 200; WA flip LIVE=1 par auto_sent 0/2270 NO msg-id (day5) -> 0 UPI; SIP 5 vars ALL len=0 DID NOT landed, CLI len13 revoked; dialer DEAD day5 (proc0 leads0); rev Rs1,999 Jiya sole; GAP Rs4,98,001. 10:30 FINAL GHANTI over → 11:00 OWNER ESCALATION gate.",
    "engineering": "ENG-004 P0 (#1 gate): WA flip LIVE=1 par auto_send 0/2270 NO msg-id — link-only→sendText. 10:45 MISSED → 11:00 escalate.",
    "platform": "PLT-005 P0: SIP 5 vars ALL len=0 (DID NOT landed, re-verified 10:40), CLI revoked, leads 0. DID-land. 10:45 → 11:00.",
    "operations": "OPS-007 P1: 09-03 queue PRESENT (healed); auto_send 0 digest + dialer dead cadence. 10:45 → 11:00.",
    "sales": "SAL-005 P0: dirty blast HARD STOP; genuine wa_conversations intent close. 10:45 → 11:00.",
    "hunter": "HNT-005 P1: leads/ =0 (ammo 0, day5); 50 qualified DND mobile CSV. 10:45 → 11:00.",
    "guardian": "GRD-004 P1: verdicts file (auto_send/rev-truth/dialer/DID/43-blast/09-03-heal). 10:45 → 11:00.",
    "success": "SUC-004 P0: Jiya sole payer retention SMTP+WA proof. 10:45 → 11:00.",
    "board": "BRD-003 P2: VPS mirror + page verify. 10:45 → 11:00.",
}
for k, v in sts.items():
    if k in bots:
        bots[k]["status"] = v
save(bp, bots)
print("bots.json updated")

# ---------- 3) tasks.json fresh evidence_tail + updated_at for active tasks ----------
tp = os.path.join(BASE, "tasks.json")
tasks = load(tp)
tails = {
    "ENG-004": "PILOT 10:40 IST Sep3 FRESH-LIVE: WA flip containers BOTH=1 (worker+app) par auto_sent true=0/2270 NO msg-id (link-only day5) -> sendText 0. #1 gate. 10:45 MISSED -> 11:00 OWNER ESCALATION.",
    "SAL-005": "PILOT 10:40 IST Sep3 FRESH-LIVE: dirty 86 HARD STOP (guardian FAIL); redirect genuine wa_conversations intent -> manual sendText close msg-id. 10:45 MISSED -> 11:00 escalate.",
    "PLT-005": "PILOT 10:40 IST Sep3 FRESH-LIVE: SIP 5 vars ALL len=0 re-confirm (SIP_HOST/USERNAME/PASSWORD/DID/PROVIDER empty -> DID NOT landed); VOBIZ_CALLER_ID len13 REVOKED; loop proc0 mtime Aug31 08:39Z; leads=0. Dialer DEAD day5. 11:00 escalate.",
    "SUC-004": "PILOT 10:40 IST Sep3 FRESH-LIVE: Jiya sole payer Rs1,999; 0 SMTP/WA proof since Sep2 (day2). ACC 10:45 SMTP msg-id + WA follow-up MISSED -> 11:00 escalate. REVENUE-PROTECT P0.",
    "HNT-005": "PILOT 10:40 IST Sep3 FRESH-LIVE: leads/ dir =0 (ammo 0 day5 re-confirm). 50 qualified DND mobile CSV MISSED 10:45 -> 11:00 escalate.",
    "GRD-004": "PILOT 10:40 IST Sep3 FRESH-LIVE: verdicts file MISSED 10:45 -> 11:00 escalate (auto_send link-only PASS/FAIL critical).",
    "OPS-007": "PILOT 10:40 IST Sep3 FRESH-LIVE: 09-03 queue PRESENT (scheduler healed — GOOD); auto_send 0 digest + dialer dead cadence + 09-04 watch MISSED 10:45 -> 11:00.",
    "BRD-003": "PILOT 10:40 IST Sep3 FRESH-LIVE: mirror + page verify MISSED 10:45 -> 11:00.",
}
for t in tasks:
    if t["id"] in tails:
        t["evidence_tail"] = tails[t["id"]]
        t["updated_at"] = "2026-09-03T10:40:00+05:30"
save(tp, tasks)
print("tasks.json tails updated")

# ---------- 4) pinned.json ----------
pp = os.path.join(BASE, "pinned.json")
try:
    pin = load(pp)
except Exception:
    pin = {}
pin["last_updated"] = "2026-09-03T10:40+05:30"
pin["vps_status"] = ("HEALTHY (200, 10:40 FRESH-LIVE); VERIFIED rev Rs1,999 (Jiya INV/2026-27/0001 SOLE); "
                     "GAP Rs4,98,001; WA flip LIVE=1 par auto_sent 0/2270 NO msg-id (link-only day5) -> 0 UPI; "
                     "hot-queue 09-03 PRESENT (scheduler healed); dialer DEAD day5 (SIP 5 vars ALL len=0 DID NOT landed, "
                     "CLI revoked, leads 0); 10:30 FINAL GHANTI 10:45 gates MISSED -> 11:00 OWNER ESCALATION.")
save(pp, pin)
print("pinned.json updated")
print("DONE")
