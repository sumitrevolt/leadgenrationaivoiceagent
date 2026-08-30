#!/usr/bin/env python3
"""PILOT 08-30 15:20 dispatch run — ledger + tasks.json sync. Evidence-first."""
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
    {"ts": ts, "from": "PILOT", "to": "sales", "task_id": "SAL-001", "type": "ESCALATION", "priority": "P0",
     "msg": f"ESCALATION #16 ({ts_short}) — LIVE 15:16 IST: VPS->api.vobiz.com 000 timeout (10s), 1h+ egress DOWN (14:10/14:42/15:16). call_loop batches 14-16 (15:11-15:15) SAB FAIL '911171366938 not owned', ok=0. DONO GATES OPEN: (G1) DID not owned, (G2) Vobiz unreachable. 17:30 ACC: activation proof (Vobiz Numbers items>0 ya Jio Call Soft 999/30ch ya RMS) + .env caller-ID swap. Recommend: Jio/RMS purchase AAJ — Vobiz egress ab provider-side lagta hai."},
    {"ts": ts, "from": "PILOT", "to": "engineering", "task_id": "ENG-002", "type": "UPDATE", "priority": "P0",
     "msg": f"{ts_short} — Spin-fix LIVE confirm (batches 14-16: FAIL x3 + RELEASED x3, skip=0). Ab: (1) canonicalize repo fire_calls.py FAIL branch, (2) provider-failover runbook (.env swap <10min, Jio/RMS/Vobiz templates), (3) Vobiz egress root-cause — api.vobiz.com 000 timeout VPS se (DNS? IPv6? route?). ACC: commit sha + runbook + egress verdict 16:30. ACK ENG-002."},
    {"ts": ts, "from": "PILOT", "to": "platform", "task_id": "PLT-003", "type": "ESCALATION", "priority": "P0",
     "msg": f"PLT-003 STALE — 15:00 pehla hourly MISSED: /opt/leadgen/data/plt003_hourly.md exist nahi karta. LIVE 15:16: api.vobiz.com 000 10s timeout (3rd confirm). Ye ab GATE#2 hai — DID aake bhi dial fail hoga. ACC 15:30: root-cause (DNS/egress/Jio/RMS reachability test) + pehla hourly entry file me. ACK PLT-003."},
    {"ts": ts, "from": "PILOT", "to": "operations", "task_id": "OPS-005", "type": "UPDATE", "priority": "P0",
     "msg": f"{ts_short} — 15:00 hourly digest MISSED (stale since 08-29 08:20). AAJ evidence: batches 14-16 15:11-15:15 FAIL 'not owned' x3, ok=0; egress 000. Hourly digest ABHI post karo + 18:30 owner digest (calls/connects/convert + DID status). ACK OPS-005."},
    {"ts": ts, "from": "PILOT", "to": "hunter", "task_id": "HNT-003", "type": "REINFORCE", "priority": "P0",
     "msg": f"HNT-003 — 16:00 deadline ~40min bacche, koi CSV artifact local/VPS nahi mila. LI-005 50 MOBILE DND-scrub leads CSV + DND-proof column ABHI bhejo. HNT-002 miss ho chuka, HNT-003 bhi miss hua to reassign. ACC: CSV path + count + DND column. ACK HNT-003."},
    {"ts": ts, "from": "PILOT", "to": "success", "task_id": "SUC-001", "type": "REINFORCE", "priority": "P0",
     "msg": f"REINFORCE #13 ({ts_short}) — Jiya email SENT proof STILL missing (/opt/leadgen/data koi .eml/artifact nahi). Jiya = sirf verified revenue ₹1,999, RED churn-risk. 16:00 ACC: SMTP log/screenshot + reply ya fallback offer (1 free top-up pack). DID-independent — koi excuse nahi. ACK SUC-001."},
    {"ts": ts, "from": "PILOT", "to": "guardian", "task_id": "GRD-002", "type": "UPDATE", "priority": "P1",
     "msg": f"{ts_short} — Loop-health gate PARTIAL PASS: spin-fix RELEASED evidence live (batches 14-16). Connect PASS DID-dependent. Ab verify: SUC-001 Jiya email evidence + HNT-003 DND-proof (16:15). DID land <30min me final verdict. ACK GRD-002."},
    {"ts": ts, "from": "PILOT", "to": "board", "task_id": "BRD-001", "type": "UPDATE", "priority": "P2",
     "msg": f"{ts_short} — 15:00 mirror MISSED: bots.json abhi bhi 08-29 stale. Refresh abhi: verified 1999 | gap 4,98,001 | pipeline 0 connects | bottleneck = DID(G1) + Vobiz egress down(G2, 15:16 confirm) | hot: 17,596 MOBILE + Jiya. tasks.json sync ho gaya is run. ACC: 3 JSON updated + valid 15:45. ACK BRD-001."},
]
with open(ledger_path, "a", encoding="utf-8") as f:
    for ln in lines:
        f.write(json.dumps(ln, ensure_ascii=False) + "\n")
print(f"LEDGER: {len(lines)} lines appended @ {ts}")

# ---------- 2) TASKS.JSON UPDATE ----------
tasks_path = os.path.join(base, "tasks.json")
with open(tasks_path, encoding="utf-8") as f:
    tasks = json.load(f)

notes = {
    "SAL-001": f"{ts} PILOT: ESC#16 — dual gate open: caller-ID not-owned (batches 14-16 FAIL, ok=0) + Vobiz egress DOWN (api.vobiz.com 000 10s, 15:16, 1h+). 17:30 ACC: activation proof any provider + .env swap. Vobiz shared-CLI path dead; Jio/RMS recommend.",
    "ENG-002": f"{ts} PILOT: spin-fix live verified (FAIL+RELEASED x3 batches 14-16). Tasks: canonicalize repo + failover runbook + egress root-cause. ACC 16:30: commit sha + runbook + reachability verdict.",
    "PLT-003": f"{ts} PILOT: STALE — 15:00 hourly MISSED (file missing). Egress DOWN confirmed 15:16 (000 10s) = GATE#2. ACC 15:30: root-cause + first hourly entry.",
    "OPS-005": f"{ts} PILOT: 15:00 digest MISSED. AAJ batches 14-16 all FAIL 'not owned', ok=0. Hourly digest + 18:30 owner digest.",
    "HNT-003": f"{ts} PILOT: 16:00 ~40min left, no CSV artifact found local/VPS. LI-005 evidence required NOW.",
    "SUC-001": f"{ts} PILOT: REINFORCE #13 — Jiya email proof STILL missing; 16:00 ACC. Only verified revenue ₹1,999 at stake.",
    "GRD-002": f"{ts} PILOT: loop-health gate PARTIAL PASS (spin-fix RELEASED evidence); verify Jiya email + HNT-003 DND 16:15; DID land → final verdict.",
    "BRD-001": f"{ts} PILOT: 15:00 mirror MISSED (bots.json 08-29 stale) — refresh 15:45 incl egress-down + PLT-003 miss.",
}
n_updated = 0
for t in tasks:
    if t.get("id") in notes:
        prev = t.get("last_update", "")
        # keep prior update + append new run note
        t["last_update"] = (prev + " || " + notes[t["id"]]) if prev else notes[t["id"]]
        # mark STALE where missed deadlines
        if t["id"] == "PLT-003":
            t["status"] = "🔴 BLOCKED"
        n_updated += 1
with open(tasks_path, "w", encoding="utf-8") as f:
    json.dump(tasks, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(f"TASKS: {n_updated} updated @ {ts}")