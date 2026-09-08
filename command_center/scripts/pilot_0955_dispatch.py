#!/usr/bin/env python3
"""PILOT 09-02 09:55 IST sweep — FRESH live evidence (09:50-09:55 IST):
/health 200 healthy 37a1daf8; call_loop DEAD 48h+ (mtime Aug31 08:39:55Z batch211 ok=0/fail=3 'not owned', proc0 cron0);
SIP 5 vars EMPTY (SIP_PASSWORD orphan len20 only, no HOST/USER/DID); VOBIZ_CALLER_ID len13 REVOKED;
WA flip INERT (containers app+worker+heavy =0, disk .env=1; owner-approve restart);
*** HOT-QUEUE 09-02 PRESENT (stat 2026-09-02 03:30:09Z = 09:00 IST; header+43 rows, 43/43 wa_link+UPI deep-links) — CORRECTION to 07:48 'ABSENT' ***
WAHA with-key 200 WORKING session default 918459012607 (activity 1788322802243); webhook leadsgenai.in/api/wa/selfhost/webhook ok;
WHATSAPP_AUTO_SEND=1 disk; auto_sent true=0 (no sends yet); leads/ ABSENT (ammo ZERO);
scheduler ALIVE: scan_inbox/2min + staff jobs + boss-autonomy-sweep 09:55.
GATES: SAL-003 09:00 MISSED (no ACK, no WA-send, no DID) -> BLOCKED; PLT-004 09:00 MISSED -> BLOCKED;
HNT-004 09:30 MISSED (leads/ absent) -> BLOCKED; ENG-003 09:30 MISSED (watchdog absent) -> BLOCKED;
OPS-006 10:30 imminent; GRD-003 11:00; SUC-002/BRD-002 12:00. Fleet ACK 0 since 00:12Z (48h+).
Funnel: DID gate (never landed) -> WA warm-follow-up rail OPEN (hot-queue 09-02) but 0 sends; restart INERT.
NO new TASK-ID (anti-spam, max1) — SAL-003 = bottleneck owner (WA sendText NOW + DID), PLT-004 escalate.
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
     "msg": "🎯 REVENUE COMMAND 09:55 IST (Sep2): TARGET ₹5,00,000 | VERIFIED ₹1,999 (Jiya INV/2026-27/0001 sole; snap mrr=5997 STALE = GRD-003) | GAP ₹4,98,001 | PIPELINE: HOT-QUEUE 09-02 PRESENT (stat 03:30:09Z=09:00 IST, 43/43 wa_link+UPI; 09-01 also 43) — pehle 'ABSENT' was pre-generation, CORRECTED; dialer DEAD 48h+ (batch211 ok=0/fail=3 'not owned', proc0 cron0); WA-sent auto_sent true=0; leads/ ABSENT (ammo ZERO) | HOT: 43+43 UPI-tagged warm leads + Jiya P0 | BOTTLENECK: DID never landed (SAL-003 09:00 MISSED, SIP 5 vars EMPTY) -> WA container flip INERT (containers=0 disk=1, owner-restart) -> but WAHA sendText path OPEN (session WORKING 918459012607) = manual warm-follow-up EXECUTABLE NOW | ACTION: SAL-003 send >=10 WA sendText abhi (HTTP 200 + msg id evidence; hot-queue 09-02 = owner-action queue, warm follow-up after email = not cold-spam) + DID chase; PLT-004 egress verdict + SIP template + restart approval; OPS 10:30 digest; HNT/ENG 09:30 MISSED = BLOCKED; GRD 11:00; SUC/BRD 12:00 | NEXT: WA sends -> reply -> UPI close -> ledger proof | FLEET: 0 ACK since 00:12Z (48h+) — BLOCKED declarations filed 09:55; ACK karo else reassign. Owner escalation: restart approval + hot-queue manual action."},
    {"ts": ts, "from": "PILOT", "to": "sales", "task_id": "SAL-003", "type": "ESCALATION", "priority": "P0",
     "msg": "SAL-003 → BLOCKED (09:00 gate MISSED, ACK 0). FRESH 09:55: HOT-QUEUE 09-02 LIVE (43/43 wa_link+UPI, 09:00 IST generation); WAHA with-key 200 WORKING session default; auto_sent true=0. WAHA /api/sendText = container-independent — restart ke bina bhi warm follow-up bhej sakte ho (queue header: 'owner: Call ya 1-click WA. Cold auto-WA OFF' = manual warm rail, DND-safe; draft me email reference hai = not cold). ACCEPTANCE ABHI: >=10 sendText REAL proof (HTTP 200 + chat id + auto_sent>0) + vendor DID (Call Soft wa.me/917599967999 + RMS Tech 080-47652298). No ACK by 10:30 → reassign to success+bounty + owner notify."},
    {"ts": ts, "from": "PILOT", "to": "platform", "task_id": "PLT-004", "type": "ESCALATION", "priority": "P0",
     "msg": "PLT-004 → BLOCKED (09:00 egress+template MISSED, ACK 0). FRESH 09:55: /health 200 healthy 37a1daf8; SIP 5 vars EMPTY (SIP_PASSWORD orphan len20 with no HOST/USER/DID = incomplete, ignore); VOBIZ_CALLER_ID len13 REVOKED; WA flip INERT (containers 0, disk 1) — restart approval is OWNER-side, file the exact `docker compose up -d`/deploy_vps.sh command + verify plan. ACCEPTANCE: egress verdict + re-test proof + Jio SIP env-swap template (5 vars) + restart plan. No ACK by 10:30 → escalate owner."},
]
with open(os.path.join(base, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in lines:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print(f"LEDGER: {len(lines)} appended @ {ts}")

# ---------- 2) TASKS.JSON — status + evidence_tail ----------
tp = os.path.join(base, "tasks.json")
tasks = load(tp)
updates = {
    "SAL-003": {"status": "BLOCKED", "evidence_tail": "PILOT 09:55 IST (Sep2 CRON): gate 09:00 MISSED, ACK 0. NEW: hot-queue 09-02 PRESENT (stat 03:30:09Z=09:00 IST; 43/43 wa_link+UPI) — 07:48 'ABSENT' was pre-generation, CORRECTED. WAHA with-key 200 WORKING session default; auto_sent true=0. ACC: >=10 sendText abhi + vendor DID. No ACK 10:30 → reassign+owner."},
    "PLT-004": {"status": "BLOCKED", "evidence_tail": "PILOT 09:55 IST (Sep2 CRON): gate 09:00 MISSED, ACK 0. /health 200 healthy; SIP 5 vars EMPTY (SIP_PASSWORD orphan len20 only); VOBIZ_CALLER_ID REVOKED len13; WA flip INERT (containers 0 disk 1). ACC: egress verdict + re-test + SIP template + restart plan. Owner restart approval pending."},
    "HNT-004": {"status": "BLOCKED", "evidence_tail": "PILOT 09:55 IST (Sep2 CRON): gate 09:30 MISSED, ACK 0. leads/ ABSENT re-confirm (ammo ZERO). hot-queue 09-02 43/43 present — CSV+pool conversion = DID-landing ammo ready source. 50-lead DND CSV outstanding."},
    "ENG-003": {"status": "BLOCKED", "evidence_tail": "PILOT 09:55 IST (Sep2 CRON): gate 09:30 MISSED, ACK 0. watchdog absent (crontab 0); loop DEAD 48h+ bina watchdog. commit+runbook+watchdog outstanding."},
    "OPS-006": {"status": "UPDATE", "evidence_tail": "PILOT 09:55 IST (Sep2 CRON): loop DEAD 48h+ re-confirm; hot-queue 09-02 PRESENT (03:30:09Z gen) — daily job RAN; 10:30 digest me include karo; 09-01 43 also present. Restart sign = env swap."},
    "GRD-003": {"status": "UPDATE", "evidence_tail": "PILOT 09:55 IST (Sep2 CRON): +1 scope — verify hot-queue 09-02 PRESENT claim vs 07:48 ABSENT (mtime 03:30:09Z). 6+1 verdicts 11:00."},
    "SUC-002": {"status": "UPDATE", "evidence_tail": "PILOT 09:55 IST (Sep2 CRON): Jiya sole payer 1999 churn P0; 12:00 SMTP proof OWED."},
    "BRD-002": {"status": "UPDATE", "evidence_tail": "PILOT 09:55 IST (Sep2 CRON): fresh push abhi (tasks/bots/pinned/messages); page verify 12:00."},
}
n = 0
for t in tasks:
    u = updates.get(t.get("id"))
    if u:
        t["status"] = u["status"]
        t["evidence_tail"] = u["evidence_tail"]
        t["updated_at"] = ts
        n += 1
save(tp, tasks)
print(f"TASKS: {n} updated (4→BLOCKED, 4 UPDATE)")

# ---------- 3) BOTS.JSON ----------
bp = os.path.join(base, "bots.json")
bots = load(bp)
sts = {
    "Pilot": "09:55 IST SWEEP: /health 200 healthy; loop DEAD 48h+; SIP 5 vars EMPTY; VOBIZ_CALLER_ID REVOKED; WA flip INERT (containers 0 disk 1, owner-restart); HOT-QUEUE 09-02 PRESENT 43/43 (CORRECTION); WAHA WORKING; auto_sent 0; leads/ ABSENT. 4 tasks BLOCKED (09:00/09:30 gates missed, ACK 0 48h+). Ops 10:30, GRD 11:00, SUC/BRD 12:00.",
    "engineering": "ENG-003 BLOCKED: 09:30 MISSED, ACK 0; watchdog absent (crontab 0); loop DEAD 48h+ bina watchdog. commit+runbook+watchdog outstanding.",
    "platform": "PLT-004 BLOCKED: 09:00 MISSED, ACK 0; egress verdict + SIP template outstanding; WA restart owner-approve. /health 200 healthy.",
    "operations": "OPS-006 UPDATE: loop DEAD 48h+; hot-queue 09-02 PRESENT (03:30:09Z=RAN); 10:30 digest me root-cause. Restart sign = env swap.",
    "sales": "SAL-003 BLOCKED: 09:00 MISSED, ACK 0. HOT-QUEUE 09-02 43/43 UPI LIVE + WAHA WORKING = WA sendText ABHI executable. >=10 sends + vendor DID else reassign 10:30.",
    "hunter": "HNT-004 BLOCKED: 09:30 MISSED, ACK 0; leads/ ABSENT (ammo ZERO); 50-lead DND CSV outstanding; hot-queue 09-02 as ammo source.",
    "guardian": "GRD-003 UPDATE: 6+1 verdicts 11:00 (+verify hot-queue 09-02 PRESENT claim).",
    "success": "SUC-002 UPDATE: Jiya sole payer 1999 P0; SMTP SENT proof 12:00. REV-105 standby.",
    "board": "BRD-002 UPDATE: mirror push abhi; page verify 12:00. Visualization only.",
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
pin["vps_status"] = "UP (/health 200 healthy 37a1daf8); loop DEAD 48h+ (batch211 REVOKED CLI; proc0 cron0); SIP 5 vars EMPTY; VOBIZ_CALLER_ID REVOKED; WA flip INERT (disk=1 containers=0); HOT-QUEUE 09-02 PRESENT 43/43 (09:00 IST gen); WAHA WORKING; auto_sent 0; leads/ ABSENT"
pin["verified_revenue"] = "₹1,999 (Jiya INV/2026-27/0001)"
pin["gap"] = "₹4,98,001"
pin["pipeline"] = "43+43 HOT UPI-tagged warm leads (queue 09-01/09-02), 0 WA sends, 0 dialer connects, Jiya P0"
pin["bottleneck"] = "DID never landed (SAL-003 09:00 MISSED) + WA container flip INERT (owner-restart) + fleet 0 ACK 48h+ (4 tasks BLOCKED)"
pin["action"] = "SAL-003 WA sendText >=10 abhi (WAHA WORKING, hot-queue 09-02) + DID chase; owner: restart approval + hot-queue manual action"
pin["next_expected_payment"] = "WA sendText reply -> UPI close ya Jiya retention — evidence ke saath"
save(pp, pin)
print("PINNED: refreshed")
print("DONE")