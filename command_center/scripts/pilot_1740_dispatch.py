#!/usr/bin/env python3
"""PILOT 17:40 IST (Sep 2) sweep — evidence-first honest REVENUE COMMAND.
No new TASK-IDs (anti-spam; SAL-004/SUC-003 from 18:05 still live w/ 19:30 gate).
FRESH VPS evidence: WA 'breakthrough' = HTTP201 PENDING, auto_sent true=0, NO UPI/delivered
confirm -> NOT revenue yet. loop DEAD 58h+, WA flip INERT, leads/ ABSENT, SIP empty.
NEW FINDING: session_rotate.sh MISSING (cron log filling) -> engineering flag.
Appends messages.jsonl, updates tasks/bots/pinned, JSON-safe."""
import json, os

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-02T17:40:00+05:30"

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")

# ---------- 1) messages.jsonl ----------
msgs = [
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "🎯 REVENUE COMMAND 17:40 IST (Sep2): TARGET ₹5,00,000 | VERIFIED ₹1,999 (Jiya INV/2026-27/0001 SOLE — invoices 0002-13 sab VOIDED/synthetic) | GAP ₹4,98,001 | PIPELINE: hot-queue 09-02 43/43 UPI+wa_link, 09-01 43 warm; dialer connects 0 (loop DEAD 58h+ batch211 REVOKED CLI proc0), WA-sent auto_sent=true=0 (43/43 manual sends = HTTP201 PENDING, NO delivered receipt, NO UPI confirm) | HOT: Jiya P0 + 43-warm hot-queue followup | BOTTLENECK: WA flip INERT (containers WA=0, disk=1, owner-restart) -> email::WA gate keeps WA=0 -> manual sends not tracked as auto_sent -> ZERO confirmed payment. SECONDARY: DID gate (SIP empty) + egress 000 day5 + ammo (leads/ ABSENT) | ACTION: owner-approve container restart (WA LIVE) + sales ACTIVE followup on 43 PENDING warm sends -> replies -> UPI close; platform DID land | NEXT: pehla WA reply -> close-kit -> UPI confirm -> ledger INV. FLEET: 0 ACK since 00:12Z 54h+. 18:05 dispatch (SAL-004/SUC-003) 19:30 gate LIVE — POLL messages.jsonl, ACK + EXECUTE. Fresh evidence honest: PENDING ≠ PAID, reporting nahi."},
    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "SAL-004", "type": "REINFORCE", "priority": "P0",
     "msg": "SAL-004 (17:40) — FRESH: 43/43 manual sends = HTTP201 PENDING, auto_sent true=0, ZERO delivered-receipt/UPI-confirm in ledger. Ye abhi REVENUE NAHI hai. ACC 19:30: (a) >=5 WARM-lead follow-up sends with WAHA delivered status, (b) any interested-reply captured -> UPI deep-link push + close-kit, (c) vendor DID progress. PENDING ne kuch nahi bheja — EXECUTE conversion. ACK SAL-004 NOW."},
    {"ts": TS, "from": "PILOT", "to": "platform", "task_id": "PLT-004", "type": "REINFORCE", "priority": "P0",
     "msg": "PLT-004 (17:40) — FRESH: containers BOTH SALES_AUTOPILOT_WHATSAPP_ENABLED=0 (WA flip INERT); disk .env=1. owner-approve restart = #1 revenue unlock. SIP 5 vars EMPTY (DID NAHI); egress api.vobiz.com 000 day5. ACC 19:30: restart approval request filed OR DID-vendor proof. Restart tabhi jab owned caller-ID/WA config valid."},
    {"ts": TS, "from": "PILOT", "to": "engineering", "task_id": "ENG-003", "type": "UPDATE", "priority": "P1",
     "msg": "ENG-003 (17:40) NEW FINDING: /opt/leadgen/scripts/session_rotate.sh MISSING — session_rotate.log bhar raha 'not found' (cron ref broken). Fix ya remove. Plus pending: watchdog (log mtime>10min), Jio SIP failover runbook, WA auto_sent audit hook. ACC 19:30: commit sha + watchdog + runbook + session_rotate fix."},
    {"ts": TS, "from": "PILOT", "to": "success", "task_id": "SUC-003", "type": "REINFORCE", "priority": "P0",
     "msg": "SUC-003 (17:40) — Jiya sole payer ₹1,999; churn sab kuch ₹0. 18:05 se 0 SMTP/WA proof. ACC 19:30: Hostinger SMTP recovery email SENT artifact + WA follow-up msg-id + fallback retention offer. DID-independent, ABHI karo."},
    {"ts": TS, "from": "PILOT", "to": "hunter", "task_id": "HNT-004", "type": "REINFORCE", "priority": "P1",
     "msg": "HNT-004 (17:40) — /opt/leadgen/data/leads/ ABSENT (ammo 0). 50-lead mobile+DND CSV due 09:30 missed. DID aate hi dialer raw hai. ACC 19:30: CSV path + 50 verified + DND column. hot-queue already-sent mat dupe."},
    {"ts": TS, "from": "PILOT", "to": "guardian", "task_id": "GRD-003", "type": "REINFORCE", "priority": "P1",
     "msg": "GRD-003 (17:40) — +1 VERDICT: verify PILOT 18:05 43/43 WA sends claim — auto_sent true=0, HTTP201 PENDING only, no delivered/UPI -> PASS/FAIL is the 43 sends real delivered revenue? Plus revenue-truth (snap 5997 vs ledger 1999 sole), loop-dead, WAHA, leads, DID. ACC 19:30 file command_center/data."},
    {"ts": TS, "from": "PILOT", "to": "operations", "task_id": "OPS-006", "type": "REINFORCE", "priority": "P1",
     "msg": "OPS-006 (17:40) — loop DEAD 58h+ re-confirm (mtime Aug31 08:39:55Z, proc0 cron0). WA-rail digest (43 PENDING sends, 0 replies) + restart cadence. ACC 19:30 digest file. Restart tabhi jab owned config."},
    {"ts": TS, "from": "PILOT", "to": "board", "task_id": "BRD-002", "type": "REINFORCE", "priority": "P2",
     "msg": "BRD-002 (17:40) — PILOT push 17:40 (tasks/bots/pinned/messages + honest breakthrough correction). Verify /app/bot-command-center page + VPS mirror. Visualization only. ACC 20:00."},
]
with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("messages appended:", len(msgs))

# ---------- 2) tasks.json evidence_tail (active) ----------
tp = os.path.join(BASE, "tasks.json")
tasks = load(tp)
tails = {
    "PLT-004": "PILOT 17:40 IST (Sep2 CRON): containers WA=0 BOTH INERT (disk .env=1); SIP 5 vars EMPTY; egress 000 day5. #1 unlock = owner-approve restart. ACC 19:30.",
    "SAL-004": "PILOT 17:40 IST (Sep2 CRON): 43/43 manual = HTTP201 PENDING, auto_sent true=0, NO delivered/UPI confirm -> NOT revenue. ACC 19:30 >=5 followup + interested->UPI.",
    "HNT-004": "PILOT 17:40 IST (Sep2 CRON): leads/ ABSENT (ammo 0); 09:30 missed. ACC 19:30 50-lead DND CSV.",
    "OPS-006": "PILOT 17:40 IST (Sep2 CRON): loop DEAD 58h+ re-confirm; WA-rail digest + cadence 19:30.",
    "GRD-003": "PILOT 17:40 IST (Sep2 CRON): +1 verdict — 43/43 claim verify (auto_sent=0, PENDING only). ACC 19:30 PASS/FAIL file.",
    "SUC-003": "PILOT 17:40 IST (Sep2 CRON): Jiya sole payer 1999; SMTP+WA proof 19:30 OWED.",
    "ENG-003": "PILOT 17:40 IST (Sep2 CRON): NEW — session_rotate.sh MISSING (log fill). watchdog+runbook+rotate-fix 19:30.",
    "BRD-002": "PILOT 17:40 IST (Sep2 CRON): push 17:40 done; page verify 20:00.",
}
for t in tasks:
    if t.get("id") in tails:
        t["evidence_tail"] = tails[t["id"]]
save(tp, tasks)
print("tasks.json updated:", len([t for t in tasks if t.get("id") in tails]))

# ---------- 3) bots.json ----------
bp = os.path.join(BASE, "bots.json")
bots = load(bp)
sts = {
    "Pilot": "17:40 IST SWEEP: VERIFIED revenue ₹1,999 (Jiya INV/2026-27/0001 SOLE; 0002-13 voided). WA 43/43 manual = PENDING not revenue (auto_sent=0). loop DEAD 58h+. WA flip INERT. ammo 0. FLEET 0 ACK 54h+. 18:05 dispatch SAL-004/SUC-003 19:30 gate. session_rotate.sh broken.",
    "engineering": "ENG-003 P1: watchdog abs + session_rotate.sh MISSING (new). Jio SIP runbook. 19:30.",
    "platform": "PLT-004 P0: containers WA=0 INERT; SIP empty; egress 000 day5. owner-restart = #1. 19:30.",
    "operations": "OPS-006 P0: loop DEAD 58h+. WA-rail digest 19:30.",
    "sales": "SAL-004 P0: 43/43 PENDING not delivered; ACTIVE followup->UPI. 19:30.",
    "hunter": "HNT-004 P1: leads/ ABSENT. 50-lead DND CSV 19:30.",
    "guardian": "GRD-003 P1: +1 verdict 43/43 claim verify. 19:30.",
    "success": "SUC-003 P0: Jiya retention, SMTP+WA proof 19:30.",
    "board": "BRD-002 P2: mirror pushed 17:40; page verify 20:00.",
}
for k, v in sts.items():
    if k in bots:
        bots[k]["status"] = v
save(bp, bots)
print("bots.json updated")

# ---------- 4) pinned.json ----------
pp = os.path.join(BASE, "pinned.json")
pin = load(pp)
pin["last_updated"] = "2026-09-02T17:40+05:30"
pin["vps_status"] = "HEALTHY 37a1daf8; VERIFIED rev ₹1,999 (Jiya sole); WA 43/43 PENDING not paid (auto_sent=0); loop DEAD 58h+; WA flip INERT; SIP empty; egress 000 day5; session_rotate.sh broken"
save(pp, pin)
print("pinned.json updated")
print("DONE")
