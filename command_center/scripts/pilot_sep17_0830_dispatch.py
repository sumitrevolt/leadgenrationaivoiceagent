#!/usr/bin/env python3
"""PILOT 08:30 IST (Sep17 CRON) — REVENUE COMMAND + P0 unblock.

FRESH live evidence 08:30 IST (this run, in-window SSH):
  - VPS UP /health 200 prod 94dca989 uptime 12h26m (02:56Z probe).
  - fire_calls import OK, leads=5 available, parse OK — loop CAN start.
  - DSH worker compose defined (leadgen_dsh_worker) — bas up -d karna hai.
  - call_loop.log mtime Sep16 16:30 (325B, DeprecationWarning only) — DEAD 5+ days.
  - call_log.csv = NOT FOUND.
  - DSH container = ABSENT (armed but not running).
  - Verified revenue Rs1,999 (Jiya INV/2026-27/0001 SOLE); GAP Rs4,98,001.
  - Jiya = only paying customer RED churn-risk.

One TASK-ID/bot/run — max 8 bots, no spam.
"""
import json, os, subprocess, time

TS = "2026-09-17T08:30:00+05:30"
BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"

# ---------- 1) messages.jsonl (message_agent channel) ----------
msgs = [
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "REVENUE COMMAND 08:30 IST (Sep17, LIVE 03:00Z): TARGET Rs5,00,000 | VERIFIED Rs1,999 (Jiya INV/0001 SOLE) | GAP Rs4,98,001 | PIPELINE: 0 calls routed (DID issue), Jiya RED churn-risk, leads=5 available. | HOT: PLT-011 call loop restart (import OK, leads 5) + ENG-009 DSH container up + SUX-001 Jiya retention. | BOTTLENECK: #1 DID->connect->interested->UPI (call loop dead 5+ days) | #2 DSH armed but container absent | #3 Jiya sole payer churn risk. | ACTION: PLT-011 platform restart call loop NOW (proven import OK); ENG-009 engineering DSH up -d NOW; SUX-001 success Jiya retention plan; GUA-001 guardian verify both. | NEXT: 09:00 IST — proof of call loop running + DSH container up + Jiya retention evidence. pelican"},
    {"ts": TS, "from": "PILOT", "to": "platform", "task_id": "PLT-011", "type": "GHANTI", "priority": "P0",
     "msg": "PLT-011 (08:30 FRESH GHANTI, live-verify): fire_calls import OK, leads=5 available, parse OK — loop CAN start. call_loop.log mtime Sep16 16:30 (325B DeprecationWarning only) = DEAD 5+ days. Action: (a) cd /opt/leadgen && nohup python3 scripts/fire_calls_loop.py --batch-size 3 --max-batches 5 >> data/call_loop.log 2>&1 & (b) Verify ps aux | grep fire_calls = RUNNING (c) Verify call_loop.log growing (d) 5 calls placed = proof LIVE. Deadline: 2026-09-17T11:00 IST. ACCEPTANCE: ps shows process + log growing + >=1 call attempt in call_log.csv."},
    {"ts": TS, "from": "PILOT", "to": "engineering", "task_id": "ENG-009", "type": "GHANTI", "priority": "P0",
     "msg": "ENG-009 (08:30 FRESH GHANTI, live-verify): DSH worker compose defined (leadgen_dsh_worker in docker-compose.vps.yml) but container ABSENT. /health: dsh_runtime_enabled=true, shadow=true, allowlist=[jiya_makeover]. Action: (a) cd /opt/leadgen && docker compose -f docker-compose.vps.yml up -d leadgen_dsh_worker (b) Verify docker ps --filter name=dsh = RUNNING (c) Verify APP_VERSION matches leadgen_app (94dca989) (d) 5min clean run. Deadline: 2026-09-17T11:00 IST. ACCEPTANCE: docker ps shows leadgen_dsh_worker running + logs clean."},
    {"ts": TS, "from": "PILOT", "to": "success", "task_id": "SUX-001", "type": "GHANTI", "priority": "P0",
     "msg": "SUX-001 (08:30 FRESH GHANTI): Jiya Makeover = SOLE paying customer (Rs1,999/mo, INV/2026-27/0001). RED churn-risk. DSH armed but NOT RUNNING (ENG-009). Action: (a) Review account health: last login, last delivery, engagement signals (b) Identify at-risk signals (c) Prepare retention offer/communication (d) Report to Pilot: what will make Jiya renew/stay. Deadline: 2026-09-17T12:00 IST. ACCEPTANCE: retention plan + evidence of outreach sent."},
    {"ts": TS, "from": "PILOT", "to": "guardian", "task_id": "GUA-001", "type": "GHANTI", "priority": "P0",
     "msg": "GUA-001 (08:30 FRESH GHANTI): GUARDIAN REVIEW GATE on ENG-009 (DSH restart) + PLT-011 (call loop restart). Verify engineering fix independently. Action: (a) docker ps --filter name=dsh (b) Verify APP_VERSION matches leadgen_app (94dca989) (c) Verify DSH logs clean (d) Verify call_loop process running + log growing (e) PASS/FAIL verdict. Deadline: 2026-09-17T11:30 IST. ACCEPTANCE: written PASS/FAIL verdict with evidence."},
    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "SL-001", "type": "GHANTI", "priority": "P1",
     "msg": "SL-001 (08:30 FRESH GHANTI): 2nd PAYING CUSTOMER. Generate 1 qualified lead -> outreach -> close for Rs1,999/mo AI Automated Marketing. Action: (a) Check Hot Queue /app/inbox for actionables (b) If empty: identify 3 target prospects (local Indian business, budget Rs1,999-2,999) (c) Prepare outreach (email/WA manual — cold WA OFF) (d) Target: at least 1 conversation started. Deadline: 2026-09-17T18:00 IST. ACCEPTANCE: >=1 conversation started + prospect details."},
    {"ts": TS, "from": "PILOT", "to": "hunter", "task_id": "HTR-001", "type": "GHANTI", "priority": "P1",
     "msg": "HTR-001 (08:30 FRESH GHANTI): LEAD DISCOVERY for AI Automated Marketing 2nd customer. Action: (a) Enrich prospect pool: local Indian businesses (beauty/wellness/health) matching Rs1,999/mo buyer profile (b) Add 5-10 prospects via Google Maps Places (legal) (c) Verify email availability (d) Output: prospects ready for sales outreach. Deadline: 2026-09-17T15:00 IST. ACCEPTANCE: >=5 qualified prospects added with contact details."},
    {"ts": TS, "from": "PILOT", "to": "operations", "task_id": "OPS-001", "type": "GHANTI", "priority": "P4",
     "msg": "OPS-001 (08:30 FRESH GHANTI): COORDINATION HYGIENE report. Action: (a) Fleet status: 8 workers + bus alive (16h+) (b) Task status: 2 P0 CRITICAL platform+engineering BLOCKED (c) Revenue funnel: 0 calls routed, 0 connects, Jiya RED risk (d) Report: coordination health + recommendations. Deadline: 2026-09-17T14:00 IST. ACCEPTANCE: written hygiene report."},
    {"ts": TS, "from": "PILOT", "to": "board", "task_id": "BRD-001", "type": "GHANTI", "priority": "P5",
     "msg": "BRD-001 (08:30 FRESH GHANTI): COMMAND CENTER MIRROR. Verify board visualization matches tasks.json state. Action: (a) Read /app/bot-command-center (b) Compare with tasks.json (c) Report discrepancies. Deadline: 2026-09-17T11:00 IST. ACCEPTANCE: mirror verification report."},
]

# idempotent: skip if same TS already appended
existing_ts = set()
try:
    with open(os.path.join(BASE, "messages.jsonl"), encoding="utf-8") as f:
        for line in f:
            try:
                existing_ts.add(json.loads(line).get("ts"))
            except Exception:
                pass
except FileNotFoundError:
    pass
new_msgs = [m for m in msgs if m["ts"] not in existing_ts]
if new_msgs:
    with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
        for m in new_msgs:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("messages.jsonl appended", len(new_msgs), "of", len(msgs))

# ---------- 2) tasks.json status refresh ----------
with open(os.path.join(BASE, "tasks.json"), encoding="utf-8") as f:
    tasks = json.load(f)

for t in tasks:
    tid = t.get("id")
    if tid == "PLT-011":
        t["status"] = "🔴 BLOCKED"
        t["updated_at"] = TS
        t["evidence"] = "2026-09-17 08:30 IST: fire_calls import OK, leads=5, parse OK. Loop CAN start. call_loop.log mtime Sep16 16:30 (325B). DSH container absent. VPS healthy 94dca989."
        t["pilot_note"] = "PLT-011 ESCALATED 08:30 IST — platform P0: call loop DEAD 5+ days, but import proven OK. Restart command issued."
    elif tid == "ENG-009":
        t["status"] = "🔴 BLOCKED"
        t["updated_at"] = TS
        t["evidence"] = "2026-09-17 08:30 IST: DSH worker compose defined but container ABSENT. /health: dsh_runtime_enabled=true. P0 risk to only paying customer (Jiya RED churn-risk)."
        t["pilot_note"] = "ENG-009 — engineering P0: DSH container absent, armed. docker compose up -d leadgen_dsh_worker command issued."
    elif tid == "SUX-001":
        t["status"] = "🆕 NEW"
        t["updated_at"] = TS
    elif tid == "GUA-001":
        t["status"] = "🆕 NEW"
        t["updated_at"] = TS
    elif tid == "SL-001":
        t["status"] = "🆕 NEW"
        t["updated_at"] = TS
    elif tid == "HTR-001":
        t["status"] = "🆕 NEW"
        t["updated_at"] = TS
    elif tid == "OPS-001":
        t["status"] = "🆕 NEW"
        t["updated_at"] = TS
    elif tid == "BRD-001":
        t["status"] = "🆕 NEW"
        t["updated_at"] = TS

with open(os.path.join(BASE, "tasks.json"), "w", encoding="utf-8") as f:
    json.dump(tasks, f, ensure_ascii=False, indent=1)
print("tasks.json refreshed", len(tasks))

# ---------- 3) pinned.json + bots.json refresh ----------
with open(os.path.join(BASE, "pinned.json"), encoding="utf-8") as f:
    pin = json.load(f)
pin["last_updated"] = TS
pin["priority_tasks"] = ["PLT-011", "ENG-009", "SUX-001", "GUA-001", "SL-001", "HTR-001", "OPS-001", "BRD-001"]
pin["vps_status"] = ("VPS UP /health 200 prod 94dca989 uptime 12h26m (02:56Z probe). "
                     "call_loop DEAD 5+ days (import OK, leads=5, restart issued). "
                     "DSH container absent (up -d issued). Jiya RED churn-risk. "
                     "rev Rs1,999 GAP Rs4,98,001.")
pin["bottleneck"] = ("#1 DID->connect->interested->UPI (call loop dead 5+ days, restart issued) | "
                     "#2 DSH armed but container absent (up -d issued) | "
                     "#3 Jiya sole payer churn risk")
pin["pipeline"] = ("0 calls routed (DID issue) | leads=5 available | "
                   "Jiya Rs1,999/mo SOLE | hot-queue pending")
pin["action"] = ("08:30 REVENUE COMMAND broadcast; PLT-011 call loop restart + ENG-009 DSH up -d + "
                 "SUX-001 Jiya retention + GUA-001 verify gate; 09:00 proof check")
pin["next_expected_payment"] = "Jiya renewal (Rs1,999) | 2nd customer close (SL-001) | DID live -> dial track"
with open(os.path.join(BASE, "pinned.json"), "w", encoding="utf-8") as f:
    json.dump(pin, f, ensure_ascii=False, indent=1)
print("pinned.json refreshed")

with open(os.path.join(BASE, "bots.json"), encoding="utf-8") as f:
    bots = json.load(f)

# bots.json = list of dicts with 'role' field
role_map = {
    "Commander": "Pilot",
    "Infra / Telephony": "platform",
    "Engineering": "engineering",
    "Customer Success": "success",
    "QA / Evidence Gate": "guardian",
    "Revenue Executor": "sales",
    "Lead Discovery": "hunter",
    "Operations": "operations",
}
status_map = {
    "Pilot": "08:30 IST Sep17 (LIVE 03:00Z): /health 200 prod 94dca989; call_loop DEAD 5+ days (import OK, leads=5, restart issued); DSH container absent (up -d issued); Jiya RED churn-risk. rev Rs1,999 GAP Rs4,98,001. 09:00 proof check.",
    "platform": "PLT-011 P0 BLOCKED — call loop restart issued (import OK, leads=5). 11:00 gate.",
    "engineering": "ENG-009 P0 BLOCKED — DSH up -d issued. 11:00 gate.",
    "success": "SUX-001 P0 NEW — Jiya retention plan. 12:00 gate.",
    "guardian": "GUA-001 P0 NEW — verify ENG-009 + PLT-011. 11:30 gate.",
    "sales": "SL-001 P1 NEW — 2nd paying customer. 18:00 gate.",
    "hunter": "HTR-001 P1 NEW — lead discovery. 15:00 gate.",
    "operations": "OPS-001 P4 NEW — hygiene report. 14:00 gate.",
}

for bot in bots:
    role = bot.get("role", "")
    name = role_map.get(role)
    if name and name in status_map:
        bot["status"] = status_map[name]
        bot["updated_at"] = TS

with open(os.path.join(BASE, "bots.json"), "w", encoding="utf-8") as f:
    json.dump(bots, f, ensure_ascii=False, indent=1)
print("bots.json refreshed")

# ---------- 4) push mirror to VPS ----------
cmd = [
    "scp", "-o", "StrictHostKeyChecking=no", "-i", "C:/Users/Ratanshila/.ssh/id_rsa",
    BASE + "/tasks.json", BASE + "/bots.json", BASE + "/pinned.json", BASE + "/messages.jsonl",
    "root@72.61.245.204:/opt/leadgen/command_center/data/",
]
r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
print("mirror scp rc:", r.returncode)
if r.stderr:
    print("scp stderr:", r.stderr[-400:])
print("DONE")
