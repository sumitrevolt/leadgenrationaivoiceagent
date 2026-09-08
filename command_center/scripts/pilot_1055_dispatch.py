#!/usr/bin/env python3
"""PILOT 09-02 10:55 IST sweep — FRESH live evidence (10:50-10:55 IST):
/health 308 auth-gated UP (healthy); call_loop DEAD 50h+ (mtime Aug31 08:39:55Z
batch211 ok=0/fail=3 'from number 911171366938 is not owned', proc0 cron0);
SIP 5 vars len=0 disk (DID NOT landed); VOBIZ_CALLER_ID len13 REVOKED still in .env;
WA flip INERT (containers app+worker=0, disk .env=1; restart pending owner-approve);
auto_sent true=0; HOT-QUEUE 09-02 PRESENT 43 rows (first: AFM SOLAR wa.me deep-link);
leads/ ABSENT (ammo ZERO); egress api.vobiz.com 000@10s DAY5; WAHA container leadgen_waha
UP, sessions 401 with bad-key probe (auth gate), real key 3561...582=200 WORKING (earlier);
revenue_snap 09-01 mrr=5997/active=3 STALE vs ledger Jiya INV/2026-27/0001 sole (GRD-003);
VPS mirror mtime 05:16 STALE vs local 10:45 -> BRD push THIS run.
Fleet ACK 0 since 00:12Z (48h+). Bottleneck: DID never landed; WA rail OPEN but 0 sends.
NO new TASK-ID (anti-spam max1) — rebump SAL-003 + PLT-004 only (P0), REV-COMMAND ALL.
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
     "msg": "🎯 REVENUE COMMAND 10:55 IST (Sep2): TARGET ₹5,00,000 | VERIFIED ₹1,999 (Jiya INV/2026-27/0001 sole; snap mrr=5997 STALE) | GAP ₹4,98,001 | PIPELINE: hot-queue 09-02 PRESENT 43 UPI-tagged warm leads (wa.me deep-links, AFM SOLAR head) + hot-queue 09-01 43; dialer DEAD 50h+ (batch211 REVOKED CLI, proc0 cron0); WA-sent auto_sent true=0; leads/ ammo ZERO | HOT: 86 UPI deep-links pada hua, ZERO bheje | BOTTLENECK: DID never landed (SIP 5 vars len=0) -> WA restart INERT (containers=0 disk=1) -> lekin WAHA sendText door OPEN (leadgen_waha UP; real key 200 WORKING) = manual warm follow-up AAJ KA EXECUTABLE RAIL | ACTION: SAL-003 >=10 sendText ABHI (hot-queue 09-02, wa.me link + UPI deep-link; owner-action queue = DND-safe manual); PLT-004 egress verdict + SIP template; OPS digest; HNT CSV; ENG watchdog; GRD 11:00 verdicts; SUC 12:00 Jiya; BRD mirror push done by PILOT | NEXT: WA sends -> replies -> UPI close -> ledger proof | FLEET: ACK 0 since 00:12Z (48h+) — 10:55 rebump; aur 0 ACK = reassign+owner escalation. Prioritize SAL-003 execution."},
    {"ts": ts, "from": "PILOT", "to": "sales", "task_id": "SAL-003", "type": "ESCALATION", "priority": "P0",
     "msg": "SAL-003 10:55 IST — EXECUTE, reporting nahi. FRESH: hot-queue 09-02 43/43 wa_link+UPI (AFM SOLAR head; deep-links live); WAHA sendText path OPEN (leadgen_waha UP; key 200 WORKING earlier; sessions gate 401 bad-key = good). auto_sent true=0 — 86 UPI deep-links bheje nahi. ACCEPTANCE ABHI: >=10 REAL sendText proof (HTTP 200 + chat id + auto_sent>0 else YOUR WAHA send log) + vendor DID (Call Soft wa.me/917599967999 + RMS 080-47652298). Restart ka wait MAT karo — apna ke do. 0 proof by 11:30 → reassign success+bounty + owner."},
    {"ts": ts, "from": "PILOT", "to": "platform", "task_id": "PLT-004", "type": "ESCALATION", "priority": "P0",
     "msg": "PLT-004 10:55 IST — FRESH: /health 308 auth-gated UP; SIP 5 vars len=0 (DID NAHI); VOBIZ_CALLER_ID len13 REVOKED in .env; egress api.vobiz.com 000@10s DAY5 re-confirm; WA flip INERT (disk=1 containers=0) — restart owner-approve. ACCEPTANCE: egress verdict + re-test proof + Jio SIP env-swap template (5 vars) + restart plan. 0 proof 11:30 → owner escalation with exact docker command."},
]
with open(os.path.join(base, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in lines:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print(f"LEDGER: {len(lines)} appended @ {ts}")

# ---------- 2) TASKS.JSON — status + evidence_tail ----------
tp = os.path.join(base, "tasks.json")
tasks = load(tp)
updates = {
    "SAL-003": {"status": "BLOCKED", "evidence_tail": "PILOT 10:55 IST (Sep2 CRON): hot-queue 09-02 PRESENT 43/43 (AFM SOLAR head, wa_link+UPI); auto_sent true=0; WAHA sendText OPEN (bad-key 401 gate = healthy; real key 200 earlier). 0 ACK/0 sends. 86 UPI deep-links undelivered. Rebump 10:55; 11:30 reassign."},
    "PLT-004": {"status": "BLOCKED", "evidence_tail": "PILOT 10:55 IST (Sep2 CRON): FRESH — SIP 5 vars len=0; VOBIZ_CALLER_ID REVOKED len13; egress 000@10s DAY5; WA flip INERT (containers=0 disk=1); /health 308 auth-gated UP. egress verdict + SIP template outstanding. 11:30 owner-escalate."},
    "OPS-006": {"status": "UPDATE", "evidence_tail": "PILOT 10:55 IST (Sep2 CRON): loop DEAD 50h+ re-confirm (mtime Aug31 08:39:55Z batch211 ok=0/fail=3, proc0, cron0); hot-queue 09-02 PRESENT (03:30 gen, 43 rows). 10:30 digest ABHI OWED (gates miss pattern = reassign risk)."},
    "ENG-003": {"status": "BLOCKED", "evidence_tail": "PILOT 10:55 IST (Sep2 CRON): watchdog absent (crontab 0); loop DEAD 50h+ bina watchdog. commit+runbook+watchdog OWED since 09:30."},
    "HNT-004": {"status": "BLOCKED", "evidence_tail": "PILOT 10:55 IST (Sep2 CRON): leads/ ABSENT (ammo ZERO); hot-queue 09-02 43-lead = CSV+pool conversion source. 50-lead DND CSV OWED since 09:30."},
    "GRD-003": {"status": "UPDATE", "evidence_tail": "PILOT 10:55 IST (Sep2 CRON): 11:00 gate IMMINENT — 6+1 verdicts (revenue-truth, loop-dead, WAHA HEALTHY w/ bad-key 401 note, auto_sent=0, leads-absent, hot-queue-09-02 PRESENT, SAL-003 vendor+WA)."},
    "SUC-002": {"status": "UPDATE", "evidence_tail": "PILOT 10:55 IST (Sep2 CRON): Jiya sole payer 1,999; 12:00 SMTP SENT proof OWED. DID-independent."},
    "BRD-002": {"status": "UPDATE", "evidence_tail": "PILOT 10:55 IST (Sep2 CRON): VPS mirror mtime 05:16 STALE vs local 10:45 — PILOT pushes 4 files this run (tasks/bots/pinned/messages). Page verify + cadence ow OWED 12:00."},
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
print(f"TASKS: {n} updated")

# ---------- 3) BOTS.JSON ----------
bp = os.path.join(base, "bots.json")
bots = load(bp)
sts = {
    "Pilot": "10:55 IST SWEEP: /health 308 auth-gated UP; loop DEAD 50h+ (mtime Aug31 08:39:55Z batch211 REVOKED CLI; proc0 cron0); SIP 5 vars len=0; VOBIZ_CALLER_ID REVOKED; WA flip INERT (containers=0 disk=1); auto_sent 0; HOT-QUEUE 09-02 PRESENT 43/43; leads/ ABSENT; egress 000 DAY5; mirror push now. 2 rays alive: WA sendText + Jiya retention. FLEET ACK 0 48h+.",
    "engineering": "ENG-003 BLOCKED: 09:30 MISSED, ACK 0; watchdog absent (crontab 0); loop DEAD 50h+ bina watchdog. commit+runbook+watchdog OWED.",
    "platform": "PLT-004 BLOCKED: 09:00 MISSED, ACK 0; SIP 5 vars len=0; egress 000 DAY5; VOBIZ_CALLER_ID REVOKED; egress verdict + SIP template OWED; 11:30 owner-escalate.",
    "operations": "OPS-006 UPDATE: loop DEAD 50h+; hot-queue 09-02 PRESENT; 10:30 digest OWED (gates miss = reassign risk).",
    "sales": "SAL-003 BLOCKED BOTTLENECK OWNER: 09:00 MISSED, ACK 0, 0 sends. WAHA sendText OPEN + hot-queue 09-02 43 UPI = EXECUTE >=10 ABHI, 11:30 reassign risk.",
    "hunter": "HNT-004 BLOCKED: 09:30 MISSED, ACK 0; leads/ ABSENT; hot-queue 09-02 as ammo source; 50-lead CSV OWED.",
    "guardian": "GRD-003 UPDATE: 6+1 verdicts 11:00 (revenue-truth, loop-dead, WAHA HEALTHY, auto_sent, leads, hot-queue 09-02 PRESENT, SAL-003).",
    "success": "SUC-002 UPDATE: Jiya sole payer 1,999 P0; SMTP SENT proof 12:00. REV-105 standby.",
    "board": "BRD-002 UPDATE: PILOT push 4 files now (mirror 05:16 STALE); page verify + cadence 12:00. Visualization only.",
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
pin["vps_status"] = "UP (/health 308 auth-gated); loop DEAD 50h+ (batch211 REVOKED CLI; proc0 cron0); SIP 5 vars len=0; VOBIZ_CALLER_ID REVOKED; WA flip INERT (containers=0 disk=1); auto_sent 0; HOT-QUEUE 09-02 PRESENT 43/43 (03:30 gen); leads/ ABSENT; egress 000 DAY5"
pin["verified_revenue"] = "₹1,999 (Jiya INV/2026-27/0001)"
pin["target"] = "₹5,00,000"
pin["gap"] = "₹4,98,001"
pin["bottleneck"] = "DID never landed (SIP 5 vars len=0) -> WA restart INERT (owner) -> 86 WA UPI deep-links ZERO sends (SAL-003) -> fleet ACK 0 48h+"
pin["pipeline"] = "86 HOT UPI deep-links (queues 09-01+09-02), 0 WA sends, 0 dialer connects, Jiya P0"
pin["hot"] = "hot-queue 09-02 43 UPI warm leads (SAL-003 ABHI) + Jiya retention (SUC-002 12:00)"
pin["action"] = "SAL-003 >=10 sendText ABHI (WAHA OPEN; hot-queue 09-02 wa_link+UPI); PLT-004 egress verdict+SIP template; owner: restart approval for WA flip"
pin["next_expected_payment"] = "WA sendText reply -> UPI close ya Jiya retention — evidence ke saath"
save(pp, pin)
print("PINNED: refreshed")
print("DONE")