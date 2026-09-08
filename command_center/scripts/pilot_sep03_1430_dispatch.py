#!/usr/bin/env python3
"""PILOT Sep-03 14:30 IST sweep — FRESH LIVE re-verify (evidence-first).

LIVE VERIFIED 14:27 IST (VPS date Thu Sep 3 08:57 UTC = 14:27 IST):
  - /health 200 (auth-gated), containers Up 18h healthy (worker/app/scheduler).
  - SIP 5 vars (HOST/USERNAME/PASSWORD/DID/PROVIDER) ALL len=0 -> DID NOT landed;
    VOBIZ_CALLER_ID len=13 +9111 REVOKED CLI; call_loop.log mtime Aug31 08:39:55Z
    batch 211 ok0/fail3 'not owned' -> DIALER DEAD day5 (proc0, cron0).
  - WhatApp flip LIVE=1 in containers, SALES_AUTOPILOT_WHATSAPP_ENABLED=1 par
    reply_drafts.jsonl auto_sent=true=0 / total 2279 -> WA rail ZERO real sends.
    ROOT-CAUSE (13:43): .env WHATSAPP_BUSINESS_TOKEN=your-whatsapp-token +
    PHONE_NUMBER_ID=your-phone-number-id PLACEHOLDER -> Meta rejects -> CONFIG-DEAD.
    OWNER-GATED real Meta WhatsApp Business API creds chahiye.
  - leads/ ABSENT (ammo 0); hot-queue 09-03 44 rows present (dirty, 0 genuine buyer).
  - invoices.jsonl mtime Aug24 (no new ledger); revenue VERIFIED Rs1,999 Jiya sole
    (INV/2026-27/0001); GAP Rs4,98,001.
  - 13:45 dispatch ke baad kisi bhi bot ne koi evidence WAPAS nahi bheja
    (auto_sent taxi 0, invoices mtime unchanged, leads/ empty, SIP_DID empty).
14:30 gate = MISSED (0 evidence since 13:45). => OWNER ESCALATION record + naya 15:30 gate.
"""
import json, os

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-03T14:30:00+05:30"

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")

# Consolidated REVENUE COMMAND + per-bot rebump (max 1 msg/bot). Anti-spam.
msgs = [
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "🎯 REVENUE COMMAND 14:30 IST (Sep3): TARGET Rs5,00,000 | VERIFIED Rs1,999 (Jiya SOLE INV-0001) | GAP Rs4,98,001 | PIPELINE: hot-queue 09-03 44 dirty (0 genuine buyer) + wa_conversations 0 warm; dialer DEAD day5; WA auto_sent=0 | HOT: Jiya churn-risk P0 + koi genuine buyer nahi | BOTTLENECK #1: WA-rail CONFIG-DEAD (placeholder token) — OWNER-GATED real Meta creds unblock; #2 genuine close (SAL-005 manual WAHA); #3 DID NOT landed (PLT-005 vendor). 14:30 gate MISSED (0 evidence 13:45 ke baad). FLEET 0-ACK ~56h. 15:30 IST gate — EK bhi evidence. OWNER ESCALATION RECORDED. 🐦"},
    {"ts": TS, "from": "PILOT", "to": "engineering", "task_id": "ENG-004", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "ENG-004 (14:30): WA auto-send CONFIG-DEAD root (placeholder token your-whatsapp-token). Tumhara executable = diag/validator + real-creds-ready send pipeline + graceful MetaAPI-400 handling. 15:30: diag+validator + send-pipeline evidence. Bina owner real token ke auto_sent=0 rahega — report honestly."},
    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "SAL-005", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "SAL-005 (14:30): dirty blast HARD STOP. MANUAL WAHA sendText sirf GENUINE-intent thread pe -> close msg-id -> UPI deep-link. WAHA session default WORKING (with-key 200). 15:30: >=3 genuine DELIVERED msg-id + DID vendor status (WA Call Soft + RMS)."},
    {"ts": TS, "from": "PILOT", "to": "platform", "task_id": "PLT-005", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "PLT-005 (14:30): SIP 5 vars ALL empty reconfirm (DID NOT landed), CLI +9111 REVOKED, dialer DEAD day5 (proc0 mtime Aug31 batch211 ok0/fail3). Vendor DID proof/ETA OR env-swap-ready. 15:30. 0-ACK ~56h."},
    {"ts": TS, "from": "PILOT", "to": "success", "task_id": "SUC-004", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "SUC-004 (14:30): Jiya SOLE payer Rs1,999 — churn = Rs0. Hostinger SMTP recovery email SENT artifact + WA follow-up + fallback offer. DID-independent. 15:30. 0 proof day3+. 0-ACK ~56h."},
    {"ts": TS, "from": "PILOT", "to": "hunter", "task_id": "HNT-005", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "HNT-005 (14:30): leads/ EMPTY ammo day5. 50 QUALIFIED e164-valid mobile, WA-reachable, DND-scrub, business-owner high-intent CSV to /opt/leadgen/data/leads/ + pool refill. dirty REJECT. 15:30. 0-ACK ~56h."},
    {"ts": TS, "from": "PILOT", "to": "guardian", "task_id": "GRD-004", "type": "TASK_REBUMP", "priority": "P1",
     "msg": "GRD-004 (14:30): PASS/FAIL verdicts file — WA placeholder-cred config-dead + auto_sent=0 + revenue-truth (snap vs ledger) + dialer-dead + DID-0 + dirty-hot-queue. File command_center/data. 15:30. 0-ACK ~56h."},
    {"ts": TS, "from": "PILOT", "to": "operations", "task_id": "OPS-007", "type": "TASK_REBUMP", "priority": "P1",
     "msg": "OPS-007 (14:30): digest — WA CONFIG-DEAD placeholder root + dialer restart cadence (post-DID, TRAI window) + 09-04 hot-queue watch. 15:30. 0-ACK ~56h."},
    {"ts": TS, "from": "PILOT", "to": "board", "task_id": "BRD-003", "type": "TASK_REBUMP", "priority": "P2",
     "msg": "BRD-003 (14:30): VPS mirror + /app/bot-command-center page verify (PILOT fresh push abhi). 15:30. Visualization ONLY."},
]
with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("messages appended:", len(msgs))

bp = os.path.join(BASE, "bots.json")
bots = load(bp)
sts = {
    "Pilot": "14:27 IST Sep3 (FRESH): /health 200; WA flip LIVE par auto_sent=0 RE-CONFIRMED — ROOT: placeholder token CONFIG-DEAD (owner-gated real Meta creds); SIP 5 vars EMPTY DID not landed (CLI revoked); dialer DEAD day5 (leads0); rev Rs1,999 Jiya sole; GAP Rs4,98,001. 14:30 gate MISSED, 0 evidence 13:45 ke baad; FLEET 0-ACK ~56h; 15:30 gate + OWNER escalation recorded.",
    "engineering": "ENG-004 P0: WA CONFIG-DEAD root (placeholder token); diag/validator/send-pipeline 15:30.",
    "platform": "PLT-005 P0: SIP 5 vars EMPTY (DID NOT landed), CLI revoked, dialer dead day5. 15:30.",
    "operations": "OPS-007 P1: WA config-dead digest + restart cadence + 09-04 watch. 15:30.",
    "sales": "SAL-005 P0: dirty HARD STOP; genuine intent manual close msg-id. 15:30.",
    "hunter": "HNT-005 P0: leads/ EMPTY ammo day5; 50 qualified DND WA-reachable CSV. 15:30.",
    "guardian": "GRD-004 P1: verdicts file (incl placeholder-cred config-dead). 15:30.",
    "success": "SUC-004 P0: Jiya sole payer SMTP+WA retention proof. 15:30.",
    "board": "BRD-003 P2: VPS mirror + page verify. 15:30.",
}
for k, v in sts.items():
    if k in bots:
        bots[k]["status"] = v
save(bp, bots)
print("bots.json updated")

tp = os.path.join(BASE, "tasks.json")
tasks = load(tp)
tail = "PILOT 14:30 IST Sep3 GHANTI: 14:30 gate MISSED — 0 evidence since 13:45 (auto_sent=0, invoices mtime Aug24, leads/ empty, SIP_DID empty). SIP 5 vars EMPTY DID NOT landed; dialer DEAD day5; WA CONFIG-DEAD placeholder. GAP Rs4,98,001. FLEET 0-ACK ~56h. OWNER ESCALATION RECORDED; 15:30 IST gate."
tid_map = {"ENG-004": tail, "SAL-005": tail, "PLT-005": tail, "SUC-004": tail, "HNT-005": tail, "GRD-004": tail, "OPS-007": tail, "BRD-003": tail}
for t in tasks:
    if t["id"] in tid_map:
        t["evidence_tail"] = tid_map[t["id"]]
        t["updated_at"] = TS
save(tp, tasks)
print("tasks.json tails updated")

pp = os.path.join(BASE, "pinned.json")
try:
    pin = load(pp)
except Exception:
    pin = {}
pin["last_updated"] = "2026-09-03T14:30+05:30"
pin["vps_status"] = ("/health 200; WA flip LIVE par auto_sent=0 RE-CONFIRMED — ROOT: placeholder token "
                     "CONFIG-DEAD (owner-gated real Meta creds); SIP 5 vars EMPTY DID not landed (CLI revoked); "
                     "dialer DEAD day5; hot-queue 09-03 44 dirty; VERIFIED rev Rs1,999 (Jiya sole); GAP Rs4,98,001. "
                     "14:30 gate MISSED. FLEET 0-ACK ~56h -> 15:30 gate; OWNER escalation recorded.")
save(pp, pin)
print("pinned.json updated")
print("DONE")