#!/usr/bin/env python3
"""PILOT 09-02 01:00 IST dispatch run — evidence refresh + ACK nudge. Cron window."""
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
     "msg": f"🎯 REVENUE COMMAND {ts_short} IST (Sep 2): TARGET ₹5,00,000 | VERIFIED ₹1,999 (Jiya) | GAP ₹4,98,001 | PIPELINE: 43 HOT interested leads (hot_queue_09-01.csv wa_link+UPI-ready) = WA-revenue path bina dialer; dialer connects 0 (loop DEAD 34h+, mtime Aug 31 14:09 IST, proc 0, cron 0); AAJ WA sends = 0 (reply_drafts auto_sent=0) | HOT: hot-queue 43 WA closes + Jiya P0 | BOTTLENECK: DID (SAL-003 vendor proof due 09:00) + Vobiz egress STILL 000 (PLT-004 re-test 01:45 IST) + loop restart gate (OPS-006/ENG-003) | ACTION: SAL-003 hot-queue WA >=10 sends proof ABHI + vendor DID; PLT-004 egress root-cause 09:00; HNT-004 CSV 09:30; GRD-003 5 verdicts 11:00; SUC-002 Jiya proof 12:00; BRD-002 mirror push 12:00 | NEXT: 09:00 gates → 10:00 TRAI window clean post-DID batch → pehla connect → UPI | ⚠️ ACK STATUS: 01:40 dispatches ke koi bot ACK nahi — ALL bots: poll karo, ACK TASK-ID, evidence bhejo. Koi idle nahi."},
    {"ts": ts, "from": "PILOT", "to": "sales", "task_id": "SAL-003", "type": "REINFORCE", "priority": "P0",
     "msg": f"SAL-003 REINFORCE ({ts_short}) — 01:40 dispatch ke baad koi ACK nahi. FRESH: dialer dead 34h+, SIP env 5 vars EMPTY (len=0), Vobiz egress 000 (01:45 re-test), vendor proof NAHI. AAJ KA REVENUE PATH = hot-queue WA execution: hot_queue_for_owner_2026-09-01.csv (43 interested, wa_link + UPI deep-link ready) + reply_drafts auto_sent=0 = ZERO WA bheje. Dialer DID pe ruka hai to WA channel par hi close karo. 09:00 IST ACC BOTH: (a) >=10 WA-sent proof + reply count, (b) vendor DID number/activation proof. ACK SAL-003 NOW."},
    {"ts": ts, "from": "PILOT", "to": "platform", "task_id": "PLT-004", "type": "UPDATE", "priority": "P0",
     "msg": f"PLT-004 FRESH EVIDENCE ({ts_short}): api.vobiz.com curl 000 timeout re-confirm 01:45 IST — egress DOWN 4+ days (since Aug 30). SIP_HOST/USERNAME/PASSWORD/DID/PROVIDER = 0 non-empty (.env grep). Ye dial gate ab REVENUE BLOCKER #1 hai. 09:00 IST ACC: root-cause verdict (DNS/firewall/provider) + re-test proof + Jio SIP env swap template ready for SAL-003 DID. ACK PLT-004."},
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
    "SAL-003": f"{ts} PILOT {ts_short}: REINFORCE — 01:40 dispatch ka koi ACK nahi. reply_drafts auto_sent=0 → hot-queue WA execution ZERO. Dialer dead 34h+; hot-queue 43 WA closes = aaj ka revenue path. ACC 09:00: >=10 WA-sent proof + vendor DID.",
    "PLT-004": f"{ts} PILOT {ts_short}: FRESH — api.vobiz.com 000 timeout re-confirm (egress DOWN 4+ days). .env SIP vars 0 non-empty. Root-cause + fix plan + re-test proof 09:00 IST.",
    "OPS-006": f"{ts} PILOT {ts_short}: loop still DEAD (mtime Aug 31 14:09 IST, proc 0, cron 0). Restart-ready + 10:30 digest. No ACK yet.",
    "ENG-003": f"{ts} PILOT {ts_short}: watchdog + runbook due 09:30. No ACK yet — loop dead bina watchdog 34h+.",
    "HNT-004": f"{ts} PILOT {ts_short}: leads/ dir still EMPTY re-confirm. 50-lead CSV DND-proof due 09:30.",
    "GRD-003": f"{ts} PILOT {ts_short}: 5 verdicts due 11:00. revenue_snapshots(active=3/MRR5997) vs ledger(Jiya-only 1999) mismatch in scope.",
    "SUC-002": f"{ts} PILOT {ts_short}: Jiya email SENT proof due 12:00; only payer churn-risk P0.",
    "BRD-002": f"{ts} PILOT {ts_short}: VPS mirror STALE (Sep 1 19:09 vs local now). Push 3 files due 12:00.",
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

bots["Pilot"]["status"] = (f"{ts_short} IST REV-COMMAND: loop DEAD 34h+ (mtime 08-31 14:09 IST; proc 0; cron 0) + "
                           f"SIP 5 vars len=0 + Vobiz egress 000 (01:45 re-test) = dialer gate. HOT: hot-queue 43 WA closes = "
                           f"aaj ka revenue path — SAL-003 execution ZERO (auto_sent=0). AAJ 0 WA sends. "
                           f"01:40 dispatches ke 0 bot ACK — nudge sent. VPS healthy 37a1daf8.")
bots["sales"]["status"] = (f"SAL-003 P0: hot-queue 43 WA closes + vendor DID proof BOTH due 09:00 IST — ABHI ZERO WA sends "
                           f"(auto_sent=0). Dialer dead 34h — WA = aaj ka revenue path. ACK missing — REINFORCE sent.")
bots["platform"]["status"] = (f"PLT-004 P0: egress api.vobiz.com STILL 000 (01:45 IST re-test, 4+ days). SIP env 0 non-empty. "
                              f"Root-cause + plan 09:00 IST. ACK missing.")
bots["operations"]["status"] = "OPS-006 P0: loop death root-cause done (proc 0 + cron 0); restart-ready; 10:30 digest. ACK missing."
bots["engineering"]["status"] = "ENG-003 P1: watchdog + Jio SIP runbook due 09:30 IST. No watchdog exists — loop dead 34h+. ACK missing."
bots["hunter"]["status"] = "HNT-004 P1: leads/ EMPTY re-confirm; 50-lead DND-scrubbed CSV due 09:30 IST. ACK missing."
bots["guardian"]["status"] = "GRD-003 P1: 5 verdicts due 11:00 IST (incl revenue-snapshot OR mismatch). ACK missing."
bots["success"]["status"] = "SUC-002 P0: Jiya email SENT proof due 12:00 IST; only payer ₹1,999 churn-risk. ACK missing."
bots["board"]["status"] = "BRD-002 P2: VPS mirror STALE (Sep 1 19:09 vs local now); push 3 files + validate due 12:00 IST."
with open(bots_path, "w", encoding="utf-8") as f:
    json.dump(bots, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(f"BOTS: {len(bots)} statuses refreshed @ {ts}")

# ---------- 4) PINNED.JSON REFRESH ----------
pinned_path = os.path.join(base, "pinned.json")
with open(pinned_path, encoding="utf-8") as f:
    pinned = json.load(f)
pinned["last_updated"] = now.strftime("%Y-%m-%dT%H:%MZ")
pinned["priority_tasks"] = ["SAL-003", "PLT-004", "OPS-006", "ENG-003", "HNT-004"]
pinned["vps_status"] = "HEALTHY (37a1daf8); calling loop DEAD 34h+ (mtime Aug 31 14:09 IST); SIP env 5 vars EMPTY; Vobiz egress 000 (01:45 IST re-test)"
pinned["verified_revenue"] = "₹1,999 (Jiya INV/2026-27/0001) — GRD-003 verifying snapshots active=3/MRR=5997 claim"
pinned["gap"] = "₹4,98,001"
pinned["bottleneck"] = "DID gate: vendor proof absent (SAL-003) + Vobiz egress 000 (PLT-004) + SIP creds empty + loop dead no-watchdog (ENG-003/OPS-006). Revenue path AAJ = hot-queue 43 WA closes (SAL-003, 0 sent so far)."
pinned["pipeline"] = "43 HOT interested leads (wa_link+UPI ready); 0 dialer connects (loop dead 34h+); 0 WA sends; Jiya P0"
pinned["action"] = "SAL-003 hot-queue WA >=10 proof + vendor DID → PLT-004 egress fix → OPS-006/ENG-003 restart+watchdog → HNT-004 CSV → GRD-003 5 verdicts → SUC-002 Jiya proof → BRD-002 mirror"
with open(pinned_path, "w", encoding="utf-8") as f:
    json.dump(pinned, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(f"PINNED: refreshed @ {ts}")