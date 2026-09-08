#!/usr/bin/env python3
"""PILOT 10:46 IST (Sep5 CRON) — FRESH LIVE probe evidence + REVENUE COMMAND-GHANTI dispatch + kanban + mirror push.

FRESH evidence (10:40-10:46 IST probe, SSH root@72.61.245.204):
- call_loop.log mtime Aug31 08:39:55Z batch211 fail 'not owned', proc 0 (greps empty) — DEAD day5+.
- hot-queue 09-05 CSV PRESENT 44 rows (incl header) + .md mtime Sep5 03:30 UTC — delivery RESUMED
  (pehle '09-05 ABSENT' claim 03:27Z probe ka pre-gen artifact tha — CORRECTION).
- wa_inbound latest = newsletter broadcast 05:16 UTC ('Trapped Underwater...') — SAL-006 reply STILL PENDING (0 genuine inbound).
- reply_drafts auto_sent true=1 = SAL-006 MANUAL 3EB00CFC (sent_manual) — ENG-004 automation 0.
- SIP 5 vars len=0 DID0, VOBIZ_CALLER_ID len13 REVOKED, egress api.vobiz.com timeout DAY6 (per 03:27Z probes).
- leads/ ABSENT ammo0; rev VERIFIED Rs1,999 Jiya sole; GAP Rs4,98,001.
- /health localhost curl empty (auth-gated); containers healthy Up7h per 03:05Z evidence.
"""
import json, subprocess

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-05T10:46:00+05:30"

LIVE = (
    "LIVE 10:46 IST Sep5 (FRESH SSH probe): VPS up (curl /health empty=auth-gated, containers Up7h per 03:05Z); "
    "call_loop DEAD day5+ (mtime Aug31 08:39:55Z batch211 ok=0/fail=3 NOT-OWNED, proc0 cron0); "
    "SIP 5 vars len=0 DID0 (VOBIZ_CALLER_ID len13=REVOKED); egress api.vobiz.com 000@6s DAY6 (google 302 OK); "
    "leads/ EMPTY ammo0; hot-queue 09-05 PRESENT 44 rows (mtime 03:30 UTC — gen RESUMED, earlier ABSENT claim STALE); "
    "reply_drafts auto_sent true=1 = SAL-006 MANUAL 3EB00CFC (ENG-004 auto=0); wa_inbound latest=newsletter broadcast 05:16 UTC "
    "(NO SAL-006 reply yet); rev VERIFIED Rs1,999 Jiya sole; GAP Rs4,98,001."
)

msgs = [
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND-7", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": ("🎯 REVENUE COMMAND 10:46 IST Sep5: TARGET ₹5,00,000 | VERIFIED ₹1,999 (Jiya INV/0001 sole) | "
             "GAP ₹4,98,001 | PIPELINE: SAL-006 hot inbound (proposal+2 follow-ups SENT, reply PENDING = only genuine buyer shot) "
             "+ SAL-007 86 warm UPI deep-links + hot-queue 09-05 43 (gen RESUMED 03:30 UTC) | "
             "BOTTLENECK: (1) SAL-006 reply→UPI close [SALES] (2) ENG-004 auto sendText=0 [ENG] "
             "(3) HNT-005 qualified CSV 0 → ammo 0 [HNT] (4) PLT-005 DID0+egress DAY6 → dialer dead [PLT] "
             "(5) SUC-004 Jiya sole-payer churn [SUC]. ACTION: gates 11:30 IST; 0-proof 12:00 = REASSIGN + OWNER-ESC per protocol.")},
    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "SAL-006", "type": "GHANTI", "priority": "P0",
     "msg": ("SAL-006 (10:46 FRESH, P0, hot close): wa_inbound 0 genuine reply — latest row 05:16 UTC = newsletter broadcast (noise). "
             "Proposal + follow-up SENT; ab FINAL owner-route nudge window: 1 last WAHA sendText (Product-2 pricing + UPI deep-link + "
             "trial-call offer) mat spam — max total msgs to this lead = 3. ACCEPTANCE 11:30 IST: reply/call-intent ya UPI ya "
             "clear NOT-INTERESTED proof. 0 reply 11:30 = STOP nudges, owner-route summary file + SAL-007 warm set par shift. "
             "SAL-007 (12:00 gate) parallel — 10 nudges + 3 trial pitches, msg-ids capture.")},
    {"ts": TS, "from": "PILOT", "to": "engineering", "task_id": "ENG-004", "type": "GHANTI", "priority": "P0",
     "msg": ("ENG-004 (10:46 FRESH, P0): deadline Sep4 16:00 MISSED day2, 0 ACK. auto_sent true=1 = SAL-006 MANUAL (3EB00CFC) — "
             "auto_outreach real sendText STILL 0. WAHA infra PROVEN via manual (session:default + X-Api-Key + msg-id). "
             "ACCEPTANCE 11:30 IST: commit sha + >=1 GENUINE auto_sent=true row WITH msg-id. Scale unlock = #2 bottleneck. "
             "0-proof 12:00 = GUARDIAN verify + reassign.")},
    {"ts": TS, "from": "PILOT", "to": "hunter", "task_id": "HNT-005", "type": "GHANTI", "priority": "P0",
     "msg": ("HNT-005 (10:46 FRESH, P0): leads/ EMPTY ammo0 (day6). Dialer DID aane pe bhi kuch dial nahi hoga — ammo critical. "
             "ACCEPTANCE 11:30 IST: 50 QUALIFIED mobile-only DND-scrubbed business-owner CSV (Maps Places + SearXNG) → "
             "/opt/leadgen/data/leads/ + DND-proof col + e164-valid. NOT dirty reseller (GRD: hot-queue 43-send = 0 buyer). "
             "0-proof 12:00 = reassign + OWNER-ESC.")},
    {"ts": TS, "from": "PILOT", "to": "platform", "task_id": "PLT-005", "type": "GHANTI", "priority": "P0",
     "msg": ("PLT-005 (10:46 FRESH, P0): BLOCKED day6 — SIP 5 len0 DID0, CLI REVOKED, egress Vobiz timeout DAY6, dialer dead. "
             "Vendor silent (Jio Call Soft + RMS). ACCEPTANCE 11:30 IST: RMS Tech backup CALL proof (Rajnikant 080-47652298) ya "
             "vendor DID/ETA + alternate-egress probe result + restart plan. DID live hote hi env-swap + restart (WA flip already LIVE=1) "
             "+ first post-DID dial proof. 0-proof 12:00 = REASSIGN to sales + OWNER-ESC.")},
    {"ts": TS, "from": "PILOT", "to": "success", "task_id": "SUC-004", "type": "GHANTI", "priority": "P0",
     "msg": ("SUC-004 (10:46 FRESH, P0): Jiya = SOLE payer ₹1,999; churn = revenue ZERO. SMTP sent artifact missing day5+. "
             "DID-independent — ABHI karo. ACCEPTANCE 11:30 IST: Hostinger SMTP msg-id artifact + WA follow-up + fallback retention "
             "offer + reply captured. 0-proof 12:00 = reassign + OWNER-ESC.")},
    {"ts": TS, "from": "PILOT", "to": "guardian", "task_id": "GRD-004", "type": "GHANTI", "priority": "P1",
     "msg": ("GRD-004 (10:46 FRESH, P1): verdicts file ABSENT day5+. FRESH scopes 6: (a) ENG-004 auto sendText unshipped (1=manual 3EB00CFC); "
             "(b) SAL-006 reply pending (wa_inbound latest = newsletter noise 05:16 UTC); (c) SIP blank DID0 + egress Vobiz timeout DAY6; "
             "(d) dialer dead (mtime Aug31 batch211 proc0); (e) leads EMPTY ammo0; (f) revenue-truth Jiya sole ₹1,999 vs snapshots 5997 STALE. "
             "+1 (g): hot-queue 09-05 delivery RESUMED (44 rows 03:30 UTC — earlier ABSENT claim CORRECTED). "
             "ACCEPTANCE 11:30 IST: PASS/FAIL verdicts file in command_center/data. 0 file 12:00 = reassign.")},
    {"ts": TS, "from": "PILOT", "to": "operations", "task_id": "OPS-007", "type": "GHANTI", "priority": "P1",
     "msg": ("OPS-007 (10:46 FRESH, P1): CORRECTION — hot-queue 09-05 PRESENT 44 rows (mtime 03:30 UTC) = gen RESUMED; "
             "09-05-ABSENT claim (03:27Z probe) STALE, kanban update karo. Digest STILL OVERDUE. ACCEPTANCE 11:30 IST: digest file — "
             "(1) WA auto_send defer root-cause (flip=1 par auto=0), (2) queue delivery 09-04/09-05 confirmed + date-lock status, "
             "(3) dialer dead day6 status + restart cadence (sirf DID swap ke baad). 0-proof 12:00 = reassign.")},
    {"ts": TS, "from": "PILOT", "to": "board", "task_id": "BRD-003", "type": "GHANTI", "priority": "P2",
     "msg": ("BRD-003 (10:46 FRESH, P2): PILOT mirror push 10:46 (tasks/bots/pinned/messages — hot-queue 09-05 PRESENT correction included). "
             "/app/bot-command-center page verify — SAL-006 PENDING + bottleneck chain dikhna chahiye. ACCEPTANCE 11:30 IST: page/mtime proof. "
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
    if t.get("id") in ("SAL-006", "SAL-007", "ENG-004", "PLT-005", "HNT-005", "SUC-004", "GRD-004", "OPS-007", "BRD-003"):
        t["evidence_tail"] = LIVE
        t["updated_at"] = TS

json.dump(tasks, open(f"{BASE}/tasks.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

bots = {
    "Pilot": {"avatar": "🟣", "role": "Commander",
              "status": "10:46 IST Sep5: SAL-006 reply PENDING (newsletter noise only); ENG-004 auto=0; hot-queue 09-05 gen RESUMED 44 rows; DID0 dialer dead day6; leads 0; rev ₹1,999 GAP ₹4,98,001. Gates 11:30 0-proof = REASSIGN+ESC."},
    "engineering": {"avatar": "🤖", "role": "Engineer", "status": "ENG-004 P0: auto sendText STILL 0 (1=manual). sha + genuine auto_sent row. Gate 11:30."},
    "platform": {"avatar": "🤖", "role": "Infra", "status": "PLT-005 P0 BLOCKED day6: SIP 5 len0 DID0, egress DAY6. RMS call proof + DID ETA. Gate 11:30."},
    "operations": {"avatar": "🤖", "role": "Ops Executor", "status": "OPS-007 P1: hot-queue 09-05 PRESENT (gen resumed — CORRECTED); digest OVERDUE. Gate 11:30."},
    "sales": {"avatar": "💰", "role": "Revenue Executor", "status": "SAL-006 P0: final nudge + owner-route; SAL-007 86-warm parallel. Gate 11:30 / 12:00."},
    "hunter": {"avatar": "🎯", "role": "Lead Discovery", "status": "HNT-005 P0: leads/ EMPTY ammo0; 50 QUALIFIED DND mobile CSV. Gate 11:30."},
    "guardian": {"avatar": "🛡", "role": "QA Gate", "status": "GRD-004 P1: 7 scopes PASS/FAIL file (09-05 gen RESUMED scope added). Gate 11:30."},
    "success": {"avatar": "🏆", "role": "Customer Success", "status": "SUC-004 P0: Jiya SMTP msg-id artifact + WA follow-up. Gate 11:30."},
    "board": {"avatar": "📊", "role": "Visualization Only", "status": "BRD-003 P2: mirror push 10:46; page verify 11:30."},
}
json.dump(bots, open(f"{BASE}/bots.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

pinned = {
    "last_updated": TS,
    "priority_tasks": ["SAL-006", "ENG-004", "PLT-005", "HNT-005", "SUC-004", "GRD-004", "OPS-007", "BRD-003"],
    "vps_status": "VPS UP containers healthy (Up7h per 03:05Z). WA flip=1 par auto-send=0 (manual proof done). call_loop DEAD day6 (DID0 egress DAY6). leads/ 0. hot-queue 09-05 PRESENT 44 rows (gen RESUMED 03:30 UTC).",
    "verified_revenue": "₹1,999 (Jiya INV/2026-27/0001)",
    "target": "₹5,00,000",
    "gap": "₹4,98,001",
    "bottleneck": "1) SAL-006 reply→UPI close 2) ENG-004 auto sendText 0 3) HNT-005 qualified CSV 0 4) PLT-005 DID0+egress 5) SUC-004 Jiya churn",
    "revenue_days_left": "goal 08-30 PASSED — drive continues",
    "pipeline": "SAL-006 3 msgs SENT reply PENDING + 86 warm UPI deep-links + hot-queue 09-05 43 (delivery resumed)",
    "hot": "SAL-006 final nudge + ENG-004 unlock + HNT-005 ammo + Jiya retention",
    "action": "SAL-006/ENG/PLT/HNT/SUC/GRD/OPS gates 11:30 · BRD 11:30 · 0 proof 12:00 = REASSIGN+OWNER",
    "next_expected_payment": "SAL-006 UPI close (reply pending) / Jiya renewal; DID aane par dial track",
    "goal_status": "PASSED (08-30) — collection drive continues; proposal + follow-ups sent; reply pending",
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
print("OK 10:46 dispatch done")