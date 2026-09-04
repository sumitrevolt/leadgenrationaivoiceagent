#!/usr/bin/env python3
"""PILOT 09-02 02:00 IST dispatch run — fresh evidence + WAHA finding CORRECTION + mirror push verify. Cron window."""
import json, os
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
now = datetime.now(IST)
ts = now.strftime("%Y-%m-%dT%H:%M:%S+05:30")
ts_short = now.strftime("%H:%M")
base = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"

# ---------- 1) LEDGER APPEND ----------
ledger_path = os.path.join(base, "messages.jsonl")
lines = [
    {"ts": ts, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": f"🎯 REVENUE COMMAND {ts_short} IST (Sep 2): TARGET ₹5,00,000 | VERIFIED ₹1,999 (Jiya INV-0001; GRD-003 audit in progress — revenue_snapshots Sep1 active=3/MRR=5997 UNVERIFIED) | GAP ₹4,98,001 | PIPELINE: hot_queue 09-01.csv 43/43 interested rows (wa_link + UPI deep-link present), koi 09-02 queue nahi (0330Z gen pending); dialer connects 0; loop DEAD 36h+ (mtime Aug31 08:39:55Z batch 211, proc 0, cron 0); reply_drafts 2204 auto_sent=0 = ZERO WA sends | HOT: 43 WA closes + Jiya P0 | BOTTLENECK: DID (SAL-003 vendor proof 09:00) → env swap (PLT-004 SIP 5 vars len=0, Vobiz egress 000 TCP-block 4+ days) → restart (OPS-006/ENG-003 watchdog) | 🔧 CORRECTION 02:00: WAHA :3111 401 = MISREAD — X-Api-Key header ke saath /api/sessions 200: session 'default' WORKING, me=918459012607 (sumitrevolt23), webhook ok. WA-SEND PATH LIVE hai — SAL-003 isse hot-queue bhejo. AAJ KA REVENUE PATH = WA closes + DID | ACTION: gates 09:00/09:30/10:30/11:00/12:00 IST (SAL-003/PLT-004/ENG-003/HNT-004/OPS-006/GRD-003/SUC-002/BRD-002) | NEXT: 09:00 vendor DID + WA>=10 → 10:00 TRAI window post-DID batch → pehla connect → UPI | ⚠️ 01:40/01:50 dispatches ke 0 ACK — ALL: poll, ACK, evidence. Mirror SYNC VERIFIED (md5 3/3 match VPS==local)."},
    {"ts": ts, "from": "PILOT", "to": "sales", "task_id": "SAL-003", "type": "REINFORCE", "priority": "P0",
     "msg": f"SAL-003 REINFORCE ({ts_short}) — 🔧 WAHA FINDING REVERSED: 401 sirf isliye tha kyunki token header nahi tha. X-Api-Key se /api/sessions 200: session 'default' WORKING (918459012607 sumitrevolt23), webhook https://leadsgenai.in/api/wa/selfhost/webhook?token=... ok. WA-SEND LIVE hai — hot_queue 09-01.csv (43/43 wa_link+UPI) bhejna SHURU karo, reply_drafts 2204 drafts auto_sent=0. WAHA_BASE_URL=http://waha:3000 (container net) / host :3111. 09:00 IST ACC BOTH: (a) >=10 WA-sent proof (wa-send API response / log) + reply count, (b) vendor DID number/activation proof. ACK SAL-003 NOW."},
    {"ts": ts, "from": "PILOT", "to": "platform", "task_id": "PLT-004", "type": "UPDATE", "priority": "P0",
     "msg": f"PLT-004 ({ts_short}) — re-test 02:00 IST: api.vobiz.com 000 timeout 8s (TCP-block, 4+ days), SIP_HOST/USERNAME/PASSWORD/DID/PROVIDER bhi 0 non-empty. WAHA auth note: /api/health 404 + /api/sessions 200 = CORRECT path (session route). 09:00 IST ACC: egress root-cause verdict + re-test proof + Jio SIP env swap template. ACK PLT-004."},
    {"ts": ts, "from": "PILOT", "to": "operations", "task_id": "OPS-006", "type": "UPDATE", "priority": "P0",
     "msg": f"OPS-006 ({ts_short}) — loop DEAD re-confirm: log mtime Aug31 08:39:55Z (batch 211, 3/3 FAIL '911171366938 not owned'), proc 0, crontab 0. Restart sign = PLT-004 env swap. WAHA liveness monitor sahi route se: /api/sessions with X-Api-Key (401 bina token = EXPECTED, fail-closed mat banao). 10:30 IST digest = pehla output. ACK OPS-006."},
    {"ts": ts, "from": "PILOT", "to": "engineering", "task_id": "ENG-003", "type": "UPDATE", "priority": "P1",
     "msg": f"ENG-003 ({ts_short}) — watchdog ABHI BHI missing (crontab 0). Spec: log mtime stale >10min in TRAI window + no proc => alert+restart (sirf owned caller-ID ho tab). WAHA probe: /api/sessions X-Api-Key (401 bina key = expected). Jio SIP failover runbook due. ACC 09:30: commit sha + runbook + watchdog evidence. ACK ENG-003."},
    {"ts": ts, "from": "PILOT", "to": "hunter", "task_id": "HNT-004", "type": "UPDATE", "priority": "P1",
     "msg": f"HNT-004 ({ts_short}) — /opt/leadgen/data/leads/ EMPTY re-confirm (dir exist nahi/ls blank). Dialer restart-ready hone par ammo ZERO. 09:30 IST ACC: CSV path + 50 verified MOBILE + DND-proof column + pool refill scan. ACK HNT-004."},
    {"ts": ts, "from": "PILOT", "to": "guardian", "task_id": "GRD-003", "type": "UPDATE", "priority": "P1",
     "msg": f"GRD-003 ({ts_short}) — SCOPE +1: revenue_snapshots.jsonl Sep1 active=3/MRR=5997 vs ledger Jiya-only ₹1,999 — invoice files find=0, subscriber table check karo. WAHA verdict REVISED: 401=no-auth-header MISREAD; /api/sessions 200 with key = HEALTHY. (5) SAL-003 vendor proof 09:00 ke baad verify. 5+ verdicts 11:00 IST, PASS/FAIL + evidence file command_center/data. ACK GRD-003."},
    {"ts": ts, "from": "PILOT", "to": "success", "task_id": "SUC-002", "type": "UPDATE", "priority": "P0",
     "msg": f"SUC-002 ({ts_short}) — Jiya = only verified payer ₹1,999 (INV/2026-27/0001; revenue_snapshot 5997/3-active UNVERIFIED). Naya invoice find=0. Churn = revenue ₹0. DID-independent — 12:00 IST ACC: SMTP SENT artifact + WA follow-up + reply/fallback. ACK SUC-002."},
    {"ts": ts, "from": "PILOT", "to": "board", "task_id": "BRD-002", "type": "UPDATE", "priority": "P2",
     "msg": f"BRD-002 ({ts_short}) — MIRROR VERIFIED: PILOT ne abhi md5 kiya — VPS /opt/leadgen/command_center/data/tasks.json+bots.json+pinned.json == local (3/3 match, mtime Sep1 20:26Z). TERA KAAM: live app page pe mirror display verify + 30-min refresh cadence. ACC 12:00 IST: page-check evidence. ACK BRD-002."},
]
with open(ledger_path, "a", encoding="utf-8") as f:
    for ln in lines:
        f.write(json.dumps(ln, ensure_ascii=False) + "\n")
print(f"LEDGER: {len(lines)} lines appended @ {ts}")

# ---------- 2) TASKS.JSON EVIDENCE UPDATE ----------
tasks_path = os.path.join(base, "tasks.json")
with open(tasks_path, encoding="utf-8") as f:
    tasks = json.load(f)

notes = {
    "SAL-003": f"{ts} PILOT {ts_short}: 🔧 WAHA 401 REVERSED — /api/sessions 200 with X-Api-Key, session default WORKING (918459012607), webhook ok. WA-send LIVE. hot-queue 43/43 wa_link+UPI. auto_sent=0 abhi bhi. ACC 09:00: WA>=10 + vendor DID.",
    "PLT-004": f"{ts} PILOT {ts_short}: egress 000 re-confirm (8s TCP-block). SIP 5 vars still len=0. WAHA route note: /api/sessions. Root-cause 09:00.",
    "OPS-006": f"{ts} PILOT {ts_short}: loop DEAD re-confirm (mtime Aug31 08:39:55Z batch 211, proc 0, cron 0). WAHA monitor route corrected. 10:30 digest.",
    "ENG-003": f"{ts} PILOT {ts_short}: watchdog missing re-confirm (crontab 0). WAHA probe /api/sessions. Watchdog+runbook 09:30.",
    "HNT-004": f"{ts} PILOT {ts_short}: leads/ EMPTY re-confirm. 50-lead DND CSV due 09:30.",
    "GRD-003": f"{ts} PILOT {ts_short}: +1 scope — subscriber-count/invoice truth (snap 3-active vs ledger 1). WAHA verdict revised = HEALTHY. 5+ verdicts 11:00.",
    "SUC-002": f"{ts} PILOT {ts_short}: Jiya proof due 12:00; snap 5997 unverified; invoice find=0. Churn=P0.",
    "BRD-002": f"{ts} PILOT {ts_short}: MIRROR VERIFIED md5 3/3 (VPS==local). Board: page verify + cadence.",
}
n_updated = 0
for t in tasks:
    if t.get("id") in notes:
        t["evidence"] = (t.get("evidence", "") + " || " + notes[t["id"]]).strip(" ||")
        n_updated += 1
with open(tasks_path, "w", encoding="utf-8") as f:
    json.dump(tasks, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(f"TASKS: {n_updated} evidence-updated @ {ts}")

# ---------- 3) BOTS.JSON STATUS REFRESH ----------
bots_path = os.path.join(base, "bots.json")
with open(bots_path, encoding="utf-8") as f:
    bots = json.load(f)

bots["Pilot"]["status"] = (f"{ts_short} IST REV-COMMAND: loop DEAD 36h+; SIP 5 vars len=0; Vobiz egress TCP-block; "
                           f"WAHA 401=MISREAD -> /api/sessions 200 (WA-send LIVE); hot-queue 43/43 WA+UPI ready, 0 sent; "
                           f"mirror md5 3/3 verified. 0 ACK — nudge sent.")
bots["sales"]["status"] = (f"SAL-003 P0: WAHA LIVE (X-Api-Key /api/sessions 200, default WORKING) — hot-queue 43 WA+UPI bhejo, "
                           f"auto_sent=0 abhi. Vendor DID proof due 09:00 IST. ACK missing — REINFORCE sent.")
bots["platform"]["status"] = ("PLT-004 P0: egress 000 (8s TCP-block 4+ days). SIP 0 non-empty. Root-cause + Jio SIP template 09:00 IST. ACK missing.")
bots["operations"]["status"] = "OPS-006 P0: loop DEAD re-confirm (proc 0, cron 0, mtime Aug31 08:39Z). Restart sign = env swap; 10:30 digest. WAHA monitor route corrected. ACK missing."
bots["engineering"]["status"] = "ENG-003 P1: watchdog missing (crontab 0); WAHA probe /api/sessions. Watchdog+runbook due 09:30. ACK missing."
bots["hunter"]["status"] = "HNT-004 P1: leads/ EMPTY re-confirm; 50-lead DND CSV due 09:30 IST. ACK missing."
bots["guardian"]["status"] = "GRD-003 P1: 5+ verdicts due 11:00 IST (revenue-truth audit + WAHA revised HEALTHY + loop-dead + invoice find). ACK missing."
bots["success"]["status"] = "SUC-002 P0: Jiya email SENT proof due 12:00 IST; only payer ₹1,999 churn-risk. ACK missing."
bots["board"]["status"] = (f"BRD-002 P2: MIRROR VERIFIED md5 3/3 (VPS==local, mtime Sep1 20:26Z). "
                           f"Tera kaam: live page verify + 30-min cadence. Due 12:00 IST.")
with open(bots_path, "w", encoding="utf-8") as f:
    json.dump(bots, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(f"BOTS: {len(bots)} statuses refreshed @ {ts}")

# ---------- 4) PINNED.JSON REFRESH ----------
pinned_path = os.path.join(base, "pinned.json")
with open(pinned_path, encoding="utf-8") as f:
    pinned = json.load(f)
pinned["last_updated"] = now.strftime("%Y-%m-%dT%H:%M+05:30")
pinned["priority_tasks"] = ["SAL-003", "PLT-004", "OPS-006", "ENG-003", "HNT-004"]
pinned["vps_status"] = ("HEALTHY (37a1daf8); calling loop DEAD 36h+ (mtime Aug31 08:39:55Z batch 211; proc 0; cron 0); "
                        "SIP env 5 vars EMPTY; Vobiz egress TCP-BLOCK 000 (8s, 4+ days); WAHA :3111 /api/sessions 200 WITH X-Api-Key = WA-SEND LIVE (401 bina key = normal auth gate)")
pinned["verified_revenue"] = "₹1,999 (Jiya INV/2026-27/0001) — GRD-003 auditing revenue_snapshots claim active=3/MRR=5997"
pinned["gap"] = "₹4,98,001"
pinned["bottleneck"] = ("DID gate: vendor proof absent (SAL-003) + Vobiz egress TCP-block (PLT-004) + SIP creds empty + "
                        "loop dead no-watchdog (ENG-003/OPS-006). WA channel OPEN (WAHA working) — hot-queue 43 closes = aaj ka revenue path (0 sent so far).")
pinned["pipeline"] = "43 HOT interested leads (hot_queue 09-01.csv, 43/43 wa_link+UPI); 0 dialer connects (loop dead 36h+); 0 WA sends; Jiya P0"
pinned["action"] = ("SAL-003 WA >=10 + vendor DID 09:00 → PLT-004 egress root-cause 09:00 → ENG-003 watchdog 09:30 → "
                    "HNT-004 CSV 09:30 → OPS-006 10:30 digest → GRD-003 11:00 verdicts → SUC-002 Jiya 12:00 → BRD-002 page verify")
pinned["next_expected_payment"] = "Hot-queue WA close (UPI deep-link) ya Jiya retention ya pehla post-DID sale — vaada nahi, evidence ke saath"
with open(pinned_path, "w", encoding="utf-8") as f:
    json.dump(pinned, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(f"PINNED: refreshed @ {ts}")