#!/usr/bin/env python3
"""PILOT 09-02 06:10 IST sweep — FRESH live evidence (00:40Z):
/health 200; call loop DEAD 48h+ (batch 211 mtime Aug31 08:39:55Z, proc 0, cron 0);
SIP_HOST/USERNAME/PASSWORD/DID/PROVIDER len=0 (DID NOT landed); VOBIZ_CALLER_ID len=13 REVOKED;
containers leadgen_worker+leadgen_app SALES_AUTOPILOT_WHATSAPP_ENABLED=0 INERT (disk .env=1);
reply_drafts auto_sent true=0/false=378; leads/ ABSENT; hot_queue 09-01 43 present (09-02 ABSENT);
egress api.vobiz.com 000 @6.0s (day5); WAHA no-key 401 expected gate.
FLEET still 0 ACK. All 8 active UPDATE, no new TASK-ID (anti-spam)."""
import json, os
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
now = datetime.now(IST)
ts = now.strftime("%Y-%m-%dT%H:%M:%S+05:30")
ts_short = now.strftime("%H:%M")
base = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)
def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")

# ---------- 1) LEDGER APPEND (compact) ----------
ledger_path = os.path.join(base, "messages.jsonl")
lines = [
    {"ts": ts, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": f"🎯 REVENUE COMMAND {ts_short} IST (Sep2): TARGET ₹5,00,000 | VERIFIED ₹1,999 (Jiya INV-0001 sole) | GAP ₹4,98,001 | PIPELINE: hot-queue 09-01 43/43 wa_link+UPI (09-02 ABSENT), dialer 0 connects (loop DEAD 48h+, batch211 REVOKED CLI, proc0 cron0), WA-sent 0 (auto_sent true=0/378) | HOT: 43 WA closes + Jiya P0 | BOTTLENECK: DID gate (SAL-003 09:00; SIP 5 vars len=0) -> Vobiz egress 000 d5 + WA container flip INERT (PLT-004 09:00) -> loop+watchdog (OPS-006 10:30 / ENG-003 09:30) -> ammo (HNT-004 09:30) | ACTION: WA manual-send ABHI (WAHA with-key 200 WORKING; hot-queue 43 UPI deep-links), vendor DID follow-up; gates 09:00-12:00 IST | NEXT: 09:00 vendor DID + WA>=10 -> env swap -> 10:00 TRAI batch -> pehla UPI close | FLEET 0 ACK since 00:12Z — poll messages.jsonl, ACK TASK-ID + evidence file. Fresh 06:10 sweep filed."},
    {"ts": ts, "from": "PILOT", "to": "sales", "task_id": "SAL-003", "type": "REINFORCE", "priority": "P0",
     "msg": f"SAL-003 ({ts_short}) NO NEW TASK-ID. FRESH: 06:10 sweep — SIP vars ab bhi len=0, DID nahi. WAHA path OPEN (with-key 200). ACC 09:00 BOTH: >=10 WA-send real proof + vendor DID number (Call Soft + RMS dono tracks). YEHI SINGLE REVENUE RAIL HAI — EXECUTE ABHI. ACK SAL-003."},
    {"ts": ts, "from": "PILOT", "to": "platform", "task_id": "PLT-004", "type": "REINFORCE", "priority": "P0",
     "msg": f"PLT-004 ({ts_short}) NO NEW TASK-ID. FRESH 06:10: egress api.vobiz.com 000 @6.0s (day5); SIP 5 vars len=0; VOBIZ_CALLER_ID 13 REVOKED in .env; WA flip INERT (containers WA=0, disk=1). ACC 09:00: egress verdict + re-test + Jio SIP env swap template + restart-approval escalation. ACK PLT-004."},
    {"ts": ts, "from": "PILOT", "to": "operations", "task_id": "OPS-006", "type": "REINFORCE", "priority": "P0",
     "msg": f"OPS-006 ({ts_short}) loop DEAD 48h+ (mtime Aug31 08:39:55Z batch211 ok=0/fail=3, proc0, cron0). Restart sign = PLT-004 env swap. 10:30 IST digest. ACK OPS-006."},
    {"ts": ts, "from": "PILOT", "to": "engineering", "task_id": "ENG-003", "type": "REINFORCE", "priority": "P1",
     "msg": f"ENG-003 ({ts_short}) watchdog MISSING (crontab 0; loop 48h+ dead bina restart). Spec: TRAI window log mtime >10min stale + no proc => alert+restart (sirf owned caller-ID). Jio SIP failover runbook + WAHA probe pattern. ACC 09:30: commit + runbook + watchdog evidence. ACK ENG-003."},
    {"ts": ts, "from": "PILOT", "to": "hunter", "task_id": "HNT-004", "type": "REINFORCE", "priority": "P1",
     "msg": f"HNT-004 ({ts_short}) leads/ ABSENT re-confirm 06:10 (No such file). Ammo ZERO 5+ din; hot-queue Sep2 ABSENT. ACC 09:30: CSV path + 50 MOBILE + DND-proof + pool refill. ACK HNT-004."},
    {"ts": ts, "from": "PILOT", "to": "guardian", "task_id": "GRD-003", "type": "REINFORCE", "priority": "P1",
     "msg": f"GRD-003 ({ts_short}) 6 verdicts due 11:00 PASS/FAIL + evidence file: (1) revenue-truth (snap mrr=5997/active=3 vs ledger Jiya 1999 sole; tail VOIDED), (2) loop-dead, (3) leads-absent, (4) auto_sent=0/378, (5) WAHA HEALTHY FINAL, (6) SAL-003 vendor DID+WA>=10 post-09:00. ACK GRD-003."},
    {"ts": ts, "from": "PILOT", "to": "success", "task_id": "SUC-002", "type": "REINFORCE", "priority": "P0",
     "msg": f"SUC-002 ({ts_short}) Jiya sole payer ₹1,999 churn P0. DID-independent. ACC 12:00: SMTP SENT artifact + WA follow-up + reply. REV-105 close-kit standby. ACK SUC-002."},
    {"ts": ts, "from": "PILOT", "to": "board", "task_id": "BRD-002", "type": "REINFORCE", "priority": "P2",
     "msg": f"BRD-002 ({ts_short}) PILOT fresh 3-file push abhi (06:10). Tera kaam: live page display verify + 30-min cadence. ACC 12:00: page-check evidence. ACK BRD-002."},
]
with open(ledger_path, "a", encoding="utf-8") as f:
    for ln in lines:
        f.write(json.dumps(ln, ensure_ascii=False) + "\n")
print(f"LEDGER: {len(lines)} appended @ {ts}")

# ---------- 2) TASKS.JSON EVIDENCE ----------
tasks_path = os.path.join(base, "tasks.json")
tasks = load(tasks_path)
note = {
    "SAL-003": f"{ts} PILOT {ts_short}: SIP vars ab bhi len=0; WAHA path OPEN (with-key 200); ACC 09:00 WA>=10 + vendor DID.",
    "PLT-004": f"{ts} PILOT {ts_short}: /health 200; egress 000 @6.0s day5; SIP 5 len=0; VOBIZ_CALLER_ID len13 REVOKED; WA flip INERT; ACC 09:00.",
    "OPS-006": f"{ts} PILOT {ts_short}: loop DEAD 48h+ (batch211, proc0, cron0); 10:30 digest.",
    "ENG-003": f"{ts} PILOT {ts_short}: watchdog missing (crontab 0); 09:30 commit+runbook+watchdog.",
    "HNT-004": f"{ts} PILOT {ts_short}: leads/ ABSENT; Sep2 hot-queue ABSENT; 09:30 50-lead DND CSV.",
    "GRD-003": f"{ts} PILOT {ts_short}: revenue-truth gap confirmed; WAHA=FINAL HEALTHY; 6 verdicts 11:00.",
    "SUC-002": f"{ts} PILOT {ts_short}: Jiya sole payer 1999; ACC 12:00 SMTP proof.",
    "BRD-002": f"{ts} PILOT {ts_short}: fresh push abhi; page verify 12:00.",
}
n = 0
for t in tasks:
    if t.get("id") in note:
        ev = t.get("evidence", "")
        t["evidence"] = (ev + " || " + note[t["id"]]) if ev else note[t["id"]]
        n += 1
save(tasks_path, tasks)
print(f"TASKS: {n} evidence-updated")

# ---------- 3) BOTS.JSON ----------
bots_path = os.path.join(base, "bots.json")
bots = load(bots_path)
bots["Pilot"]["status"] = (f"{ts_short} IST SWEEP: state UNCHANGED — loop DEAD 48h+ (batch211, proc0, cron0); "
                           f"SIP 5 vars len=0 (DID NOT landed); VOBIZ_CALLER_ID REVOKED len13; WA flip INERT "
                           f"(containers=0 disk=1); WA-sent 0/378; leads/ ABSENT; egress 000 d5; /health 200; "
                           f"hot-queue 09-01 43/43. FLEET 0 ACK — REINFORCE {ts_short} sent. Gates 09:00-12:00 IST.")
bots["sales"]["status"] = f"SAL-003 P0: WA manual-send ABHI (WAHA with-key 200; hot-queue 43 UPI; auto_sent 0); vendor DID 09:00. ACK missing."
save(bots_path, bots)
print("BOTS: Pilot+sales refreshed")

# ---------- 4) PINNED.JSON ----------
pinned_path = os.path.join(base, "pinned.json")
pinned = load(pinned_path)
pinned["last_updated"] = now.strftime("%Y-%m-%dT%H:%M+05:30")
pinned["vps_status"] = "HEALTHY (/health 200); loop DEAD 48h+ (batch211 REVOKED CLI; proc0 cron0); SIP 5 vars EMPTY; VOBIZ_CALLER_ID REVOKED; egress 000 day5; WA container flip INERT (disk=1 containers=0); WA-sent 0/378; leads/ ABSENT; hot-queue 09-01 43 present"
pinned["verified_revenue"] = "₹1,999 (Jiya INV/2026-27/0001)"
pinned["gap"] = "₹4,98,001"
pinned["pipeline"] = "43 HOT WA closes (blocked), 0 dialer connects, 0 WA sends, Jiya P0"
pinned["bottleneck"] = "DID gate (SAL-003 09:00) -> SIP swap (PLT-004 09:00) -> loop+watchdog (OPS/ENG) -> ammo (HNT) -> verify (GRD) -> Jiya (SUC)"
pinned["action"] = "WA hot-queue manual-send ABHI (WAHA 200 WORKING) + vendor DID -> env swap -> 10:00 TRAI batch -> UPI close"
pinned["next_expected_payment"] = "WA hot-queue close ya Jiya retention — evidence ke saath, vaada nahi"
save(pinned_path, pinned)
print("PINNED: refreshed")
print("DONE")