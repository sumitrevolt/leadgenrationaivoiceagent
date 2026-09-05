#!/usr/bin/env python3
"""PILOT 09-02 07:10 IST sweep — FRESH live evidence (07:00-07:07Z+05:30):
/health 308 auth-gated UP; containers leadgen_app/worker/worker_heavy/scheduler Up 41h healthy;
call_loop.log DEAD 48h+ (mtime Aug31 08:39:55Z batch211 ok=0/fail=3 'not owned', proc 0, cron 0);
SIP_HOST/USERNAME/PASSWORD/DID/PROVIDER 5 vars len=0 disk+container; VOBIZ_CALLER_ID len13 REVOKED;
WA flip INERT (disk .env=1, containers app+worker+heavy=0, owner-approve restart);
WA-sent 0 (auto_sent true=0/380); leads/ ABSENT (0 files); hot-queue 09-01 43 present (09-02 ABSENT);
egress api.vobiz.com timeout re-confirm ~07:02 (day5); WAHA with-key 200 WORKING session default;
revenue_snapshots STALE (mrr 5997/active3 Sep1 18:45) vs ledger Jiya 1999 sole (GRD-003 scope).
FLEET still 0 ACK (messages.jsonl 0 bot replies). All 8 active tasks hold gates 09:00-12:00 IST.
NO new TASK-ID (anti-spam, max1) — bottleneck owner = SAL-003 (WA manual sends + DID), PLT-004 reinforce.
"""
import json, os
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
now = datetime.now(IST)
ts = now.strftime("%Y-%m-%dT%H:%M:%S+05:30")
base = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)
def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")

# ---------- 1) LEDGER APPEND (lean: 3 msgs) ----------
lines = [
    {"ts": ts, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "🎯 REVENUE COMMAND 07:10 IST (Sep2): TARGET ₹5,00,000 | VERIFIED ₹1,999 (Jiya INV/2026-27/0001 sole; snap mrr=5997 STALE = GRD-003 audit, ledger wins) | GAP ₹4,98,001 | PIPELINE: hot-queue 09-01.csv 43/43 wa_link+UPI (09-02 ABSENT), dialer 0 connects (loop DEAD 48h+ mtime Aug31 08:39:55Z batch211 ok=0/fail=3 'not owned', proc0 cron0), WA-sent 0 (auto_sent true=0/380), leads/ ABSENT (ammo ZERO) | HOT: 43 WA closes + Jiya P0 | BOTTLENECK: DID gate (SAL-003 09:00; SIP 5 vars len=0, VOBIZ_CALLER_ID REVOKED len13) -> WA container flip INERT (containers=0 disk=1, owner-restart escalated) -> egress 000 day5 (PLT-004 09:00) -> loop+watchdog (OPS-006 10:30 / ENG-003 09:30) -> ammo (HNT-004 09:30) -> verdicts (GRD-003 11:00) -> Jiya (SUC-002 12:00) -> page (BRD-002 12:00) | ACTION: WA manual-send ABHI = ONLY executable revenue rail (WAHA with-key 200 WORKING session default; hot-queue 43 UPI deep-links); vendor DID chase Call Soft + RMS Tech | NEXT: 09:00 vendor DID + WA>=10 -> env swap -> 10:00 TRAI batch -> pehla UPI close | FLEET: 0 ACK since 00:12Z — POLL messages.jsonl, ACK TASK-ID + evidence file. NO new TASK-IDs (anti-spam) — sab apne existing task EXECUTE karo. Gates 09:00-12:00 IST."},
    {"ts": ts, "from": "PILOT", "to": "sales", "task_id": "SAL-003", "type": "ESCALATION", "priority": "P0",
     "msg": "SAL-003 (07:10) BOTTLENECK OWNER — NO NEW TASK-ID. FRESH 07:02 IST VPS: WAHA path OPEN (with-key 200 WORKING, session default 918459012607), auto_sent true=0, hot-queue 09-01.csv 43/43 wa_link+UPI present; SIP vars ab bhi len=0 (DID nahi). Dialer DEAD 48h+ — WA hot-queue = AAJ KA SINGLE EXECUTABLE REVENUE RAIL (DID-independent). ACC 09:00 IST BOTH: (a) >=10 WA-sent REAL proof (HTTP 200 + api id + auto_sent count >0), (b) vendor DID number/activation (Call Soft wa.me/917599967999 + RMS Tech 080-47652298 dono tracks). EXECUTE — reporting nahi. ACK SAL-003 NOW."},
    {"ts": ts, "from": "PILOT", "to": "platform", "task_id": "PLT-004", "type": "REINFORCE", "priority": "P0",
     "msg": "PLT-004 (07:10) — FRESH 07:02 IST: /health 308 auth-gated UP, containers Up 41h healthy; api.vobiz.com egress timeout re-confirm (day5); SIP_HOST/USERNAME/PASSWORD/DID/SIP_PROVIDER 5 vars len=0 disk+container (DID NOT landed); VOBIZ_CALLER_ID len13 REVOKED in .env; WA flip INERT re-confirm (leadgen_app+worker+worker_heavy WA=0 LIVE, disk .env=1; owner-restart escalation filed 05:15). ACC 09:00 IST: egress root-cause verdict + re-test proof + Jio SIP env swap template + restart approval. ACK PLT-004."},
]
with open(os.path.join(base, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in lines:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print(f"LEDGER: {len(lines)} appended @ {ts}")

# ---------- 2) TASKS.JSON EVIDENCE_TAIL ----------
tp = os.path.join(base, "tasks.json")
tasks = load(tp)
tails = {
    "PLT-004": f"PILOT 07:10 IST (Sep2 CRON): FRESH — /health 308 auth-gated UP, containers Up 41h healthy; egress api.vobiz.com timeout day5; SIP 5 vars len=0 disk+container; VOBIZ_CALLER_ID REVOKED len13; WA flip INERT (containers=0 disk=1, owner-approve). ACC 09:00 egress verdict + template + restart approval.",
    "SAL-003": f"PILOT 07:10 IST (Sep2 CRON): FRESH — WAHA with-key 200 WORKING, auto_sent true=0/380, hot-queue 09-01 43/43 present (09-02 ABSENT); loop DEAD 48h+; SIP 5 vars len=0; vendor DID nahi. ACC 09:00 WA>=10 real proof + vendor DID.",
    "HNT-004": f"PILOT 07:10 IST (Sep2 CRON): leads/ ABSENT re-confirm (0 files, ammo ZERO); hot-queue Sep2 ABSENT. ACC 09:30 50-lead DND CSV.",
    "OPS-006": f"PILOT 07:10 IST (Sep2 CRON): loop DEAD 48h+ re-confirm (mtime Aug31 08:39:55Z batch211 ok=0/fail=3, proc0, cron0). Restart sign = env swap. 10:30 digest OWED.",
    "GRD-003": f"PILOT 07:10 IST (Sep2 CRON): revenue-truth gap confirmed (snap mrr=5997/active=3 Sep1 18:45 STALE vs ledger Jiya 1999 sole VOIDED tail); 6+1 verdicts 11:00 OWED.",
    "SUC-002": f"PILOT 07:10 IST (Sep2 CRON): Jiya sole payer 1999 churn P0; ACC 12:00 SMTP proof OWED.",
    "ENG-003": f"PILOT 07:10 IST (Sep2 CRON): watchdog missing (crontab 0); ACC 09:30 commit+runbook+watchdog OWED.",
    "BRD-002": f"PILOT 07:10 IST (Sep2 CRON): fresh push abhi (3 files); page verify 12:00 OWED.",
}
n = 0
for t in tasks:
    if t.get("id") in tails:
        t["evidence_tail"] = tails[t["id"]]
        n += 1
save(tp, tasks)
print(f"TASKS: {n} evidence_tail updated")

# ---------- 3) BOTS.JSON ----------
bp = os.path.join(base, "bots.json")
bots = load(bp)
sts = {
    "Pilot": "07:10 IST SWEEP: state UNCHANGED — loop DEAD 48h+ (batch211, proc0, cron0); SIP 5 vars len=0; VOBIZ_CALLER_ID REVOKED len13; WA flip INERT (containers=0 disk=1, owner-restart escalated); WA-sent 0/380; leads/ ABSENT; hot-queue 09-01 43/43; /health UP; egress 000 day5. FLEET 0 ACK — REV-COMMAND + SAL-003 escalate + PLT-004 sent 07:10. Gates 09:00/09:30/10:30/11:00/12:00 IST.",
    "engineering": "ENG-003 P1: watchdog missing (crontab 0). Jio SIP failover runbook + watchdog evidence 09:30 IST. ACK missing.",
    "platform": "PLT-004 P0: egress timeout DAY5; SIP 5 vars len=0 disk+container; VOBIZ_CALLER_ID REVOKED; WA flip INERT (owner-approve). Root-cause + template 09:00 IST. ACK missing.",
    "operations": "OPS-006 P0: loop DEAD 48h+ re-confirm (proc 0, cron 0, mtime Aug31 08:39:55Z). Restart sign = env swap; 10:30 digest. ACK missing.",
    "sales": "SAL-003 P0 BOTTLENECK OWNER: WA manual-send ABHI (WAHA with-key 200 WORKING; hot-queue 09-01 43 UPI; auto_sent 0/380); vendor DID 09:00. ACK missing.",
    "hunter": "HNT-004 P1: leads/ ABSENT re-confirm (0 files); hot-queue Sep2 ABSENT; 50-lead DND CSV 09:30 IST. ACK missing.",
    "guardian": "GRD-003 P1: 6+1 verdicts 11:00 IST (revenue-truth snap STALE vs ledger, loop-dead, WAHA HEALTHY FINAL, auto_sent=0/380, leads-absent, SAL-003 vendor+WA post-09:00, WA-claim). ACK missing.",
    "success": "SUC-002 P0: Jiya only payer 1999 churn-risk; SMTP SENT proof 12:00 IST. REV-105 close-kit standby. ACK missing.",
    "board": "BRD-002 P2: VPS mirror push abhi 07:10; page verify + cadence 12:00. ACK missing.",
}
for k, v in sts.items():
    if k in bots:
        bots[k]["status"] = v
save(bp, bots)
print("BOTS: statuses refreshed")

# ---------- 4) PINNED.JSON ----------
pp = os.path.join(base, "pinned.json")
pin = load(pp)
pin["last_updated"] = now.strftime("%Y-%m-%dT%H:%M+05:30")
pin["vps_status"] = "UP (/health 308 auth-gated; containers Up 41h healthy; DB ok); loop DEAD 48h+ (batch211 REVOKED CLI; proc0 cron0); SIP 5 vars EMPTY; VOBIZ_CALLER_ID REVOKED; egress 000 day5; WA flip INERT (disk=1 containers=0, owner-restart); WA-sent 0/380; leads/ ABSENT; hot-queue 09-01 43/43 present; snap STALE (GRD-003 scope)"
pin["verified_revenue"] = "₹1,999 (Jiya INV/2026-27/0001)"
pin["gap"] = "₹4,98,001"
pin["pipeline"] = "43 HOT WA closes (blocked on execution), 0 dialer connects, 0 WA sends, Jiya P0"
pin["bottleneck"] = "DID gate (SAL-003 09:00) -> WA container flip INERT (owner-restart) + egress (PLT-004 09:00) -> loop+watchdog (OPS/ENG) -> ammo (HNT) -> verdicts (GRD) -> Jiya (SUC)"
pin["action"] = "WA hot-queue manual-send ABHI (WAHA 200 WORKING) + vendor DID chase -> env swap -> 10:00 TRAI batch -> UPI close"
pin["next_expected_payment"] = "WA hot-queue close ya Jiya retention — evidence ke saath, vaada nahi"
save(pp, pin)
print("PINNED: refreshed")
print("DONE")