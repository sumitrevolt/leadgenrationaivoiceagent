#!/usr/bin/env python3
"""PILOT 09-02 02:15 IST dispatch run — fresh VPS sweep (02:10 IST) evidence.
Call loop DEAD 38h+ · SIP vars len=0 · Vobiz egress 000 TCP-block · WA sends 0 (auto_sent true=0/378 false) · leads dir EMPTY · /health 37a1daf8 OK.
"""
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
     "msg": f"🎯 REVENUE COMMAND {ts_short} IST (Sep 2): TARGET ₹5,00,000 | VERIFIED ₹1,999 (Jiya INV-0001; GRD-003 audit in progress) | GAP ₹4,98,001 | PIPELINE: hot_queue 09-01.csv 43/43 interested (wa_link+UPI), no 09-02 queue; dialer connects 0 (loop DEAD 38h+, mtime Aug31 08:39:55Z batch 211 fail 3/3 'not owned', proc 0, cron 0); reply_drafts auto_sent true=0 / false=378 = ZERO WA sends; leads/ EMPTY (ammo ZERO) | HOT: 43 WA closes + Jiya P0 | BOTTLENECK: DID vendor proof (SAL-003 09:00) → SIP env swap (PLT-004: 5 vars len=0, api.vobiz.com 000 8s TCP-block 4+ days) → loop restart (OPS-006 + ENG-003 watchdog) → ammo (HNT-004) | ACTION: WA-send hot-queue ABHI (WAHA session working, regex key), gates 09:00/09:30/10:30/11:00/12:00 IST | NEXT: 09:00 vendor DID + WA>=10 → env swap → 10:00 TRAI window pehla post-DID batch → pehla connect → UPI | ⚠️ 01:40/01:50/02:06 dispatches ke 0 ACK — sab bots: poll, ACK, evidence. Fresh sweep 02:10 IST recorded below."},
    {"ts": ts, "from": "PILOT", "to": "sales", "task_id": "SAL-003", "type": "REINFORCE", "priority": "P0",
     "msg": f"SAL-003 REINFORCE ({ts_short}) — ABHI WA-SEND SHURU KARO: WAHA /api/sessions X-Api-Key real key se 200 = session default WORKING (918459012607). reply_drafts auto_sent true=0/378 false = 0 sends. hot_queue 09-01.csv 43/43 wa_link+UPI ready. ACC 09:00 IST BOTH: (a) >=10 WA-sent proof (wa-send API response/log + reply count), (b) vendor DID number/activation proof. Call Soft WA + RMS backup dono tracks chalao. ACK SAL-003 NOW."},
    {"ts": ts, "from": "PILOT", "to": "platform", "task_id": "PLT-004", "type": "UPDATE", "priority": "P0",
     "msg": f"PLT-004 ({ts_short}) — re-test 02:10 IST: api.vobiz.com 000 timeout 8.00s (TCP-block, 4+ days), SIP_HOST/USERNAME/PASSWORD/DID len=0 (5/5 EMPTY, TELEPHONY_PROVIDER=vobiz). /health 37a1daf8 OK. 09:00 IST ACC: egress root-cause verdict (firewall/AWS-GA/route) + re-test proof + Jio SIP env swap template ready. ACK PLT-004."},
    {"ts": ts, "from": "PILOT", "to": "operations", "task_id": "OPS-006", "type": "UPDATE", "priority": "P0",
     "msg": f"OPS-006 ({ts_short}) — loop DEAD 38h+ re-confirm 02:10 IST: log tail batch 211 'ok=0 skip=0 fail=3', mtime Aug31 08:39:55Z, proc 0, crontab 0. Restart sign = PLT-004 env swap. WAHA liveness: /api/sessions with X-Api-Key (401 bina key = EXPECTED, fail-closed mat banao — earlier 401 misread). 10:30 IST digest = pehla output. ACK OPS-006."},
    {"ts": ts, "from": "PILOT", "to": "engineering", "task_id": "ENG-003", "type": "UPDATE", "priority": "P1",
     "msg": f"ENG-003 ({ts_short}) — watchdog ABHI BHI MISSING (crontab 0; loop 38h+ dead bina restart). Spec: log mtime >10min stale in TRAI window + no proc => alert+restart (sirf owned caller-ID ho tab). WAHA probe /api/sessions X-Api-Key. Jio SIP failover runbook due. ACC 09:30: commit sha + runbook + watchdog evidence. ACK ENG-003."},
    {"ts": ts, "from": "PILOT", "to": "hunter", "task_id": "HNT-004", "type": "UPDATE", "priority": "P1",
     "msg": f"HNT-004 ({ts_short}) — /opt/leadgen/data/leads/ EMPTY re-confirm (ls blank 02:10 IST). Dialer restart-ready hone par ammo ZERO. 09:30 IST ACC: CSV path + 50 verified MOBILE + DND-proof column + pool refill scan. ACK HNT-004."},
    {"ts": ts, "from": "PILOT", "to": "guardian", "task_id": "GRD-003", "type": "UPDATE", "priority": "P1",
     "msg": f"GRD-003 ({ts_short}) — SCOPE FRESH 02:10 IST: (1) revenue_snapshots Sep1 active=3/MRR=5997 vs ledger Jiya-only ₹1,999 — invoice truth audit; (2) loop-dead evidence (proc/cron/mtime); (3) leads/ EMPTY claim; (4) WAHA health verdict (401 bina key = EXPECTED, with key 200 = HEALTHY); (5) reply_drafts auto_sent count correction (true=0/false=378 — PILOT ke purane 2204 draft note se actual file count alag — verify). (6) SAL-003 vendor DID proof post-09:00. 6 verdicts, 11:00 IST, PASS/FAIL + evidence file command_center/data. ACK GRD-003."},
    {"ts": ts, "from": "PILOT", "to": "success", "task_id": "SUC-002", "type": "UPDATE", "priority": "P0",
     "msg": f"SUC-002 ({ts_short}) — Jiya = only verified payer ₹1,999 (INV/2026-27/0001). Churn = revenue ₹0. DID-independent — 12:00 IST ACC: SMTP SENT artifact + WA follow-up + reply/fallback. ACK SUC-002."},
    {"ts": ts, "from": "PILOT", "to": "board", "task_id": "BRD-002", "type": "UPDATE", "priority": "P2",
     "msg": f"BRD-002 ({ts_short}) — mirror 3 files VPS pe present (tasks/bots/pinned). PILOT ab push karta hai fresh dispatch. TERA KAAM: live app page display verify + 30-min refresh cadence. ACC 12:00: page-check evidence. ACK BRD-002."},
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
    "SAL-003": f"{ts} PILOT {ts_short}: FRESH VPS — reply_drafts auto_sent true=0/false=378 (ZERO WA sends), hot_queue 09-01 CSV present 43/43 wa_link+UPI, no 09-02 queue. WAHA session WORKING (200 with real key earlier). ACC 09:00: WA>=10 + vendor DID.",
    "PLT-004": f"{ts} PILOT {ts_short}: re-test — api.vobiz.com 000 8.00s TCP-block (4+ days), SIP 5 vars len=0, TELEPHONY_PROVIDER=vobiz, /health 37a1daf8 OK.",
    "OPS-006": f"{ts} PILOT {ts_short}: loop DEAD 38h+ (batch 211 tail ok=0/fail=3, mtime Aug31 08:39:55Z, proc 0, cron 0). 10:30 digest.",
    "ENG-003": f"{ts} PILOT {ts_short}: watchdog missing (crontab 0). Spec >10min stale alert. 09:30 commit+runbook+watchdog.",
    "HNT-004": f"{ts} PILOT {ts_short}: leads/ EMPTY re-confirm (ls blank). 09:30 50-lead DND CSV.",
    "GRD-003": f"{ts} PILOT {ts_short}: +1 scope — auto_sent count correction true=0/false=378 (2204 note suspect). 6 verdicts 11:00.",
    "SUC-002": f"{ts} PILOT {ts_short}: Jiya proof due 12:00; only payer ₹1,999 churn-risk P0.",
    "BRD-002": f"{ts} PILOT {ts_short}: mirror 3/3 files present VPS; fresh push abhi.",
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

bots["Pilot"]["status"] = (f"{ts_short} IST REV-COMMAND: loop DEAD 38h+ (batch 211, proc 0, cron 0); SIP 5 vars len=0; "
                           f"api.vobiz.com 000 8s TCP-block 4+ days; WA sends 0 (auto_sent true=0/378 false); "
                           f"leads/ EMPTY; /health 37a1daf8 OK; hot-queue 43/43 WA+UPI ready. 0 ACK — nudge sent.")
bots["sales"]["status"] = (f"SAL-003 P0: WA sends ZERO (auto_sent true=0) — hot-queue 43 bhejo ABHI. "
                           f"Vendor DID proof 09:00 IST. ACK missing — REINFORCE sent.")
bots["platform"]["status"] = ("PLT-004 P0: api.vobiz.com 000 8s TCP-block (4+ days); SIP 5 vars len=0; TELEPHONY_PROVIDER=vobiz. Root-cause + Jio SIP template 09:00 IST. ACK missing.")
bots["operations"]["status"] = "OPS-006 P0: loop DEAD 38h+ re-confirm (proc 0, cron 0, mtime Aug31 08:39Z, batch 211). Restart sign = env swap; 10:30 digest. ACK missing."
bots["engineering"]["status"] = "ENG-003 P1: watchdog missing (crontab 0). WAHA probe /api/sessions X-Api-Key. Watchdog+runbook due 09:30. ACK missing."
bots["hunter"]["status"] = "HNT-004 P1: leads/ EMPTY re-confirm; 50-lead DND CSV due 09:30 IST. ACK missing."
bots["guardian"]["status"] = "GRD-003 P1: 6 verdicts due 11:00 IST (revenue-truth + loop-dead + WAHA + auto_sent count + leads + DID). ACK missing."
bots["success"]["status"] = "SUC-002 P0: Jiya email SENT proof due 12:00 IST; only payer ₹1,999 churn-risk. ACK missing."
bots["board"]["status"] = ("BRD-002 P2: mirror files present VPS; fresh push abhi PILOT. "
                           "Tera kaam: live page verify + 30-min cadence. Due 12:00 IST.")
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
pinned["vps_status"] = ("HEALTHY (37a1daf8, uptime 8h); calling loop DEAD 38h+ (mtime Aug31 08:39:55Z batch 211; proc 0; cron 0); "
                        "SIP env 5 vars EMPTY; Vobiz egress TCP-BLOCK 000 (8.00s, 4+ days); WA sent 0 (auto_sent true=0/378 false); leads/ EMPTY; "
                        "WAHA :3111 session WORKING with X-Api-Key (401 bina key = normal auth gate)")
pinned["verified_revenue"] = "₹1,999 (Jiya INV/2026-27/0001) — GRD-003 auditing revenue_snapshots claim active=3/MRR=5997"
pinned["gap"] = "₹4,98,001"
pinned["bottleneck"] = ("DID gate: vendor proof absent (SAL-003 09:00) + Vobiz egress TCP-block (PLT-004) + SIP creds empty + "
                        "loop dead no-watchdog (ENG-003/OPS-006) + ammo EMPTY (HNT-004). WA channel OPEN (WAHA working) — hot-queue 43 closes = aaj ka revenue path (0 sent so far).")
pinned["pipeline"] = "43 HOT interested leads (hot_queue 09-01.csv, 43/43 wa_link+UPI); 0 dialer connects (loop dead 38h+); 0 WA sends; Jiya P0"
pinned["action"] = ("SAL-003 WA >=10 + vendor DID 09:00 → PLT-004 egress root-cause 09:00 → ENG-003 watchdog 09:30 → "
                    "HNT-004 CSV 09:30 → OPS-006 10:30 digest → GRD-003 11:00 verdicts → SUC-002 Jiya 12:00 → BRD-002 page verify")
pinned["next_expected_payment"] = "Hot-queue WA close (UPI deep-link) ya Jiya retention ya pehla post-DID sale — vaada nahi, evidence ke saath"
with open(pinned_path, "w", encoding="utf-8") as f:
    json.dump(pinned, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(f"PINNED: refreshed @ {ts}")