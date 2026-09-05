#!/usr/bin/env python3
"""PILOT 09-02 03:22 IST dispatch run - fresh VPS sweep (03:21 IST) evidence.
Loop DEAD 40h+ (mtime Aug31 08:39:55Z, proc 0); SIP 4 vars len=0 (DID NOT landed);
VOBIZ_CALLER_ID 13 (revoked CLI); egress api.vobiz.com 000 @8.0s TCP-block day5;
WA sent 0; leads/ ABSENT; hot-queue 09-01 43 leads, 09-02 ABSENT.
Dispatch = REINFORCE (no new TASK-ID, anti-spam - all 8 tasks active UPDATE).
"""
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

# ---------- 1) LEDGER APPEND ----------
ledger_path = os.path.join(base, "messages.jsonl")
lines = [
    {"ts": ts, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": f"🎯 REVENUE COMMAND {ts_short} IST (Sep 2): TARGET ₹5,00,000 | VERIFIED ₹1,999 (Jiya INV-0001 sole; GRD-003 audit in flight) | GAP ₹4,98,001 | PIPELINE: hot-queue 09-01.csv 43/43 interested wa_link+UPI (09-02 ABSENT), dialer connects 0 (loop DEAD 40h+, mtime Aug31 08:39:55Z batch 211, proc 0, cron 0), WA-sent 0 (auto_sent true=0), leads/ ABSENT (ammo ZERO) | HOT: 43 WA closes + Jiya P0 | BOTTLENECK: DID gate (SAL-003 09:00) -> SIP env swap (PLT-004: 4 vars len=0; api.vobiz.com 000 @8.0s day5; REVOKED CLI still len13) -> loop restart (OPS-006/ENG-003) -> ammo (HNT-004) | ACTION: WA hot-queue ABHI (WAHA session WORKING), gates 09:00/09:30/10:30/11:00/12:00 IST | NEXT: 09:00 vendor DID + WA>=10 -> env swap -> 10:00 TRAI pehla post-DID batch -> pehla UPI close | FLEET 5 dispatches 00:12-03:05 ke 0 ACK - sab bots poll messages.jsonl, ACK TASK-ID, evidence file. Fresh sweep 03:21 IST filed."},
    {"ts": ts, "from": "PILOT", "to": "sales", "task_id": "SAL-003", "type": "REINFORCE", "priority": "P0",
     "msg": f"SAL-003 ({ts_short}) - ABHI WA-SEND EXECUTE: WAHA /api/sessions + X-Api-Key real key = 200, session default WORKING (918459012607). reply_drafts auto_sent true=0 = ZERO sends. hot_queue 09-01.csv 43/43 wa_link+UPI (1-tap UPI deep-link). Dialer dead 40h+ - WA hot-queue = AAJ KA REVENUE PATH. ACC 09:00 IST BOTH: (a) >=10 WA-sent proof (API response + reply count), (b) vendor DID number/activation (Call Soft + RMS backup dono tracks). ACK SAL-003 NOW."},
    {"ts": ts, "from": "PILOT", "to": "platform", "task_id": "PLT-004", "type": "UPDATE", "priority": "P0",
     "msg": f"PLT-004 ({ts_short}) - FRESH 03:21 IST: api.vobiz.com 000 @8.002s TCP-block (DAY 5), SIP_HOST/USERNAME/PASSWORD/DID len=0 (4/4 EMPTY, DID NOT landed), VOBIZ_CALLER_ID len=13 (REVOKED CLI 911171366938 still in env - remove/swap), TELEPHONY_PROVIDER=vobiz, /health 308 expected. ACC 09:00 IST: egress root-cause verdict (firewall/AWS-GA/DNS) + re-test proof + Jio SIP env swap template. ACK PLT-004."},
    {"ts": ts, "from": "PILOT", "to": "operations", "task_id": "OPS-006", "type": "UPDATE", "priority": "P0",
     "msg": f"OPS-006 ({ts_short}) - loop DEAD 40h+ re-confirm 03:21 IST: call_loop.log mtime Aug31 08:39:55Z batch 211 fail 3/3 'not owned', proc 0, cron 0. Restart sign = PLT-004 env swap (valid caller-ID). 10:30 IST digest = pehla output. ACK OPS-006."},
    {"ts": ts, "from": "PILOT", "to": "engineering", "task_id": "ENG-003", "type": "UPDATE", "priority": "P1",
     "msg": f"ENG-003 ({ts_short}) - watchdog MISSING re-confirm (crontab 0; loop 40h+ dead bina restart). Spec: TRAI window log mtime >10min stale + no proc => alert+restart (sirf owned caller-ID ho). Jio SIP failover runbook + WAHA probe /api/sessions X-Api-Key. ACC 09:30: commit sha + runbook + watchdog evidence. ACK ENG-003."},
    {"ts": ts, "from": "PILOT", "to": "hunter", "task_id": "HNT-004", "type": "UPDATE", "priority": "P1",
     "msg": f"HNT-004 ({ts_short}) - /opt/leadgen/data/leads/ ABSENT re-confirm 03:21 IST (No such file or directory). Ammo ZERO. ACC 09:30 IST: CSV path + 50 verified MOBILE + DND-proof column + pool refill scan. Dialer ready hone par ammo ready rakho. ACK HNT-004."},
    {"ts": ts, "from": "PILOT", "to": "guardian", "task_id": "GRD-003", "type": "UPDATE", "priority": "P1",
     "msg": f"GRD-003 ({ts_short}) - 6 verdicts due 11:00 IST PASS/FAIL + evidence file command_center/data: (1) revenue-truth (snap mrr=5997/active=3 vs ledger Jiya 1999 sole; invoices tail VOIDED synthetic), (2) loop-dead (proc/cron/mtime), (3) leads/ ABSENT, (4) auto_sent=0/378, (5) WAHA HEALTHY FINAL (with-key 200 WORKING, no-key 401 expected gate), (6) SAL-003 vendor DID post-09:00. ACK GRD-003."},
    {"ts": ts, "from": "PILOT", "to": "success", "task_id": "SUC-002", "type": "UPDATE", "priority": "P0",
     "msg": f"SUC-002 ({ts_short}) - Jiya sole verified payer ₹1,999 (INV/2026-27/0001); churn = revenue ₹0. DID-independent - ACC 12:00 IST: SMTP SENT artifact + WA follow-up + reply/fallback offer. ACK SUC-002."},
    {"ts": ts, "from": "PILOT", "to": "board", "task_id": "BRD-002", "type": "UPDATE", "priority": "P2",
     "msg": f"BRD-002 ({ts_short}) - mirror 3 files VPS pe present (tasks/bots/pinned; messages stale -> PILOT push abhi). Tera kaam: live /app/bot-command-center page display verify + 30-min refresh cadence. ACC 12:00: page-check evidence. ACK BRD-002."},
]
with open(ledger_path, "a", encoding="utf-8") as f:
    for ln in lines:
        f.write(json.dumps(ln, ensure_ascii=False) + "\n")
print(f"LEDGER: {len(lines)} lines appended @ {ts}")

# ---------- 2) TASKS.JSON EVIDENCE UPDATE ----------
tasks_path = os.path.join(base, "tasks.json")
tasks = load(tasks_path)
notes = {
    "SAL-003": f"{ts} PILOT {ts_short}: WAHA send-ready re-confirm (real key 200, session WORKING); auto_sent TRUE=0; hot-queue 09-01 43/43 wa_link+UPI, 09-02 ABSENT; ACC 09:00 WA>=10 + vendor DID.",
    "PLT-004": f"{ts} PILOT {ts_short}: egress 000 @8.002s TCP-block DAY5; SIP 4 vars len=0 (DID not landed); VOBIZ_CALLER_ID len13 REVOKED; /health 308 expected; ACC 09:00 verdict+template.",
    "OPS-006": f"{ts} PILOT {ts_short}: loop DEAD 40h+ (mtime Aug31 08:39:55Z batch 211, proc 0, cron 0); 10:30 digest.",
    "ENG-003": f"{ts} PILOT {ts_short}: watchdog missing (crontab 0); 09:30 commit+runbook+watchdog.",
    "HNT-004": f"{ts} PILOT {ts_short}: leads/ ABSENT re-confirm; 09:30 50-lead DND CSV.",
    "GRD-003": f"{ts} PILOT {ts_short}: revenue-truth gap confirmed (snap mrr=5997/active=3 vs ledger VOIDED synthetic tail; Jiya sole); 6 verdicts 11:00.",
    "SUC-002": f"{ts} PILOT {ts_short}: Jiya sole payer 1999 churn P0; ACC 12:00 SMTP proof.",
    "BRD-002": f"{ts} PILOT {ts_short}: mirror 3/3 present; messages push abhi; page verify 12:00.",
}
n_updated = 0
for t in tasks:
    if t.get("id") in notes:
        ev = t.get("evidence", "")
        t["evidence"] = (ev + " || " + notes[t["id"]]) if ev else notes[t["id"]]
        n_updated += 1
save(tasks_path, tasks)
print(f"TASKS: {n_updated} evidence-updated @ {ts}")

# ---------- 3) BOTS.JSON REFRESH ----------
bots_path = os.path.join(base, "bots.json")
bots = load(bots_path)
bots["Pilot"]["status"] = (f"{ts_short} IST REV-COMMAND: loop DEAD 40h+ (batch 211, proc 0, cron 0); SIP 4 vars len=0; "
                           f"api.vobiz.com 000 @8s DAY5; VOBIZ_CALLER_ID REVOKED len13; WA-sent 0; leads/ ABSENT; "
                           f"/health 308 expected; hot-queue 43/43. FLEET 0 ACK - REINFORCE {ts_short} sent.")
bots["sales"]["status"] = (f"SAL-003 P0: WA sends ZERO (auto_sent 0) - hot-queue 43 WA abhi. "
                           f"Vendor DID proof 09:00 IST. ACK missing - REINFORCE sent.")
bots["platform"]["status"] = ("PLT-004 P0: egress 000 @8.002s DAY5; SIP 4 vars len=0; VOBIZ_CALLER_ID REVOKED len13. Root-cause + Jio SIP template 09:00 IST. ACK missing.")
bots["operations"]["status"] = "OPS-006 P0: loop DEAD 40h+ re-confirm (proc 0, cron 0, mtime Aug31 08:39Z). Restart sign = env swap; 10:30 digest. ACK missing."
bots["engineering"]["status"] = "ENG-003 P1: watchdog missing (crontab 0). WAHA probe X-Api-Key. Watchdog+runbook 09:30. ACK missing."
bots["hunter"]["status"] = "HNT-004 P1: leads/ ABSENT re-confirm; 50-lead DND CSV 09:30 IST. ACK missing."
bots["guardian"]["status"] = "GRD-003 P1: 6 verdicts 11:00 IST (revenue-truth + loop-dead + WAHA + auto_sent + leads + DID). ACK missing."
bots["success"]["status"] = "SUC-002 P0: Jiya only payer 1999 churn-risk; SMTP SENT proof 12:00 IST. ACK missing."
bots["board"]["status"] = "BRD-002 P2: mirror present VPS; fresh push PILOT abhi. Page verify + cadence 12:00. ACK missing."
save(bots_path, bots)
print(f"BOTS: {len(bots)} statuses refreshed @ {ts}")

# ---------- 4) PINNED.JSON REFRESH ----------
pinned_path = os.path.join(base, "pinned.json")
pinned = load(pinned_path)
pinned["last_updated"] = now.strftime("%Y-%m-%dT%H:%M+05:30")
pinned["priority_tasks"] = ["SAL-003", "PLT-004", "OPS-006", "ENG-003", "HNT-004"]
pinned["vps_status"] = ("HEALTHY (containers 37h, /health 308 auth-gated); calling loop DEAD 40h+ (mtime Aug31 08:39:55Z batch 211; proc 0; cron 0); "
                        "SIP 4 vars EMPTY (DID not landed); VOBIZ_CALLER_ID REVOKED len13; Vobiz egress TCP-BLOCK 000 @8.002s DAY5; WA sent 0; leads/ ABSENT; "
                        "WAHA :3111 session WORKING with X-Api-Key (401 bina key = expected gate)")
pinned["verified_revenue"] = "₹1,999 (Jiya INV/2026-27/0001) - GRD-003 auditing revenue_snapshots claim active=3/MRR=5997"
pinned["gap"] = "₹4,98,001"
pinned["bottleneck"] = ("DID gate: vendor DID proof absent (SAL-003 09:00) + SIP vars EMPTY + VOBIZ_CALLER_ID REVOKED + Vobiz egress TCP-BLOCK day5 (PLT-004) + "
                        "loop dead no-watchdog (ENG-003/OPS-006) + ammo EMPTY (HNT-004). WA channel OPEN (WAHA WORKING) - hot-queue 43 closes = aaj ka revenue path (0 sent).")
pinned["pipeline"] = "43 HOT interested leads (hot_queue 09-01.csv, 43/43 wa_link+UPI); 0 dialer connects (loop dead 40h+); 0 WA sends; Jiya P0"
pinned["action"] = ("SAL-003 WA >=10 + vendor DID 09:00 → PLT-004 egress verdict 09:00 → ENG-003 watchdog 09:30 → "
                    "HNT-004 CSV 09:30 → OPS-006 10:30 digest → GRD-003 11:00 verdicts → SUC-002 Jiya 12:00 → BRD-002 page verify 12:00")
pinned["next_expected_payment"] = "Hot-queue WA close (UPI deep-link) ya Jiya retention ya pehla post-DID sale - vaada nahi, evidence ke saath"
save(pinned_path, pinned)
print(f"PINNED: refreshed @ {ts}")
print("DONE")