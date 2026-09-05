#!/usr/bin/env python3
"""PILOT Sep-03 11:05 IST sweep — FRESH LIVE-verification + OWNER ESCALATION (11:00 gate).
FRESH LIVE (11:01): /health 200 healthy (version 036a4e4b, uptime 1h53m). auto_sent true=0/2270
(NO msg-id anywhere — WA rail ZERO real send day5); SIP 5 vars ALL len=0 (SIP_HOST/USERNAME/PASSWORD/
DID/PROVIDER) -> DID NOT landed, VOBIZ_CALLER_ID len13 REVOKED CLI; call_loop proc0 mtime Aug31 08:39Z
(dialer DEAD day5 batch211 ok0/fail3); leads/ ABSENT (ammo 0); hot-queue 09-03 PRESENT (scheduler healed).
Revenue VERIFIED Rs1,999 Jiya sole (INV/2026-27/0001); GAP Rs4,98,001.
FLEET 0-ACK ~54h — ALL 8 bots own tasks (07:35 assign, 10:00/10:45/11:00 gates ALL MISSED, 0 evidence).
11:00 OWNER ESCALATION GATE ARRIVED. No new TASK-ID (anti-spam, max 1/bot/run honoured since 07:35).
Apex bottleneck #1 WA-rail auto_send=0 (ENG-004); #2 genuine-intent close (SAL-005); #3 DID-land (PLT-005);
Jiya protect (SUC-004). ESCALATION: fleet DEAF 54h -> dispatch rail (messages.jsonl) NOT reaching bots;
revenue execution 0 across all channels. OWNER must decide: (a) unblock fleet comms, (b) reduce scope,
(c) direct executor. Appends messages.jsonl, updates bots/tasks/pinned."""
import json, os

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-03T11:05:00+05:30"

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")

# ---------- 1) messages.jsonl (message_agent channel) ----------
msgs = [
    {"ts": TS, "from": "PILOT", "to": "OWNER", "task_id": "ESCALATION-1105", "type": "OWNER_ESCALATION", "priority": "P0",
     "msg": "🚨 OWNER ESCALATION 11:05 IST (Sep3) — FLEET 0-ACK ~54h, REVENUE STALLED DAY5. VERIFIED Rs1,999 (Jiya INV/2026-27/0001 SOLE) | GAP Rs4,98,001. LIVE (11:01): /health 200; auto_sent TRUE=0/2270 NO msg-id (WA rail ZERO real send day5, flip LIVE par 0); SIP 5 vars ALL EMPTY (DID NOT landed, CLI revoked); dialer DEAD day5 (leads ammo 0); hot-queue 09-03 PRESENT (dirty). ALL 8 bots (ENG/SAL/PLT/SUC/HNT/OPS/GRD/BRD) apne tasks OWN kar rahe par 10:00/10:45/11:00 gates sab MISSED, 0 ACK, 0 evidence ~54h. DISPATCH RAIL (messages.jsonl) INEFFECTIVE — bots DEAF. DECISION CHAHIYE (deadline 12:00 IST): (a) fleet comms unblock karo (message_agent channel verify/pry), YA (b) 2-3 executable humans/executors ko direct kick do, YA (c) scope cut karo (7-day ₹5L ab unrealistic — day5 pe ₹0 collect) + realizable target. RECOMMEND: (b)+(c) — WA-rail #1 gate manual executor + Jiya retention abhi, target ko evidence-based re-base karo. Impact: har decision-day miss = ₹0 day. MUST-PICK. 🐦"},
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "🎯 REVENUE COMMAND 11:05 IST (Sep3): TARGET Rs5,00,000 | VERIFIED Rs1,999 (Jiya SOLE) | GAP Rs4,98,001 | PIPELINE hot-queue 09-03 PRESENT dirty (0 buyer proven) + wa_conversations 435 (0 genuine proven) | HOT: Jiya retention + GENUINE-intent close | BOTTLENECK #1 WA auto_send ZERO day5 (ENG-004) #2 genuine close (SAL-005) #3 DID (PLT-005) | FLEET 0-ACK ~54h -> 11:00 OWNER ESCALATION FIRED. Ek evidence lao — koi bhi bot, koi bhi task: pehla auto_sent msg-id / genuine reply / SMTP artifact / verdict / digest / CSV / DID status. Abhi bhi 0 = fleet DEAD. Pehla proof = reassign unblock. ACK jaldi. 🐦"},
    {"ts": TS, "from": "PILOT", "to": "engineering", "task_id": "ENG-004", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "ENG-004 (11:05 REBUMP — 5th gate): WA flip LIVE=1 par auto_sent true=0/2270, msg-id count 0 — sendText path ZERO day5. #1 revenue gate. 10:00/10:45/11:00 sab MISSED. Show me pehla auto_sent msg-id + commit sha. 0 ACK 54h = you are the #1 reason ₹0. Ships by 12:00 or reassign."},
    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "SAL-005", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "SAL-005 (11:05 REBUMP): dirty blast HARD STOP. GENUINE wa_conversations intent thread -> manual WAHA sendText close msg-id. ACC 12:00: >=3 genuine DELIVERED + DID vendor status. 0 ACK 54h."},
    {"ts": TS, "from": "PILOT", "to": "platform", "task_id": "PLT-005", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "PLT-005 (11:05 REBUMP): SIP 5 vars EMPTY re-confirm (DID NOT landed), CLI revoked, dialer dead day5, leads 0. vendor DID proof/ETA ya env-swap+restart. ACC 12:00. 0 ACK 54h."},
    {"ts": TS, "from": "PILOT", "to": "success", "task_id": "SUC-004", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "SUC-004 (11:05 REBUMP): Jiya SOLE payer — churn = ₹0. SMTP artifact + WA follow-up, DID-independent. ACC 12:00. 0 proof day2. Revenue-protect P0."},
    {"ts": TS, "from": "PILOT", "to": "hunter", "task_id": "HNT-005", "type": "TASK_REBUMP", "priority": "P1",
     "msg": "HNT-005 (11:05 REBUMP): leads/=0 ammo day5. 50 QUALIFIED DND mobile CSV (dirty REJECT). ACC 12:00. 0 ACK 54h."},
    {"ts": TS, "from": "PILOT", "to": "guardian", "task_id": "GRD-004", "type": "TASK_REBUMP", "priority": "P1",
     "msg": "GRD-004 (11:05 REBUMP): PASS/FAIL verdicts file (auto_send link-only/rev-truth/dialer/DID/43-blast/heal). ACC 12:00. 0 ACK 54h — independent gate blocks everything."},
    {"ts": TS, "from": "PILOT", "to": "operations", "task_id": "OPS-007", "type": "TASK_REBUMP", "priority": "P1",
     "msg": "OPS-007 (11:05 REBUMP): digest — WA auto_send 0 root + dialer restart cadence + 09-04 queue watch. ACC 12:00. 0 ACK 54h."},
    {"ts": TS, "from": "PILOT", "to": "board", "task_id": "BRD-003", "type": "TASK_REBUMP", "priority": "P2",
     "msg": "BRD-003 (11:05 REBUMP): VPS mirror + /app/bot-command-center page verify. PILOT fresh push abhi. ACC 12:00. Visualization ONLY. 0 ACK 54h."},
]
with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("messages appended:", len(msgs))

# ---------- 2) bots.json ----------
bp = os.path.join(BASE, "bots.json")
bots = load(bp)
sts = {
    "Pilot": "11:05 IST Sep3: /health 200 (ver 036a4e4b uptime1h53m); WA flip LIVE=1 par auto_sent 0/2270 NO msg-id day5 -> 0 UPI; SIP 5 vars ALL EMPTY DID NOT landed; dialer DEAD day5 (leads0); rev Rs1,999 Jiya sole; GAP Rs4,98,001. FLEET 0-ACK ~54h -> 11:00 OWNER ESCALATION FIRED. All 10:00/10:45/11:00 gates missed.",
    "engineering": "ENG-004 P0: WA flip LIVE par auto_send 0/2270 NO msg-id — #1 gate. 5th rebump. 12:00.",
    "platform": "PLT-005 P0: SIP 5 vars EMPTY (DID NOT landed), CLI revoked, leads0, dialer dead day5. 12:00.",
    "operations": "OPS-007 P1: 09-03 queue PRESENT (healed); WA auto_send 0 digest + restart cadence. 12:00.",
    "sales": "SAL-005 P0: dirty blast HARD STOP; genuine wa_conversations intent close. 12:00.",
    "hunter": "HNT-005 P1: leads/ 0 ammo day5; 50 qualified DND mobile CSV. 12:00.",
    "guardian": "GRD-004 P1: verdicts file (auto_send/rev-truth/dialer/DID/43-blast/heal). 12:00.",
    "success": "SUC-004 P0: Jiya sole payer retention SMTP+WA proof. 12:00.",
    "board": "BRD-003 P2: VPS mirror + page verify. 12:00.",
}
for k, v in sts.items():
    if k in bots:
        bots[k]["status"] = v
save(bp, bots)
print("bots.json updated")

# ---------- 3) tasks.json evidence_tail + updated_at ----------
tp = os.path.join(BASE, "tasks.json")
tasks = load(tp)
tails = {
    "ENG-004": "PILOT 11:05 IST Sep3 LIVE: auto_sent TRUE=0/2270 (msg-id 0) — WA rail ZERO real send day5. #1 gate. 5th rebump, 0 ACK ~54h -> OWNER ESCALATION. 12:00 gate.",
    "SAL-005": "PILOT 11:05 IST Sep3: dirty HARD STOP; genuine intent close. 5th rebump, 0 ACK ~54h. 12:00.",
    "PLT-005": "PILOT 11:05 IST Sep3 LIVE: SIP 5 vars ALL EMPTY re-confirm (DID NOT landed); CLI revoked; dialer DEAD day5 (proc0 mtime Aug31 leads0). 5th rebump 0 ACK ~54h. 12:00.",
    "SUC-004": "PILOT 11:05 IST Sep3: Jiya sole payer; 0 SMTP/WA proof day2. 5th rebump 0 ACK ~54h. 12:00.",
    "HNT-005": "PILOT 11:05 IST Sep3 LIVE: leads/ ABSENT ammo day5. 50 qualified DND CSV. 5th rebump 0 ACK. 12:00.",
    "GRD-004": "PILOT 11:05 IST Sep3: verdicts file owed. 5th rebump 0 ACK ~54h -> escalation. 12:00.",
    "OPS-007": "PILOT 11:05 IST Sep3: 09-03 queue PRESENT (healed); digest + restart cadence. 5th rebump 0 ACK. 12:00.",
    "BRD-003": "PILOT 11:05 IST Sep3: mirror + page verify. 5th rebump 0 ACK. 12:00.",
}
for t in tasks:
    if t["id"] in tails:
        t["evidence_tail"] = tails[t["id"]]
        t["updated_at"] = TS
save(tp, tasks)
print("tasks.json tails updated")

# ---------- 4) pinned.json ----------
pp = os.path.join(BASE, "pinned.json")
try:
    pin = load(pp)
except Exception:
    pin = {}
pin["last_updated"] = "2026-09-03T11:05+05:30"
pin["vps_status"] = ("HEALTHY (200 ver 036a4e4b); VERIFIED rev Rs1,999 (Jiya INV/2026-27/0001 SOLE); "
                     "WA flip LIVE=1 par auto_sent 0/2270 NO msg-id day5 -> 0 UPI; hot-queue 09-03 PRESENT (dirty); "
                     "dialer DEAD day5 (SIP 5 vars ALL EMPTY, CLI revoked, leads0); GAP Rs4,98,001. "
                     "FLEET 0-ACK ~54h -> 11:00 OWNER ESCALATION FIRED. Decision due 12:00.")
save(pp, pin)
print("pinned.json updated")
print("DONE")
