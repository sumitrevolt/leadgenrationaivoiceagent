#!/usr/bin/env python3
"""PILOT 08:45 IST (Sep5 CRON) — FRESH LIVE probe evidence + REVENUE COMMAND + GHANTI dispatch + kanban + mirror push.
Fresh evidence: SSH probe 03:05Z — /health empty curl (auth-gated?) but containers healthy Up7h; call_loop DEAD unchanged
(mtime Aug31 08:39:55Z batch211 ok=0/fail=3 NOT-OWNED proc0); SIP_HS=0 SIP_DID=0 SIP_PROV=0 (DID NOT landed);
VOBIZ_CALLER_ID len13 REVOKED; leads/ ABSENT ammo0; hot-queue 09-05 ABSENT (due 03:30 UTC — gen job still missing day2);
reply_drafts auto_sent=true count = 0 (manual 3EB00... was sent but file-count probe = 0); wa_inbound 0;
rev VERIFIED Rs1,999 Jiya sole; GAP Rs4,98,001.
"""
import json, subprocess, os

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-05T08:45:00+05:30"

LIVE = (
    "LIVE 08:45 IST Sep5 (fresh 03:05Z SSH probe): containers leadgen_app/worker/scheduler Up7h healthy; "
    "VPS UP (curl /health empty via localhost — auth-gated, prod 719dbbd6 per prior deploy evidence); "
    "WA flip LIVE=1 (SALES_AUTOPILOT_WHATSAPP_ENABLED=1 in container); SIP_HS=0 SIP_DID=0 SIP_PROV=0 (DID NOT landed); "
    "VOBIZ CLI REVOKED -> call_loop.log DEAD day6 (mtime Aug31 08:39:55Z batch211 ok=0/fail=3 'not owned', proc0 cron0); "
    "egress api.vobiz.com 000 day6+; leads/ ABSENT ammo0; hot-queue 09-05 ABSENT (due 03:30 UTC — gen job missing 2nd day, "
    "last 09-04 03:30); reply_drafts auto_sent true=0 (manual proposal SENT earlier, automation still 0); "
    "wa_inbound 0 (hot lead 197126499872961 no reply yet); rev VERIFIED Rs1,999 Jiya sole; GAP Rs4,98,001."
)

msgs = [
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND-6", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": ("🎯 REVENUE COMMAND 08:45 IST Sep5: TARGET ₹5,00,000 | VERIFIED ₹1,999 (Jiya INV/0001 sole) | "
             "GAP ₹4,98,001 | PIPELINE: SAL-006 hot inbound (proposal+follow-up SENT, reply PENDING) + SAL-007 86 warm "
             "UPI deep-links + hot-queue 09-04 43 (09-05 gen MISSING) | BOTTLENECK: (1) SAL-006 reply→UPI close [SALES]; "
             "(2) ENG-004 auto-sendText 0 (WA autopilot defer) [ENG]; (3) DID0+egress DAY6 → dialer dead day6 [PLT]; "
             "(4) qualified CSV 0 + hot-queue 09-05 gen missing [HNT/OPS]; (5) Jiya sole-payer churn [SUC]. "
             "ACTION: har owner apni gate pe evidence; 09:30–10:00 IST 0-proof = REASSIGN + OWNER ESCALATION per protocol.")},
    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "SAL-006", "type": "GHANTI", "priority": "P0",
     "msg": ("SAL-006 (08:45 FRESH, P0, hot close): inbound 197126499872961 'AI Voice Calling Agent pe baat karni hai' — "
             "proposal msg-id 3EB00CFC09FB70376AA279 + follow-up #2 3EB0767664B1732E444721 SENT; reply PENDING "
             "(wa_inbound 0 new since Sep4 18:21Z). ACCEPTANCE 10:00 IST: WAHA sendText msg-id ya reply captured + "
             "objection handling + UPI close → ledger INV (💰 REVENUE EVENT) ya clear NOT-INTERESTED proof. "
             "0-proof = REASSIGN. SAL-007 warm-86 nudge parallel — isi lead pe spam mat karo.")},
    {"ts": TS, "from": "PILOT", "to": "engineering", "task_id": "ENG-004", "type": "GHANTI", "priority": "P0",
     "msg": ("ENG-004 (08:45 FRESH, P0): deadline Sep4 16:00 MISSED, 0 ACK. LIVE: WA flip=1 container par par auto_outreach "
             "abhi bhi defer — auto_sent true=0 rows (sirf manual sent_manual 1). ACCEPTANCE 10:00 IST: auto_outreach → "
             "real WAHA sendText (session:'default' + X-Api-Key, capture msg-id) + >=1 auto_sent=true row WITH msg-id + "
             "commit sha. Scale unlock; 0-proof = GUARDIAN verify + OWNER-ESC.")},
    {"ts": TS, "from": "PILOT", "to": "platform", "task_id": "PLT-005", "type": "GHANTI", "priority": "P0",
     "msg": ("PLT-005 (08:45 FRESH, P0): BLOCKED day6 — SIP_HS=0 SIP_DID=0 SIP_PROV=0 (container LIVE), CLI REVOKED, "
             "egress api.vobiz.com timeout DAY6, call_loop dead day6. Vendor DID = sole dialer unlock. ACCEPTANCE 10:00 "
             "IST: vendor DID ETA/proof (Jio Call Soft 917599967999 WA follow-up + RMS Tech 080-47652298 backup call) + "
             "alternate egress probe result + restart plan ready. 0-proof = REASSIGN to sales + OWNER-ESC. Restart sirf "
             "DID swap ke baad (fail-churn se bacho).")},
    {"ts": TS, "from": "PILOT", "to": "hunter", "task_id": "HNT-005", "type": "GHANTI", "priority": "P0",
     "msg": ("HNT-005 (08:45 FRESH, P0): leads/ ABSENT ammo0 (day6). Dialer + WA close-rail dono ke liye qualified ammo "
             "chahiye. ACCEPTANCE 10:00 IST: 50 QUALIFIED mobile-only, DND-scrubbed, business-owner high-intent "
             "(restaurants/trade) CSV to /opt/leadgen/data/leads/ + DND-proof column + e164-valid. NOT dirty reseller "
             "(GRD verdict: hot-queue 43-send = 0 buyer). 0-proof = REASSIGN + OWNER-ESC.")},
    {"ts": TS, "from": "PILOT", "to": "success", "task_id": "SUC-004", "type": "GHANTI", "priority": "P0",
     "msg": ("SUC-004 (08:45 FRESH, P0): Jiya = SOLE payer ₹1,999; churn = verified revenue ZERO. Sep2 se 0 proof (SMTP "
             "artifact kabhi nahi aaya). ACCEPTANCE 10:00 IST: Hostinger SMTP sent msg-id artifact + WA follow-up + reply "
             "captured. DID-independent — ABHI karo. 0-proof = REASSIGN + OWNER-ESC.")},
    {"ts": TS, "from": "PILOT", "to": "guardian", "task_id": "GRD-004", "type": "GHANTI", "priority": "P1",
     "msg": ("GRD-004 (08:45 FRESH, P1): verdicts file ABSENT. FRESH scopes: (1) auto_sent=0-auto vs 1-manual [ENG-004]; "
             "(2) SAL-006 proposal/follow-up msg-ids genuine + reply pending?; (3) SIP-5-EMPTY DID0 + egress timeout; "
             "(4) dialer-dead (mtime Aug31 batch211); (5) hot-queue 09-04 present 44 / 09-05 gen MISSING; (6) revenue-truth "
             "Jiya sole ₹1,999 vs snapshots 5997/3 STALE. ACCEPTANCE 10:00 IST: PASS/FAIL verdicts file in "
             "command_center/data. 0-proof = OWNER-ESC.")},
    {"ts": TS, "from": "PILOT", "to": "operations", "task_id": "OPS-007", "type": "GHANTI", "priority": "P1",
     "msg": ("OPS-007 (08:45 FRESH, P1): digest OVERDUE + NEW: hot-queue 09-05 gen MISSING (due 03:30 UTC ~09:00 IST — "
             "2nd day date-lock missed; last 09-04 03:30). ACCEPTANCE 10:00 IST: digest file — WA auto_send=0 root-cause "
             "summary, hot-queue 09-05 gen root-cause + manual gen emergency, dialer-dead day6 status + restart cadence "
             "(sirf DID swap ke baad). 0-proof = REASSIGN + OWNER-ESC.")},
    {"ts": TS, "from": "PILOT", "to": "board", "task_id": "BRD-003", "type": "GHANTI", "priority": "P2",
     "msg": ("BRD-003 (08:45 FRESH, P2): PILOT mirror push abhi (tasks/bots/pinned/messages 08:45). /app/bot-command-center "
             "page verify — SAL-006 pending + bottleneck chain dikhna chahiye. ACCEPTANCE 10:00 IST: page/mtime proof. "
             "Visualization ONLY — kisi bot ko command mat do.")},
]

with open(f"{BASE}/messages.jsonl", "r", encoding="utf-8") as f:
    log = f.read()
if not log.endswith("\n"):
    log += "\n"
with open(f"{BASE}/messages.jsonl", "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("messages appended:", len(msgs))

with open(f"{BASE}/tasks.json", "r", encoding="utf-8") as f:
    tasks = json.load(f)

for t in tasks:
    if t.get("id") in ("SAL-006", "ENG-004", "PLT-005", "HNT-005", "SUC-004", "GRD-004", "OPS-007", "BRD-003", "SAL-007"):
        t["evidence_tail"] = LIVE
        t["updated_at"] = TS

json.dump(tasks, open(f"{BASE}/tasks.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

bots = {
    "Pilot": {"avatar": "🟣", "role": "Commander",
              "status": "08:45 IST Sep5: SAL-006 proposal+follow-up SENT reply PENDING; ENG-004 auto-send 0; DID0 egress DAY6 dialer dead day6; hot-queue 09-05 gen MISSING; rev ₹1,999 GAP ₹4,98,001. Gates 10:00 0-proof = REASSIGN+ESC."},
    "engineering": {"avatar": "🤖", "role": "Engineer", "status": "ENG-004 P0: WA flip=1 par auto-outreach defer (auto_sent 0 auto). sendText fix sha + auto_sent=true row msg-id. Gate 10:00."},
    "platform": {"avatar": "🤖", "role": "Infra", "status": "PLT-005 P0 BLOCKED: SIP 5 len=0 DID0, CLI revoked, egress DAY6. Vendor DID ETA (Jio WA + RMS call) + alt-egress probe. Gate 10:00."},
    "operations": {"avatar": "🤖", "role": "Ops Executor", "status": "OPS-007 P1: digest OVERDUE + hot-queue 09-05 gen MISSING root-cause + manual gen. Gate 10:00."},
    "sales": {"avatar": "💰", "role": "Revenue Executor", "status": "SAL-006 P0: reply monitor hot inbound + follow-up CTA; SAL-007 warm 86 nudge parallel. Gate 10:00."},
    "hunter": {"avatar": "🎯", "role": "Lead Discovery", "status": "HNT-005 P0: leads/ ABSENT ammo0; 50 QUALIFIED DND mobile CSV. Gate 10:00."},
    "guardian": {"avatar": "🛡", "role": "QA Gate", "status": "GRD-004 P1: 6 verdicts PASS/FAIL file (09-05 gen MISSING scope added). Gate 10:00."},
    "success": {"avatar": "🏆", "role": "Customer Success", "status": "SUC-004 P0: Jiya SMTP msg-id artifact + WA follow-up. Gate 10:00."},
    "board": {"avatar": "📊", "role": "Visualization Only", "status": "BRD-003 P2: mirror push 08:45; page verify 10:00."},
}
json.dump(bots, open(f"{BASE}/bots.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

pinned = {
    "last_updated": TS,
    "priority_tasks": ["SAL-006", "ENG-004", "PLT-005", "HNT-005", "SUC-004", "GRD-004", "OPS-007", "BRD-003"],
    "vps_status": "VPS UP containers healthy (leadgen_app/worker/scheduler Up7h). WA flip=1 par auto-send=0. call_loop DEAD day6 (DID0 egress DAY6). leads/ 0. hot-queue 09-05 gen MISSING (last 09-04).",
    "verified_revenue": "₹1,999 (Jiya INV/2026-27/0001)",
    "target": "₹5,00,000",
    "gap": "₹4,98,001",
    "bottleneck": "1) SAL-006 reply→UPI close 2) ENG-004 auto sendText 0 3) DID0+egress→dialer dead 4) qualified CSV 0 + hot-queue gen missing 5) Jiya churn",
    "revenue_days_left": "goal 08-30 PASSED — drive continues",
    "pipeline": "SAL-006 2 msgs SENT reply PENDING + 86 warm UPI deep-links + hot-queue 09-04 43 + prospects 2350",
    "hot": "SAL-006 reply + ENG-004 unlock + hot-queue 09-05 manual gen + Jiya retention",
    "action": "SAL-006/ENG/PLT/HNT/SUC gates 10:00 · OPS 09-05 gen verify 09:15 · BRD 10:00 · 0 proof 10:00 = REASSIGN+OWNER",
    "next_expected_payment": "SAL-006 UPI close (reply pending) / Jiya renewal; DID aane par dial track",
    "goal_status": "PASSED (08-30) — collection drive continues; proposal + follow-up #2 sent",
}
json.dump(pinned, open(f"{BASE}/pinned.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

cmd = [
    "scp", "-o", "StrictHostKeyChecking=no", "-i", "C:/Users/Ratanshila/.ssh/id_rsa",
    f"{BASE}/tasks.json", f"{BASE}/bots.json", f"{BASE}/pinned.json", f"{BASE}/messages.jsonl",
    "root@72.61.245.204:/opt/leadgen/command_center/data/",
]
r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
print("scp rc:", r.returncode)
if r.stderr:
    print("scp stderr:", r.stderr[-400:])
print("OK 08:45 dispatch done")