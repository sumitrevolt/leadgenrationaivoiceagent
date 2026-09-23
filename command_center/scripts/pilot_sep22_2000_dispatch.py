#!/usr/bin/env python3
"""PILOT 20:00 IST (Sep22 CRON) — VPS DOWN. Dispatch non-VPS tasks + mark VPS-dependent BLOCKED.

LIVE evidence 20:00 IST:
  - VPS SSH: timeout (connects but commands hang)
  - VPS /health: curl 000 (timeout)
  - PLT-119 evidence: load avg 209, health EMPTY, 0 call loop procs, Docker unresponsive
  - VPS needs manual reboot / host intervention — cannot fix remotely

Non-VPS tasks that CAN execute:
  - PLT-105 (operations): SMS setup — independent of VPS
  - PLT-110 (board): Dashboard sync — local files
  - PLT-111 (engineering): Jio SIP prep — local code prep + config template
  - PLT-109 (hunter): Lead enrichment — local data + Google Maps
  - PLT-117 (guardian): Revenue audit — local ledger files
  - PLT-118 (success): Jiya health — local CRM data if available
  - PLT-113 (sales): Jiya + pipeline follow-up — email/WA independent of VPS

VPS-dependent (mark BLOCKED):
  - PLT-119 (platform): VPS emergency recovery — VPS unreachable
"""
import json, os

TS = "2026-09-22T20:00:00+05:30"
BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"

# ---------- 1) messages.jsonl (message_agent channel) ----------
msgs = [
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND-0922-2000", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "🎯 REVENUE COMMAND 20:00 IST (Sep22): TARGET ₹5,00,000 | VERIFIED ₹5,997 (FY26-27, 3 invoices) | GAP ₹4,94,003 | PIPELINE: ₹31,034 (Gaurav ₹6,425 + Ujjwal ₹24,609) | HOT: PLT-113 Jiya + pipeline follow-up | BOTTLENECK: #1 VPS DOWN (load 209, SSH timeout, health EMPTY) — call loop DEAD, telephony 0 | #2 Tata creds 401 (secondary, VPS down so untestable) | #3 Jiya sole-payer churn-risk | ACTION: VPS-dependent tasks BLOCKED. Non-VPS tasks dispatched: PLT-105 SMS, PLT-110 dashboard, PLT-111 SIP prep, PLT-109 lead enrichment, PLT-117 audit, PLT-118 Jiya health, PLT-113 sales follow-up. | NEXT: VPS recovery = owner/host reboot. 21:00 ACK gate for non-VPS tasks."},

    {"ts": TS, "from": "PILOT", "to": "operations", "task_id": "PLT-105", "type": "ASSIGN", "priority": "P1",
     "msg": "@operations PLT-105 P1 (20:00, VPS-independent): SMS CHANNEL SETUP. VPS down (load 209) — SMS is critical backup comms. ACTION: (1) Check MSG91 or other free SMS gateway config in local files (2) If not configured: set up SMS for lead outreach + Jiya retention (3) Test SMS send to owner number (4) Report: SMS ready + test log. Evidence: SMS gateway config + test send log. Deadline: 21:00 IST. ACCEPTANCE: ACK + test SMS proof."},

    {"ts": TS, "from": "PILOT", "to": "board", "task_id": "PLT-110", "type": "ASSIGN", "priority": "P2",
     "msg": "@board PLT-110 P2 (20:00, VPS-independent): REVENUE DASHBOARD SYNC. Update mirror dashboard with current live state: target ₹5L, verified ₹5,997, gap ₹4,94,003, pipeline ₹31,034, bottleneck = VPS DOWN (load 209, health EMPTY), hot = Jiya retention + pipeline follow-up. Report: dashboard URL. Evidence: updated dashboard. Deadline: 21:00 IST. ACCEPTANCE: ACK + dashboard URL."},

    {"ts": TS, "from": "PILOT", "to": "engineering", "task_id": "PLT-111", "type": "ASSIGN", "priority": "P1",
     "msg": "@engineering PLT-111 P1 (20:00, VPS-independent): JIO SIP INTEGRATION CODE PREP. VPS down — do LOCAL prep. ACTION: (1) Research Jio SIP API/trunk config (Call Soft, wa.me/917599967999) (2) Prepare code changes for SIP provider integration in fire_calls_loop.py (3) Document required env vars: SIP_HOST, SIP_USERNAME, SIP_PASSWORD, DID (4) Report: integration ready status + config template. Evidence: code diff + config template. Deadline: 21:00 IST. ACCEPTANCE: ACK + config template."},

    {"ts": TS, "from": "PILOT", "to": "hunter", "task_id": "PLT-109", "type": "ASSIGN", "priority": "P1",
     "msg": "@hunter PLT-109 P1 (20:00, VPS-independent): LEAD ENRICHMENT. VPS down — work from local data. ACTION: (a) Scrape + enrich 20 new leads (Thane/Mumbai service businesses) using local tools (b) Upload to CRM when VPS recovers (c) Report: enriched count + niche breakdown. Evidence: CRM lead count + sample records. Deadline: 21:00 IST. ACCEPTANCE: ACK + CRM proof or local file proof if VPS still down."},

    {"ts": TS, "from": "PILOT", "to": "guardian", "task_id": "PLT-117", "type": "ASSIGN", "priority": "P1",
     "msg": "@guardian PLT-117 P1 (20:00, VPS-independent): REVENUE AUDIT + RECONCILIATION. VPS down — audit LOCAL ledger files. ACTION: (a) Verify ₹5,997 ledger — cross-check UPI txn IDs in local files (b) Audit if any unrecorded payments exist (c) Verify pipeline deals (Gaurav ₹6,425, Ujjwal ₹24,609) are real (d) Report: verified revenue + pipeline accuracy. Evidence: ledger + UPI proofs. Deadline: 21:00 IST. ACCEPTANCE: ACK + audit report."},

    {"ts": TS, "from": "PILOT", "to": "success", "task_id": "PLT-118", "type": "ASSIGN", "priority": "P1",
     "msg": "@success PLT-118 P1 (20:00, VPS-independent): JIYA ACCOUNT HEALTH CHECK. VPS down — use local CRM data if available. ACTION: (a) Review Jiya account usage + health score from local data (b) Identify churn signals (payment overdue, low engagement) (c) Prepare retention plan (d) Report: health score + retention actions. Evidence: account data + plan. Deadline: 21:00 IST. ACCEPTANCE: ACK + report."},

    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "PLT-113", "type": "ASSIGN", "priority": "P0",
     "msg": "@sales PLT-113 P0 (20:00, VPS-independent): JIYA PIPELINE VALUE UNBLOCK. VPS down — use email/WA from local. ACTION: (a) Check LOCAL CRM for Jiya + Gaurav + Ujjwal email/phone (b) Send retainer upsell email with UPI deeplink to Jiya (c) Send follow-up emails with UPI deeplink to Gaurav + Ujjwal (d) Report: outreach sent + any response. Evidence: email/CRM log. Deadline: 21:00 IST. ACCEPTANCE: ACK + outreach proof."},
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
    if tid == "PLT-119":
        t["status"] = "🔴 BLOCKED — VPS UNREACHABLE (load 209, SSH timeout, health EMPTY). Needs host-level reboot."
        t["updated_at"] = TS
        t["evidence"] = "20:00 IST: VPS SSH timeout, curl /health returns 000. Load avg 209. VPS needs manual reboot or host intervention. Cannot fix remotely."
        t["pilot_note"] = "PLT-119: BLOCKED — VPS unreachable. Owner/host must reboot."
    elif tid == "PLT-105":
        t["status"] = "🆕 NEW"
        t["updated_at"] = TS
    elif tid == "PLT-110":
        t["status"] = "🆕 NEW"
        t["updated_at"] = TS
    elif tid == "PLT-111":
        t["status"] = "🆕 NEW"
        t["updated_at"] = TS
    elif tid == "PLT-109":
        t["status"] = "🆕 NEW"
        t["updated_at"] = TS
    elif tid == "PLT-117":
        t["status"] = "🆕 NEW"
        t["updated_at"] = TS
    elif tid == "PLT-118":
        t["status"] = "🆕 NEW"
        t["updated_at"] = TS
    elif tid == "PLT-113":
        t["status"] = "🆕 NEW"
        t["updated_at"] = TS

with open(os.path.join(BASE, "tasks.json"), "w", encoding="utf-8") as f:
    json.dump(tasks, f, ensure_ascii=False, indent=1)
print("tasks.json refreshed", len(tasks))

# ---------- 3) pinned.json + bots.json refresh ----------
with open(os.path.join(BASE, "pinned.json"), encoding="utf-8") as f:
    pin = json.load(f)
pin["last_updated"] = TS
pin["priority_tasks"] = ["PLT-113", "PLT-119", "PLT-118", "PLT-117", "PLT-105", "PLT-111", "PLT-109", "PLT-110"]
pin["vps_status"] = ("VPS DOWN 20:00 IST — SSH timeout, health EMPTY, load avg 209. "
                     "Call loop DEAD. Telephony 0. Needs host-level reboot. "
                     "Non-VPS tasks dispatched to 7 bots.")
pin["bottleneck"] = ("#1 VPS DOWN (load 209, SSH timeout, health EMPTY) — call loop DEAD, telephony 0 | "
                     "#2 Tata creds 401 (secondary, untestable with VPS down) | "
                     "#3 Jiya sole-payer churn-risk")
pin["pipeline"] = ("VPS down — 0 calls routed. Jiya ₹1,999/mo SOLE payer. "
                   "Pipeline ₹31,034 (Gaurav ₹6,425 + Ujjwal ₹24,609) pending follow-up.")
pin["action"] = ("20:00 REVENUE COMMAND: VPS-dependent tasks BLOCKED. "
                 "Non-VPS tasks dispatched: PLT-105 SMS, PLT-110 dashboard, PLT-111 SIP prep, "
                 "PLT-109 lead enrichment, PLT-117 audit, PLT-118 Jiya health, PLT-113 sales follow-up.")
pin["next_expected_payment"] = "Jiya renewal (₹1,999) | 2nd customer close (PLT-113) | VPS recovery → call loop resume"
with open(os.path.join(BASE, "pinned.json"), "w", encoding="utf-8") as f:
    json.dump(pin, f, ensure_ascii=False, indent=1)
print("pinned.json refreshed")

with open(os.path.join(BASE, "bots.json"), encoding="utf-8") as f:
    bots = json.load(f)

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
    "Pilot": "20:00 IST Sep22: VPS DOWN (load 209, SSH timeout, health EMPTY). Non-VPS tasks dispatched to 7 bots. VPS-dependent BLOCKED. rev ₹5,997 GAP ₹4,94,003.",
    "platform": "PLT-119 P0 BLOCKED — VPS unreachable (load 209, SSH timeout). Needs host reboot.",
    "engineering": "PLT-111 P1 NEW — Jio SIP code prep (local, VPS-independent). 21:00 gate.",
    "success": "PLT-118 P1 NEW — Jiya health check (local data). 21:00 gate.",
    "guardian": "PLT-117 P1 NEW — revenue audit (local ledger). 21:00 gate.",
    "sales": "PLT-113 P0 NEW — Jiya + pipeline follow-up (email/WA). 21:00 gate.",
    "hunter": "PLT-109 P1 NEW — lead enrichment (local tools). 21:00 gate.",
    "operations": "PLT-105 P1 NEW — SMS setup (VPS-independent). 21:00 gate.",
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

print("DONE — VPS DOWN. Non-VPS tasks dispatched. 21:00 ACK gate.")
