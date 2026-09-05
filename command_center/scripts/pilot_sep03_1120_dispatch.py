#!/usr/bin/env python3
"""PILOT Sep-03 11:20 IST sweep — FRESH LIVE re-verify (evidence-first, corrected probe).

LIVE VERIFIED 11:20 IST (clean positional probe — earlier sed=SET reading was a probe artifact):
  - /health 308 auth-gated; containers worker/app/scheduler Up 15h healthy.
  - WA flip LIVE=1 both containers (env gate SOLVED) BUT auto_sent true=0/false=443
    (msg-id count 0) -> WA rail still ZERO real send day5 -> #1 bottleneck (ENG-004).
  - SIP 5 vars ALL len=0 (SIP_HOST/USERNAME/PASSWORD/DID/PROVIDER EMPTY) -> DID NOT landed;
    VOBIZ_CALLER_ID len13 +9111 REVOKED CLI. call_loop proc 0; log mtime Aug31 08:39Z batch211
    ok0/fail3 -> dialer DEAD day5.
  - leads/ EMPTY ammo 0; hot-queue 09-03 PRESENT 44 rows (dirty, 0 genuine buyer proven).
  - Revenue VERIFIED Rs1,999 Jiya sole (INV/2026-27/0001); GAP Rs4,98,001.
  - FLEET 0-ACK ~54h independent of PILOT probes. 12:00 OWNER-ESCALATION gate next.
Apex same as 10:30/11:05: #1 WA auto_send ZERO (ENG-004); #2 genuine close (SAL-005);
#3 DID (PLT-005); Jiya protect (SUC-004). No new TASK-ID (07:35 set already owns; max 1/bot/run
honoured). Rebump only. Syncs messages.jsonl + bots/tasks/pinned."""
import json, os

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-03T11:20:00+05:30"

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
     "msg": "🎯 REVENUE COMMAND 11:20 IST (Sep3): TARGET Rs5,00,000 | VERIFIED Rs1,999 (Jiya SOLE) | GAP Rs4,98,001 | PIPELINE hot-queue 09-03 44 dirty (0 genuine buyer) + wa_conversations (0 genuine) | HOT: Jiya + GENUINE-intent close | BOTTLENECK #1 WA auto_send ZERO day5 (ENG-004) #2 genuine close (SAL-005) #3 DID NOT landed (PLT-005) | FLEET 0-ACK ~54h. 12:00 OWNER-ESCALATION gate. EK bhi evidence lao (usable msg-id / genuine reply / SMTP / verdict / digest / CSV / DID) — pehla proof = reassign unblock. Abhi bhi 0 = fleet DEAD. 🐦"},
    {"ts": TS, "from": "PILOT", "to": "engineering", "task_id": "ENG-004", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "ENG-004 (11:20 REBUMP): WA flip LIVE=1 re-confirm par auto_sent TRUE=0/443, msg-id 0 — sendText path ZERO day5. #1 revenue gate. 12:00 gate = pehla auto_sent msg-id + commit sha. 0 ACK 54h."},
    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "SAL-005", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "SAL-005 (11:20 REBUMP): dirty HARD STOP. GENUINE wa_conversations intent thread -> manual WAHA sendText close msg-id. 12:00: >=3 genuine DELIVERED + DID vendor status. 0 ACK 54h."},
    {"ts": TS, "from": "PILOT", "to": "platform", "task_id": "PLT-005", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "PLT-005 (11:20 REBUMP): SIP 5 vars re-verify ALL len=0 (DID NOT landed), CLI +9111 REVOKED, dialer proc0 day5, leads0. vendor DID proof/ETA ya env-swap+restart. 12:00. 0 ACK 54h."},
    {"ts": TS, "from": "PILOT", "to": "success", "task_id": "SUC-004", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "SUC-004 (11:20 REBUMP): Jiya SOLE payer — churn = Rs0. SMTP artifact + WA follow-up, DID-independent. 12:00. Revenue-protect P0, 0 proof day2."},
    {"ts": TS, "from": "PILOT", "to": "hunter", "task_id": "HNT-005", "type": "TASK_REBUMP", "priority": "P1",
     "msg": "HNT-005 (11:20 REBUMP): leads/ EMPTY ammo day5. 50 QUALIFIED DND mobile CSV (dirty REJECT). 12:00. 0 ACK 54h."},
    {"ts": TS, "from": "PILOT", "to": "guardian", "task_id": "GRD-004", "type": "TASK_REBUMP", "priority": "P1",
     "msg": "GRD-004 (11:20 REBUMP): PASS/FAIL verdicts file. 12:00. 0 ACK 54h — independent gate blocks everything."},
    {"ts": TS, "from": "PILOT", "to": "operations", "task_id": "OPS-007", "type": "TASK_REBUMP", "priority": "P1",
     "msg": "OPS-007 (11:20 REBUMP): digest — WA auto_send 0 root + dialer restart cadence + 09-04 queue watch. 12:00. 0 ACK 54h."},
    {"ts": TS, "from": "PILOT", "to": "board", "task_id": "BRD-003", "type": "TASK_REBUMP", "priority": "P2",
     "msg": "BRD-003 (11:20 REBUMP): VPS mirror + /app/bot-command-center verify. PILOT fresh push abhi. 12:00. Visualization ONLY. 0 ACK 54h."},
]
with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("messages appended:", len(msgs))

# ---------- 2) bots.json ----------
bp = os.path.join(BASE, "bots.json")
bots = load(bp)
sts = {
    "Pilot": "11:20 IST Sep3: /health 308 auth-gated containers Up15h; WA flip LIVE=1 par auto_sent 0/443 NO msg-id day5; SIP 5 vars ALL EMPTY DID NOT landed (CLI revoked); dialer DEAD day5 (leads0); rev Rs1,999 Jiya sole; GAP Rs4,98,001. FLEET 0-ACK ~54h; 12:00 OWNER-ESCALATION gate next.",
    "engineering": "ENG-004 P0: WA flip LIVE par auto_send 0/443 NO msg-id — #1 gate. 12:00.",
    "platform": "PLT-005 P0: SIP 5 vars EMPTY (DID NOT landed), CLI revoked, leads0, dialer dead day5. 12:00.",
    "operations": "OPS-007 P1: 09-03 queue PRESENT; WA auto_send 0 digest + restart cadence. 12:00.",
    "sales": "SAL-005 P0: dirty blast HARD STOP; genuine wa_conversations intent close. 12:00.",
    "hunter": "HNT-005 P1: leads/ EMPTY ammo day5; 50 qualified DND mobile CSV. 12:00.",
    "guardian": "GRD-004 P1: verdicts file. 12:00.",
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
    "ENG-004": "PILOT 11:20 IST Sep3 LIVE: auto_sent TRUE=0/443 (msg-id 0) — WA rail ZERO real send day5, flip LIVE par 0 = code bug. #1 gate. 6th rebump 0 ACK ~54h. 12:00 OWNER-ESC gate.",
    "SAL-005": "PILOT 11:20 IST Sep3: dirty HARD STOP; genuine intent close. 6th rebump 0 ACK ~54h. 12:00.",
    "PLT-005": "PILOT 11:20 IST Sep3 LIVE: SIP 5 vars re-verify ALL len=0 (positional probe clean); CLI +9111 REVOKED; dialer DEAD day5 (proc0 mtime Aug31 batch211). 6th rebump 0 ACK ~54h. 12:00.",
    "SUC-004": "PILOT 11:20 IST Sep3: Jiya sole payer; 0 SMTP/WA proof day2. 6th rebump 0 ACK. 12:00.",
    "HNT-005": "PILOT 11:20 IST Sep3 LIVE: leads/ EMPTY ammo day5. 50 qualified DND CSV. 6th rebump 0 ACK. 12:00.",
    "GRD-004": "PILOT 11:20 IST Sep3: verdicts file owed. 6th rebump 0 ACK. 12:00.",
    "OPS-007": "PILOT 11:20 IST Sep3: 09-03 queue PRESENT 44; digest + restart cadence. 6th rebump 0 ACK. 12:00.",
    "BRD-003": "PILOT 11:20 IST Sep3: mirror + page verify. 6th rebump 0 ACK. 12:00.",
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
pin["last_updated"] = "2026-09-03T11:20+05:30"
pin["vps_status"] = ("/health 308 auth-gated containers Up15h; WA flip LIVE=1 par auto_sent 0/443 NO msg-id "
                     "day5 -> 0 UPI; SIP 5 vars ALL EMPTY DID NOT landed (CLI revoked); dialer DEAD day5 (leads0); "
                     "hot-queue 09-03 44 dirty; VERIFIED rev Rs1,999 (Jiya INV/2026-27/0001 SOLE); GAP Rs4,98,001. "
                     "FLEET 0-ACK ~54h -> 12:00 OWNER-ESCALATION gate.")
save(pp, pin)
print("pinned.json updated")
print("DONE")
