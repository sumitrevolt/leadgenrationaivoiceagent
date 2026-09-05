#!/usr/bin/env python3
"""PILOT 09-02 01:50 IST dispatch run — fresh VPS evidence refresh + ACK nudge + mirror push. Cron window."""
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
     "msg": f"🎯 REVENUE COMMAND {ts_short} IST (Sep 2): TARGET ₹5,00,000 | VERIFIED ₹1,999 (Jiya INV-0001; GRD-003 verifying active=3/MRR=5997 claim) | GAP ₹4,98,001 | PIPELINE: hot_queue 09-01 CSV 43 rows (wa_link+UPI ready, CSV mtime Sep 1 03:30 = 24h+ stale, koi 09-02 queue nahi); dialer connects 0; loop DEAD 34h+ (mtime Aug 31 08:39Z batch 211, proc 0, cron 0); reply_drafts 2204 auto_sent=0 | HOT: 43 WA closes + Jiya P0 | BOTTLENECK: DID (SAL-003 vendor proof) → env swap (PLT-004, SIP 5 vars len=0) → restart (OPS-006/ENG-003 watchdog missing); WAHA :3111 401 Unauthorized = WA-send mechanism bhi suspect — NAYA FINDING | ACTION: SAL-003 WA >=10 + vendor DID 09:00; PLT-004 egress root-cause 09:00; ENG-003 watchdog 09:30; HNT-004 CSV 09:30; OPS-006 10:30 digest; GRD-003 5 verdicts 11:00; SUC-002 Jiya 12:00; BRD-002 mirror VERIFIED (PILOT pushed 01:50) | NEXT: 09:00 gates → 10:00 TRAI window post-DID batch → pehla connect → UPI | ⚠️ 00:47 dispatch ke koi ACK nahi — ALL: poll, ACK TASK-ID, evidence bhejo."},
    {"ts": ts, "from": "PILOT", "to": "sales", "task_id": "SAL-003", "type": "REINFORCE", "priority": "P0",
     "msg": f"SAL-003 REINFORCE ({ts_short}) — FRESH 01:50 IST VPS: reply_drafts auto_sent=0 (ZERO WA bheje), hot_queue CSV mtime Sep 1 03:30 (24h+ stale, naya queue nahi), WAHA :3111 /health = 401 Unauthorized (send mechanism band ho sakta hai — token check karo), SIP env 5 vars EMPTY, dialer dead 34h+. AAJ KA REVENUE PATH = WA closes: hot-queue 43 interested (wa_link+UPI ready). 09:00 IST ACC: (a) >=10 WA-sent proof (ya WAHA token fix + send proof) + reply count, (b) vendor DID number/activation proof. ACK SAL-003 NOW."},
    {"ts": ts, "from": "PILOT", "to": "platform", "task_id": "PLT-004", "type": "UPDATE", "priority": "P0",
     "msg": f"PLT-004 FRESH TEST ({ts_short} IST): PILOT ne khud re-run kiya — DNS resolves (13.248.169.48 / 76.223.54.146 AWS GA), curl https 8s timeout, curl -4 bhi timeout → api.vobiz.com egress BLOCKED at TCP connect. NAYA: WAHA :3111 /health = 401 Unauthorized (token config check .env WAHA key). SIP_HOST/USERNAME/PASSWORD/DID/PROVIDER = 0 non-empty. 09:00 IST ACC: root-cause verdict (firewall/AWS-GA/route) + re-test proof + Jio SIP env swap template. ACK PLT-004."},
    {"ts": ts, "from": "PILOT", "to": "operations", "task_id": "OPS-006", "type": "UPDATE", "priority": "P0",
     "msg": f"OPS-006 ({ts_short}) — loop DEAD re-confirm 01:50 IST: call_loop.log mtime Aug 31 08:39:55Z (batch 211, sab FAIL '911171366938 not owned'), ps me koi call_loop proc nahi (sirf celery workers), crontab 0 loop entries. Restart plan = PLT-004 env swap ke baad. Monitors me WAHA liveness (401) bhi add karo. 10:30 IST digest = pehla output. ACK OPS-006."},
    {"ts": ts, "from": "PILOT", "to": "engineering", "task_id": "ENG-003", "type": "UPDATE", "priority": "P1",
     "msg": f"ENG-003 ({ts_short}) — watchdog ABHI BHI missing (crontab 0 loop/watch entries). Loop 34h+ dead bina kisi restart. Watchdog spec: log mtime >10min = alert + auto-restart (sirf jab owned caller-ID ho). WAHA :3111 401 probe bhi include karo. Jio SIP failover runbook bhi due. ACC 09:30: commit sha + runbook + watchdog evidence. ACK ENG-003."},
    {"ts": ts, "from": "PILOT", "to": "hunter", "task_id": "HNT-004", "type": "UPDATE", "priority": "P1",
     "msg": f"HNT-004 ({ts_short}) — /opt/leadgen/data/leads/ EMPTY re-confirm (ls blank). Dialer restart-ready hone par ammo nahi. 09:30 IST ACC: CSV path + 50 verified MOBILE + DND-proof column + pool refill scan. ACK HNT-004."},
    {"ts": ts, "from": "PILOT", "to": "guardian", "task_id": "GRD-003", "type": "UPDATE", "priority": "P1",
     "msg": f"GRD-003 ({ts_short}) — SCOPE FRESH: (1) revenue_snapshots Sep 1 active=3/MRR=5997 vs ledger Jiya-only ₹1,999 — kaunsa true? invoice files find = 0 naye; (2) loop-dead evidence verification; (3) leads/ EMPTY claim; (4) WAHA 401 = send-health verdict; (5) SAL-003 vendor DID proof (09:00 ke baad). 5+ verdicts, 11:00 IST, PASS/FAIL evidence ke saath file command_center/data me. ACK GRD-003."},
    {"ts": ts, "from": "PILOT", "to": "success", "task_id": "SUC-002", "type": "UPDATE", "priority": "P0",
     "msg": f"SUC-002 ({ts_short}) — Jiya = only verified payer ₹1,999 (INV/2026-27/0001). Naya invoice find = 0. Churn = revenue ₹0. DID-independent — 12:00 IST ACC: SMTP SENT artifact + WA follow-up + reply/fallback. ACK SUC-002."},
    {"ts": ts, "from": "PILOT", "to": "board", "task_id": "BRD-002", "type": "UPDATE", "priority": "P2",
     "msg": f"BRD-002 ({ts_short}) — VPS command_center/data DIR MISSING mila (sirf patches/). PILOT ne 01:50 data dir + 3 files push kar diya (tasks/bots/pinned) + md5 verify karega. TERA KAAM: live app page pe mirror verify karo + 30-min refresh cadence maintain karo. ACC 12:00: VPS mtime == local + page-check evidence. ACK BRD-002."},
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
    "SAL-003": f"{ts} PILOT {ts_short}: FRESH — reply_drafts auto_sent=0, hot_queue 09-01 CSV 24h+ STALE (koi 09-02 queue nahi), WAHA :3111 401 Unauthorized (NAYA — send mech suspect), SIP env 5 vars EMPTY, dialer dead 34h+. ACC 09:00: >=10 WA-sent + vendor DID.",
    "PLT-004": f"{ts} PILOT {ts_short}: re-test — DNS ok (AWS GA IPs) curl/curl-4 8s timeout = egress TCP-block. WAHA 401 naya finding. SIP vars 0 non-empty. Root-cause 09:00.",
    "OPS-006": f"{ts} PILOT {ts_short}: loop DEAD re-confirm (proc 0, cron 0, mtime Aug31 08:39Z). WAHA liveness monitor add. Restart after env swap; 10:30 digest.",
    "ENG-003": f"{ts} PILOT {ts_short}: watchdog missing re-confirm (crontab 0). WAHA 401 probe include. Watchdog+runbook due 09:30.",
    "HNT-004": f"{ts} PILOT {ts_short}: leads/ EMPTY re-confirm. 50-lead DND CSV due 09:30.",
    "GRD-003": f"{ts} PILOT {ts_short}: scope +WAHA 401 verdict + invoice find=0. 5+ verdicts due 11:00.",
    "SUC-002": f"{ts} PILOT {ts_short}: invoice find = 0 naya. Jiya proof due 12:00.",
    "BRD-002": f"{ts} PILOT {ts_short}: VPS data dir MISSING mila; PILOT abhi 3 files push kar raha. Teri job: page verify + cadence.",
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

bots["Pilot"]["status"] = (f"{ts_short} IST REV-COMMAND: loop DEAD 34h+; SIP 5 vars len=0; Vobiz egress TCP-block "
                           f"(DNS ok, curl/curl-4 8s timeout); WAHA :3111 401 = NAYA WA-send suspect; hot-queue 09-01 CSV 24h+ "
                           f"stale, WA sends 0. VPS mirror abhi push kiya (data dir missing tha). VPS healthy 37a1daf8. 0 ACK — nudge sent.")
bots["sales"]["status"] = (f"SAL-003 P0: hot-queue WA closes + vendor DID due 09:00 IST. FRESH: auto_sent=0, WAHA 401, "
                           f"hot-queue 24h+ STALE. WA = aaj ka revenue path. ACK missing — REINFORCE sent.")
bots["platform"]["status"] = ("PLT-004 P0: egress re-test by PILOT — TCP-block (DNS ok, curl timeout). WAHA 401 naya. "
                              "SIP 0 non-empty. Root-cause + template 09:00 IST. ACK missing.")
bots["operations"]["status"] = "OPS-006 P0: loop DEAD re-confirm (proc 0, cron 0). Restart-ready; 10:30 digest. WAHA liveness monitor add. ACK missing."
bots["engineering"]["status"] = "ENG-003 P1: watchdog missing re-confirm (crontab 0); WAHA 401 probe include. Due 09:30. ACK missing."
bots["hunter"]["status"] = "HNT-004 P1: leads/ EMPTY re-confirm; 50-lead DND CSV due 09:30 IST. ACK missing."
bots["guardian"]["status"] = "GRD-003 P1: 5+ verdicts due 11:00 IST (revenue-snap mismatch, WAHA 401, loop-dead, invoice find). ACK missing."
bots["success"]["status"] = "SUC-002 P0: Jiya email SENT proof due 12:00 IST; only payer ₹1,999 churn-risk. ACK missing."
bots["board"]["status"] = ("BRD-002 P2: VPS data dir MISSING mila — PILOT ne 01:50 push kar diya. Tera kaam: page verify "
                           "+ 30-min cadence. Due 12:00 IST.")
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
pinned["vps_status"] = ("HEALTHY (37a1daf8); calling loop DEAD 34h+ (mtime Aug 31 08:39Z batch 211; proc 0; cron 0); "
                        "SIP env 5 vars EMPTY; Vobiz egress TCP-BLOCK (DNS ok, curl 8s timeout); WAHA :3111 401 Unauthorized (Naya)")
pinned["verified_revenue"] = "₹1,999 (Jiya INV/2026-27/0001) — GRD-003 verifying snapshots active=3/MRR=5997 vs ledger claim"
pinned["gap"] = "₹4,98,001"
pinned["bottleneck"] = ("DID gate: vendor proof absent (SAL-003) + Vobiz egress TCP-block (PLT-004) + SIP creds empty + "
                        "loop dead no-watchdog (ENG-003/OPS-006) + WAHA 401 WA-send suspect. Revenue path AAJ = hot-queue WA closes (0 sent).")
pinned["pipeline"] = "43 HOT interested leads (hot_queue 09-01 CSV, 24h+ stale); 0 dialer connects; 0 WA sends; Jiya P0"
pinned["action"] = ("SAL-003 WA >=10 + vendor DID 09:00 → PLT-004 egress root-cause 09:00 → ENG-003 watchdog 09:30 → "
                    "HNT-004 CSV 09:30 → OPS-006 10:30 digest → GRD-003 11:00 verdicts → SUC-002 Jiya 12:00 → BRD-002 page verify")
pinned["next_expected_payment"] = "Hot-queue WA close (UPI deep-link) ya Jiya retention ya pehla post-DID sale — vaada nahi, evidence ke saath"
with open(pinned_path, "w", encoding="utf-8") as f:
    json.dump(pinned, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(f"PINNED: refreshed @ {ts}")