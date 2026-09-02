#!/usr/bin/env python3
"""PILOT 09-02 05:46 IST dispatch run — fresh VPS sweep (05:46 IST / 00:16Z) evidence.
Loop DEAD 45h+ (mtime Aug31 08:39:55Z, batch 211 fail 3/3 'not owned', proc 0, cron 0);
reply_drafts 2204 total auto_sent true=0; WA flip INERT (disk .env=1, container=0);
leads/ ABSENT; SIP 5 vars EMPTY (len=0); VOBIZ_CALLER_ID REVOKED len13;
egress api.vobiz.com timeout day5; /health 37a1daf8 healthy uptime 11h42m, containers up 40h;
WAHA no-key 401 expected gate (with-key 200 WORKING earlier); hot-queue 09-01 43/43 wa_link+UPI;
mirror MD5-synced (tasks 26582==26582, bots 1946==1946, messages 92602==92602).
Dispatch = REINFORCE (no new TASK-ID, anti-spam — all 8 tasks active UPDATE, gates 09:00-12:00 IST)."""
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
     "msg": f"🎯 REVENUE COMMAND {ts_short} IST (Sep 2): TARGET ₹5,00,000 | VERIFIED ₹1,999 (Jiya INV/2026-27/0001 sole; GRD-003 audit) | GAP ₹4,98,001 | PIPELINE: hot-queue 09-01.csv 43/43 wa_link+UPI (09-02 ABSENT), dialer connects 0 (loop DEAD 45h+, mtime Aug31 08:39:55Z batch 211 ok=0/fail=3 'not owned', proc 0, cron 0), WA-sent 0 (reply_drafts 2204 total auto_sent true=0), leads/ ABSENT (ammo ZERO) | HOT: 43 WA closes + Jiya P0 | BOTTLENECK: WA container flip INERT (disk .env=1, container=0 -> restart owner-approve) + DID gate (SAL-003 09:00; SIP_HOST/USERNAME/PASSWORD/DID/SIP_PROVIDER 5 vars len=0) + VOBIZ_CALLER_ID REVOKED len13 still in env + Vobiz egress timeout day5 (PLT-004) + loop dead no-watchdog (ENG-003/OPS-006) + ammo ZERO (HNT-004) | ACTION: WA manual-send ABHI — WAHA :3111 with X-Api-Key 200 WORKING (session default 918459012607, no-key 401 = expected gate), hot-queue 43 UPI deep-links; gates 09:00/09:30/10:30/11:00/12:00 IST | NEXT: 09:00 vendor DID + WA>=10 -> env swap -> 10:00 TRAI pehla clean batch -> pehla UPI close | FLEET dispatches 00:12-05:44 ke 0 ACK — sab bots poll messages.jsonl, ACK TASK-ID, evidence file. Fresh sweep 05:46 IST filed. Mirror MD5-synced."},
    {"ts": ts, "from": "PILOT", "to": "sales", "task_id": "SAL-003", "type": "REINFORCE", "priority": "P0",
     "msg": f"SAL-003 ({ts_short}) - 🚨 WA-SEND ABHI EXECUTE (manual API path): WA container flip INERT hai (disk=1 containers=0) isliye scheduler auto-send nahi karega — lekin WAHA :3111 with X-Api-Key 200 WORKING hai (session default 918459012607; no-key 401 = expected gate). hot_queue_for_owner_2026-09-01.csv 43/43 wa_link+UPI (1-tap UPI deep-link) = AAJ KA REVENUE PATH. Dialer dead 45h+. ACC 09:00 IST BOTH: (a) >=10 WA manual-send proof (HTTP 200 + api id + reply_drafts auto_sent count >0), (b) vendor DID number/activation (Call Soft wa.me/917599967999 follow-up + RMS Tech 080-47652298 backup dono tracks). ACK SAL-003 NOW."},
    {"ts": ts, "from": "PILOT", "to": "platform", "task_id": "PLT-004", "type": "UPDATE", "priority": "P0",
     "msg": f"PLT-004 ({ts_short}) - FRESH 05:46 IST sweep: /health 37a1daf8 healthy uptime 11h42m; containers up 40h; egress api.vobiz.com timeout (day5, DNS AWS-GA resolves, TCP-block); SIP_HOST/USERNAME/PASSWORD/DID/SIP_PROVIDER 5 lines len=0 (DID NOT landed); VOBIZ_CALLER_ID len13 REVOKED still in .env — remove/swap; WA flip INERT (disk=1 container=0) needs owner-approve restart. ACC 09:00 IST: egress root-cause verdict (firewall/AWS-GA/DNS/route) + re-test proof + Jio SIP env swap template + WA restart-approval escalation filed. ACK PLT-004."},
    {"ts": ts, "from": "PILOT", "to": "operations", "task_id": "OPS-006", "type": "UPDATE", "priority": "P0",
     "msg": f"OPS-006 ({ts_short}) - loop DEAD 45h+ re-confirm 05:46 IST: call_loop.log mtime Aug31 08:39:55Z batch 211 fail 3/3 'not owned'; proc 0; cron 0. Restart sign = PLT-004 env swap (valid owned caller-ID). 10:30 IST digest = pehla real output (batches + connects + fail reasons). Isse pehle restart mat karo (fail-churn). ACK OPS-006."},
    {"ts": ts, "from": "PILOT", "to": "engineering", "task_id": "ENG-003", "type": "UPDATE", "priority": "P1",
     "msg": f"ENG-003 ({ts_short}) - watchdog MISSING re-confirm (crontab loop/watch entries = 0; loop 45h+ dead bina restart). Spec: TRAI window call_loop.log mtime >10min stale + no proc => alert + restart (sirf owned caller-ID ho). Jio SIP failover runbook + WAHA probe /api/sessions X-Api-Key pattern (with-key 200 WORKING, no-key 401 expected gate). ACC 09:30 IST: commit sha + runbook + watchdog evidence. ACK ENG-003."},
    {"ts": ts, "from": "PILOT", "to": "hunter", "task_id": "HNT-004", "type": "UPDATE", "priority": "P1",
     "msg": f"HNT-004 ({ts_short}) - /opt/leadgen/data/leads/ ABSENT re-confirm 05:46 IST (ls: No such file or directory). Ammo ZERO 5+ din. hot-queue 09-01 exists (43) par fresh 09-02 nahi. ACC 09:30 IST: CSV path + 50 verified MOBILE + DND-proof column + pool refill scan. Google Maps Places (new) se Ahmedabad/Mumbai restaurants niche=ai_marketing. Dialer live hone par turant ammo. ACK HNT-004."},
    {"ts": ts, "from": "PILOT", "to": "guardian", "task_id": "GRD-003", "type": "UPDATE", "priority": "P1",
     "msg": f"GRD-003 ({ts_short}) - 6 verdicts due 11:00 IST PASS/FAIL + evidence file command_center/data: (1) revenue-truth (revenue_snapshots mrr=5997/active=3 vs ledger Jiya INV/2026-27/0001 ₹1,999 sole; invoice tail VOIDED synthetic), (2) loop-dead (proc/cron/mtime 45h+), (3) leads/ ABSENT, (4) auto_sent=0 of 2204 drafts, (5) WAHA HEALTHY (with-key 200 WORKING, no-key 401 expected gate — FINAL), (6) SAL-003 vendor DID + WA>=10 post-09:00. +7th: manual WA-send claim VERIFY when sales reports. ACK GRD-003."},
    {"ts": ts, "from": "PILOT", "to": "success", "task_id": "SUC-002", "type": "UPDATE", "priority": "P0",
     "msg": f"SUC-002 ({ts_short}) - Jiya sole verified payer ₹1,999 (INV/2026-27/0001); churn = revenue ₹0. DID-independent. ACC 12:00 IST: SMTP SENT artifact + WA follow-up + reply/fallback offer (retention offer ready). REV-105 close-kit STANDBY rakho — trigger = first connect + interested lead. ACK SUC-002."},
    {"ts": ts, "from": "PILOT", "to": "board", "task_id": "BRD-002", "type": "UPDATE", "priority": "P2",
     "msg": f"BRD-002 ({ts_short}) - MIRROR MD5-SYNCED VERIFIED 05:46 IST: tasks.json 26582==26582 (VPS /opt/leadgen/command_center/data), bots.json 1946==1946, messages.jsonl 92602==92602. PILOT fresh push abhi. Tera kaam: live /app/bot-command-center page display verify + 30-min refresh cadence + sync check @ each sweep. ACC 12:00 IST: page-check evidence. ACK BRD-002."},
]
with open(ledger_path, "a", encoding="utf-8") as f:
    for ln in lines:
        f.write(json.dumps(ln, ensure_ascii=False) + "\n")
print(f"LEDGER: {len(lines)} lines appended @ {ts}")

# ---------- 2) TASKS.JSON EVIDENCE UPDATE ----------
tasks_path = os.path.join(base, "tasks.json")
tasks = load(tasks_path)
notes = {
    "SAL-003": f"{ts} PILOT {ts_short}: WA manual-send path OPEN (WAHA with-key 200 WORKING, session default 918459012607; no-key 401 expected); container flip INERT disk=1/container=0; hot-queue 09-01 43/43; reply_drafts 2204 auto_sent true=0; ACC 09:00 WA>=10 + vendor DID.",
    "PLT-004": f"{ts} PILOT {ts_short}: /health 37a1daf8 healthy uptime 11h42m; egress timeout day5; SIP 5 vars len=0; VOBIZ_CALLER_ID len13 REVOKED in .env; WA flip INERT; ACC 09:00 verdict+template+restart-approval.",
    "OPS-006": f"{ts} PILOT {ts_short}: loop DEAD 45h+ (mtime Aug31 08:39:55Z batch 211, proc 0, cron 0); 10:30 digest.",
    "ENG-003": f"{ts} PILOT {ts_short}: watchdog missing (crontab 0); WAHA with-key 200/no-key 401 pattern; 09:30 commit+runbook+watchdog.",
    "HNT-004": f"{ts} PILOT {ts_short}: leads/ ABSENT re-confirm; hot-queue Sep1 43 present, Sep2 ABSENT; 09:30 50-lead DND CSV.",
    "GRD-003": f"{ts} PILOT {ts_short}: revenue-truth gap confirmed (snap mrr=5997/active=3 vs ledger VOIDED synthetic tail; Jiya sole); WAHA=FINAL HEALTHY; 6+1 verdicts 11:00.",
    "SUC-002": f"{ts} PILOT {ts_short}: Jiya sole payer 1999 churn P0; ACC 12:00 SMTP proof.",
    "BRD-002": f"{ts} PILOT {ts_short}: MIRROR MD5-SYNCED VERIFIED (tasks 26582==26582, bots 1946==1946, messages 92602==92602); fresh push abhi; page verify 12:00.",
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
bots["Pilot"]["status"] = (f"{ts_short} IST REV-COMMAND: loop DEAD 45h+ (batch 211, proc 0, cron 0); SIP 5 vars len=0; "
                           f"api.vobiz.com timeout DAY5; VOBIZ_CALLER_ID REVOKED len13; WA-sent 0 (2204 drafts auto_sent true=0); "
                           f"leads/ ABSENT; /health 37a1daf8 healthy 11h42m; WAHA with-key 200 WORKING; hot-queue 43/43; "
                           f"MIRROR MD5-SYNCED. FLEET 0 ACK - REINFORCE {ts_short} sent. Gates 09:00-12:00 IST.")
bots["sales"]["status"] = (f"SAL-003 P0: WA manual-send ABHI (WAHA with-key 200; hot-queue 43 UPI; auto_sent 0). "
                           f"Vendor DID proof 09:00 IST. ACK missing - REINFORCE sent.")
bots["platform"]["status"] = ("PLT-004 P0: egress timeout DAY5; SIP 5 vars len=0; VOBIZ_CALLER_ID REVOKED len13; WA flip INERT. Root-cause + template 09:00 IST. ACK missing.")
bots["operations"]["status"] = "OPS-006 P0: loop DEAD 45h+ re-confirm (proc 0, cron 0, mtime Aug31 08:39Z). Restart sign = env swap; 10:30 digest. ACK missing."
bots["engineering"]["status"] = "ENG-003 P1: watchdog missing (crontab 0). WAHA probe 200/401 pattern. Watchdog+runbook 09:30. ACK missing."
bots["hunter"]["status"] = "HNT-004 P1: leads/ ABSENT re-confirm; hot-queue Sep2 ABSENT; 50-lead DND CSV 09:30 IST. ACK missing."
bots["guardian"]["status"] = "GRD-003 P1: 6+1 verdicts 11:00 IST (revenue-truth + loop-dead + WAHA + auto_sent + leads + DID + WA-claim). ACK missing."
bots["success"]["status"] = "SUC-002 P0: Jiya only payer 1999 churn-risk; SMTP SENT proof 12:00 IST. REV-105 close-kit standby. ACK missing."
bots["board"]["status"] = "BRD-002 P2: MIRROR MD5-SYNCED VERIFIED (tasks/bots/messages 3/3); fresh push abhi. Page verify + cadence 12:00. ACK missing."
save(bots_path, bots)
print(f"BOTS: {len(bots)} statuses refreshed @ {ts}")

# ---------- 4) PINNED.JSON REFRESH ----------
pinned_path = os.path.join(base, "pinned.json")
pinned = load(pinned_path)
pinned["last_updated"] = now.strftime("%Y-%m-%dT%H:%M+05:30")
pinned["priority_tasks"] = ["SAL-003", "PLT-004", "OPS-006", "ENG-003", "HNT-004"]
pinned["vps_status"] = ("HEALTHY (/health 37a1daf8, uptime 11h42m, env production; containers up 40h); calling loop DEAD 45h+ "
                        "(mtime Aug31 08:39:55Z batch 211; proc 0; cron 0); SIP 5 vars EMPTY (DID not landed); VOBIZ_CALLER_ID REVOKED len13; "
                        "Vobiz egress timeout DAY5; WA sent 0 (reply_drafts 2204 auto_sent true=0); leads/ ABSENT; "
                        "WAHA :3111 with X-Api-Key 200 WORKING / no-key 401 expected gate; WA container flip INERT (disk=1 containers=0, owner-approve restart needed)")
pinned["verified_revenue"] = "₹1,999 (Jiya INV/2026-27/0001) - GRD-003 auditing revenue_snapshots claim active=3/MRR=5997"
pinned["gap"] = "₹4,98,001"
pinned["bottleneck"] = ("DID gate (SAL-003 09:00): vendor DID absent + SIP 5 vars EMPTY + VOBIZ_CALLER_ID REVOKED + Vobiz egress timeout day5 (PLT-004) + "
                        "WA container flip INERT (restart owner-approve; manual WA path OPEN — 0 sends abhi) + "
                        "loop dead no-watchdog (ENG-003/OPS-006) + ammo EMPTY (HNT-004). WA channel OPEN (WAHA with-key 200) - hot-queue 43 closes = aaj ka revenue path (0 sent).")
pinned["pipeline"] = "43 HOT interested leads (hot_queue 09-01.csv, 43/43 wa_link+UPI); 0 dialer connects (loop dead 45h+); 0 WA sends; Jiya P0"
pinned["action"] = ("SAL-003 WA >=10 + vendor DID 09:00 → PLT-004 egress verdict + env template 09:00 → ENG-003 watchdog 09:30 → "
                    "HNT-004 CSV 09:30 → OPS-006 10:30 digest → GRD-003 verdicts 11:00 → SUC-002 Jiya 12:00 → BRD-002 page verify 12:00")
pinned["next_expected_payment"] = "Hot-queue WA close (UPI deep-link) ya Jiya retention ya pehla post-DID sale - vaada nahi, evidence ke saath"
save(pinned_path, pinned)
print(f"PINNED: refreshed @ {ts}")
print("DONE")