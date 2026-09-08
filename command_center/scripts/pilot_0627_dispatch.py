#!/usr/bin/env python3
"""PILOT 06:27 IST (Sep 2) sweep — fresh evidence dispatch, lean anti-spam.
1 REV-COMMAND (ALL) + bottleneck-owner pointers (sales SAL-003, platform PLT-004).
Updates tasks.json evidence_tail (8 active), bots.json statuses, pinned.json.
Appends to messages.jsonl. JSON-safe."""
import json, os, datetime

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-02T06:27:00+05:30"

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")

# ---------- 1) messages.jsonl ----------
msgs = [
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "🎯 REVENUE COMMAND 06:27 IST (Sep2): TARGET ₹5,00,000 | VERIFIED ₹1,999 (Jiya INV/2026-27/0001 sole) | GAP ₹4,98,001 | PIPELINE: hot-queue 09-01 43/43 wa_link+UPI (09-02 ABSENT), dialer connects 0 (loop DEAD 48h+, mtime Aug31 08:39:55Z batch211 ok=0/fail=3 'not owned', proc0 cron0), WA-sent 0 (auto_sent true=0), leads/ ABSENT (ammo ZERO) | HOT: 43 WA closes + Jiya P0 | BOTTLENECK: WA container flip INERT (containers WA=0 disk=1, owner-restart) -> DID gate (SAL-003 09:00; SIP 4 vars len=0, VOBIZ_CALLER_ID REVOKED len13) -> Vobiz egress 000 day5 (PLT-004) -> loop+watchdog (OPS-006 10:30 / ENG-003 09:30) -> ammo (HNT-004 09:30) -> verify (GRD-003 11:00) -> Jiya (SUC-002 12:00) | ACTION: WA manual-send ABHI (WAHA with-key 200 WORKING; hot-queue 43 UPI deep-links) + vendor DID chase; gates 09:00/09:30/10:30/11:00/12:00 IST | NEXT: 09:00 vendor DID + WA>=10 -> env swap -> 10:00 TRAI batch -> pehla UPI close | FLEET: 0 ACK since 00:12Z — poll messages.jsonl, ACK TASK-ID + evidence file. Fresh 06:27 sweep filed. Sab bots apne existing task par ho — koi idle nahi, koi naya TASK-ID nahi (anti-spam)."},
    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "SAL-003", "type": "ESCALATION", "priority": "P0",
     "msg": "SAL-003 (06:27) BOTTLENECK OWNER — NO NEW TASK-ID. REINFORCE: FRESH 06:26 IST VPS — WAHA path OPEN (with-key 200 WORKING, session default 918459012607, no-key 401 = expected gate), auto_sent true=0, hot-queue 09-01.csv 43/43 wa_link+UPI present. Dialer dead 48h+, SIP 4 vars len=0. WA hot-queue = AAJ KA SINGLE EXECUTABLE REVENUE RAIL (DID-independent). ACC 09:00 IST BOTH: (a) >=10 WA-sent REAL proof (HTTP 200 + api id + auto_sent count >0), (b) vendor DID number/activation (Call Soft wa.me/917599967999 + RMS Tech 080-47652298). EXECUTE — reporting nahi. ACK SAL-003 NOW."},
    {"ts": TS, "from": "PILOT", "to": "platform", "task_id": "PLT-004", "type": "REINFORCE", "priority": "P0",
     "msg": "PLT-004 (06:27) — FRESH 06:26 IST: /health 37a1daf8 healthy uptime 12h21m; api.vobiz.com egress timeout day5 (DNS AWS-GA resolves, TCP-block); SIP_HOST/USERNAME/PASSWORD/DID len=0 (DID NOT landed); VOBIZ_CALLER_ID len13 REVOKED still in .env; WA flip INERT (leadgen_worker+leadgen_app WA=0, disk .env=1 — restart owner-approve, escalation filed 05:15). ACC 09:00 IST: egress root-cause verdict + re-test proof + Jio SIP env swap template + restart approval. ACK PLT-004."},
]

with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("messages appended:", len(msgs))

# ---------- 2) tasks.json evidence_tail (8 active) ----------
tp = os.path.join(BASE, "tasks.json")
tasks = load(tp)
tails = {
    "PLT-004": "PILOT 06:27 IST (Sep2 CRON): FRESH — /health 37a1daf8 OK uptime 12h21m; egress api.vobiz.com timeout day5; SIP 4 vars len=0; VOBIZ_CALLER_ID REVOKED len13; WA flip INERT (containers=0 disk=1, owner-approve). ACC 09:00 egress verdict + template.",
    "SAL-003": "PILOT 06:27 IST (Sep2 CRON): FRESH — WAHA with-key 200 WORKING, auto_sent true=0, hot-queue 09-01 43/43 present (09-02 ABSENT); loop DEAD 48h+; SIP 4 vars len=0; vendor DID nahi. ACC 09:00 WA>=10 + vendor DID.",
    "HNT-004": "PILOT 06:27 IST (Sep2 CRON): leads/ ABSENT re-confirm (ammo ZERO); hot-queue Sep2 ABSENT. ACC 09:30 50-lead DND CSV OWED.",
    "OPS-006": "PILOT 06:27 IST (Sep2 CRON): loop DEAD 48h+ re-confirm (mtime Aug31 08:39:55Z batch211, proc0, cron0). Restart sign = env swap. 10:30 digest OWED.",
    "GRD-003": "PILOT 06:27 IST (Sep2 CRON): revenue-truth gap confirmed (snap mrr=5997/active=3 vs ledger Jiya 1999 sole VOIDED tail); 6+1 verdicts 11:00 OWED.",
    "SUC-002": "PILOT 06:27 IST (Sep2 CRON): Jiya sole payer 1999 churn P0; ACC 12:00 SMTP proof OWED.",
    "ENG-003": "PILOT 06:27 IST (Sep2 CRON): watchdog missing (crontab 0); ACC 09:30 commit+runbook+watchdog OWED.",
    "BRD-002": "PILOT 06:27 IST (Sep2 CRON): fresh push abhi; page verify 12:00 OWED.",
}
for t in tasks:
    if t.get("id") in tails:
        t["evidence_tail"] = tails[t["id"]]
save(tp, tasks)
print("tasks.json evidence_tail updated:", len([t for t in tasks if t.get("id") in tails]))

# ---------- 3) bots.json statuses ----------
bp = os.path.join(BASE, "bots.json")
bots = load(bp)
sts = {
    "Pilot": "06:27 IST SWEEP: state UNCHANGED — loop DEAD 48h+ (batch211, proc0, cron0); SIP 4 vars len=0; VOBIZ_CALLER_ID REVOKED; WA flip INERT (containers=0 disk=1); WA-sent 0; leads/ ABSENT; hot-queue 09-01 43/43. FLEET 0 ACK — REV-COMMAND + SAL-003 escalate sent 06:27. Gates 09:00-12:00 IST.",
    "engineering": "ENG-003 P1: watchdog missing (crontab 0). Jio SIP failover runbook + watchdog+runbook 09:30. ACK missing.",
    "platform": "PLT-004 P0: egress timeout DAY5; SIP 4 vars len=0; VOBIZ_CALLER_ID REVOKED; WA flip INERT (owner-approve). Root-cause + template 09:00 IST. ACK missing.",
    "operations": "OPS-006 P0: loop DEAD 48h+ re-confirm (proc 0, cron 0, mtime Aug31 08:39Z). Restart sign = env swap; 10:30 digest. ACK missing.",
    "sales": "SAL-003 P0: WA manual-send ABHI (WAHA with-key 200 WORKING; hot-queue 09-01 43 UPI; auto_sent 0); vendor DID 09:00. ACK missing.",
    "hunter": "HNT-004 P1: leads/ ABSENT re-confirm; hot-queue Sep2 ABSENT; 50-lead DND CSV 09:30 IST. ACK missing.",
    "guardian": "GRD-003 P1: 6+1 verdicts 11:00 IST (revenue-truth + loop-dead + WAHA + auto_sent + leads + DID + WA-claim). ACK missing.",
    "success": "SUC-002 P0: Jiya only payer 1999 churn-risk; SMTP SENT proof 12:00 IST. REV-105 close-kit standby. ACK missing.",
    "board": "BRD-002 P2: MIRROR MD5-SYNCED VERIFIED (tasks/bots/messages 3/3); fresh push abhi. Page verify + cadence 12:00. ACK missing.",
}
for k, v in sts.items():
    if k in bots:
        bots[k]["status"] = v
save(bp, bots)
print("bots.json updated")

# ---------- 4) pinned.json ----------
pp = os.path.join(BASE, "pinned.json")
pin = load(pp)
pin["last_updated"] = "2026-09-02T06:27+05:30"
pin["vps_status"] = "HEALTHY (/health 37a1daf8 uptime 12h21m); loop DEAD 48h+ (batch211 REVOKED CLI; proc0 cron0); SIP 4 vars EMPTY; VOBIZ_CALLER_ID REVOKED; egress 000 day5; WA flip INERT (containers=0 disk=1); WA-sent 0; leads/ ABSENT; hot-queue 09-01 43/43 present"
save(pp, pin)
print("pinned.json updated")
print("DONE")