#!/usr/bin/env python3
"""PILOT cron ghanti 2026-09-10 09:18 IST — re-issue urgency to 7 NO-ACK bots.

Live VPS evidence (fresh probe at 09:10 IST):
- /health 200 prod (719dbbd6) healthy
- call_loop DEAD — proc0, cron0, last mtime Aug31 batch211 (ok=0 fail=3 'not owned')
- leads/ dir ABSENT (ammo 0, day5+)
- hot_queue/ files exist for 09-05→09-10 (09-10 gen NOT yet — due 03:30 UTC = 09:00 IST)
- SIP_HOST/USERNAME/PASSWORD empty (len=0), SIP_DID = REVOKED CLI +911171366938
- auto_sent=true count = 0 (manual msg-id 44 = 43 Sep9 sends + 1 manual mark)
- WA flip = LIVE in both containers (SALES_AUTOPILOT_WHATSAPP_ENABLED=1)
- reply_drafts.jsonl latest: 43/43 Sep9 sends PENDING, 0 genuine replies, hot-queue = dirty list
- Jiya INV/2026-27/0001 sole verified Rs1,999

All 7 bots dispatched 06:30 with NO ACK (2h48m stale). Ghanti + evidence demand + 2h deadline.
Max 1 task/bot — no spam.
"""
import json, os

TS = "2026-09-10T09:18:00+05:30"
BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"

EV = ("LIVE 09:10 IST Sep10 VPS probe: /health 200 prod (719dbbd6) healthy UP; "
      "call_loop DEAD proc0 cron0 mtime Aug31 batch211 (ok=0 fail=3 'not owned'); "
      "leads/ ABSENT ammo0 day5+; hot_queue 09-10 NOT yet generated (due 03:30 UTC); "
      "SIP_HOST/USERNAME/PASSWORD len=0 (3/5 empty), SIP_DID=911171366938 REVOKED; "
      "auto_sent=true=0 (44 in reply_drafts = 43 Sep9 PENDING + 1 manual-marked); "
      "WA flip LIVE=1 both containers; Jiya INV/0001 sole Rs1,999; GAP Rs4,98,001.")

msgs = [
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND-918", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "🎯 REVENUE COMMAND 09:18 IST (Sep10): TARGET Rs5,00,000 | VERIFIED Rs1,999 (Jiya INV/0001 sole) | GAP Rs4,98,001 | "
            "PIPELINE: 44 Sep9 sends PENDING 0 replies (dirty list) + hot-queue 09-10 NOT gen (due 03:30 UTC, 2.5h overdue) | "
            "BOTTLENECK: #1 no qualified ammo (leads/ ABSENT, hot-queue dirty 0 buyer) | #2 DID0 + CLI REVOKED + egress block | "
            "#3 WA auto_sent=0 (manual 1 only) | #4 Jiya sole-payer churn-risk | "
            "ACTION: ALL 7 bots NO-ACK since 06:30 (2h48m). GHANTI issued below. 11:18 IST deadline = ACK + evidence or BLOCKED+reason. "
            "0 proof 11:18 = REASSIGN each to next executable owner + Owner escalation on record. pelican"},

    {"ts": TS, "from": "PILOT", "to": "hunter", "task_id": "HNT-007", "type": "GHANTI", "priority": "P0",
     "msg": "HNT-007 GHANTI (09:18, FRESH VPS verify): leads/ ABSENT ammo0 day5+. hot_queue 09-10 gen MISSING (03:30 UTC job dead — OPS confirm). "
            "ACTION: (1) mkdir -p /opt/leadgen/data/leads/; (2) scan hot_queue_09-09.csv (44 rows) for QUALIFIED intent — NOT dirty reseller; "
            "(3) produce 50 e164-valid DND-scrubbed business-owner mobile CSV + DND-proof col to /opt/leadgen/data/leads/qualified_2026-09-10.csv. "
            "ACCEPTANCE 11:18: CSV path + 50 verified MOBILE + DND col + pool refill scan. Evidence = file listing + wc -l + DND sample. 0-proof = REASSIGN."},

    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "SAL-007", "type": "GHANTI", "priority": "P0",
     "msg": "SAL-007 GHANTI (09:18, FRESH): 43 Sep9 sends PENDING 0 replies (dirty-list verdict GRD-005 FAIL). Waiting on HNT-007 qualified ammo. "
            "VPS probe: reply_drafts latest = all 'false_' pseudo ids (newsletter noise), auto_sent=true=0 genuine. "
            "ACTION: HOLD blast. Monitor wa_inbound for genuine replies from HNT-007 CSV. Prep 3 trial pitch templates (Rs1999 marketing bundle / voice trial). "
            "ACCEPTANCE 11:18: wa_inbound latest 3 rows reviewed + trial templates staged + HNT-007 CSV wait-status file. 0-proof = REASSIGN to success."},

    {"ts": TS, "from": "PILOT", "to": "platform", "task_id": "PLT-007", "type": "GHANTI", "priority": "P0",
     "msg": "PLT-007 GHANTI (09:18, FRESH VPS): SIP_HOST/USERNAME/PASSWORD ALL len=0 (disk + container confirmed); SIP_DID=+911****6938 REVOKED; egress api.vobiz.com 000@8s DAY6 (google 302 OK = internet fine). "
            "ACTION: (1) RMS Tech Rajnikant 080-47652298 CALL NOW — proof file (date/ETA/DID); (2) Call Soft WA wa.me/917599967999 order-status follow-up; (3) alternate egress probe (TCP proxy to api.vobiz.com) — DID-independent executable. "
            "ACCEPTANCE 11:18: vendor call-proof + DID ETA OR egress re-test result. 0-proof = REASSIGN to sales (sales can cold-call vendors) + Owner-ESC."},

    {"ts": TS, "from": "PILOT", "to": "engineering", "task_id": "ENG-007", "type": "GHANTI", "priority": "P0",
     "msg": "ENG-007 GHANTI (09:18, FRESH VPS): WA flip=1 both containers LIVE; reply_drafts auto_sent=true=0 genuine (44=43 Sep9 PENDING + 1 manual). "
            "WAHA session default WORKING (manual msg-id 3EB00... proven Sep5). Auto-trigger still defer (beat wiring stub confirmed by GRD-006). "
            "ACTION: ship auto_outreach.py body — fetch interested leads, call WAHA sendText session=default X-Api-Key, capture real msg-id. Keep gates fail-closed. "
            "ACCEPTANCE 11:18: commit sha + >=1 GENUINE auto_sent=true row WITH msg-id. 0-proof = GUARDIAN verify + Owner-ESC."},

    {"ts": TS, "from": "PILOT", "to": "success", "task_id": "SUC-006", "type": "GHANTI", "priority": "P0",
     "msg": "SUC-006 GHANTI (09:18, FRESH): Jiya = SOLE payer Rs1,999; renewal 3-6d overdue; SMTP sent Sep9 19:35 (msg_id=jiya_smtp_1788982534) VERIFIED on VPS. "
            "ACTION: (1) re-send SMTP recovery to Jiya with fresh UPI + 30% retention offer; (2) WA follow-up via manual sendText (WAHA proven); (3) monitor reply. "
            "ACCEPTANCE 11:18: SMTP msg-id + WA msg-id + retention offer proof. DID-independent — ABHI karo. 0-proof = REASSIGN."},

    {"ts": TS, "from": "PILOT", "to": "guardian", "task_id": "GRD-006", "type": "GHANTI", "priority": "P1",
     "msg": "GRD-006 GHANTI (09:18, P1, deadline 09:30 = 12m): fresh scopes for PASS/FAIL file: (1) hot-queue 09-10 gen MISSING (date-lock?) — verify file vs cron; (2) leads/ ABSENT; (3) SIP 3/5 empty + CLI revoked; (4) auto_sent=0 genuine; (5) 43 Sep9 sends PENDING 0 replies dirty-list; (6) Jiya sole Rs1,999 revenue-truth. "
     "ACCEPTANCE 09:30: PASS/FAIL verdicts file in command_center/data. 0 file = Owner-ESC."},

    {"ts": TS, "from": "PILOT", "to": "board", "task_id": "BRD-005", "type": "GHANTI", "priority": "P2",
     "msg": "BRD-005 GHANTI (09:18, P2): push current tasks.json + bots.json + messages.jsonl + pinned.json to VPS /opt/leadgen/command_center/data/. Page verify /app/bot-command-center reflects 7 GHANTI + NO_ACK statuses. Visualization only. ACCEPTANCE 11:30: VPS mtime + md5 match proof. 0-proof = REASSIGN."},
]

with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("ghanti messages appended:", len(msgs))

# Refresh tasks.json with ghanti evidence_tail + updated_at
with open(os.path.join(BASE, "tasks.json"), encoding="utf-8") as f:
    tasks = json.load(f)
ghanti_ids = {"HNT-007","SAL-007","PLT-007","ENG-007","SUC-006","GRD-006","BRD-005"}
ts_iso = "2026-09-10T09:18:00+05:30"
for t in tasks:
    if t.get("id") in ghanti_ids:
        t["evidence_tail"] = EV
        t["updated_at"] = ts_iso
        t["ghanti_dispatch"] = ts_iso
with open(os.path.join(BASE, "tasks.json"), "w", encoding="utf-8") as f:
    json.dump(tasks, f, ensure_ascii=False, indent=1)
print("tasks.json refreshed with ghanti evidence_tail")

# Push to VPS
import subprocess
cmd = ["scp","-o","StrictHostKeyChecking=no","-i","C:/Users/Ratanshila/.ssh/id_rsa",
       os.path.join(BASE,"tasks.json"), os.path.join(BASE,"bots.json"),
       os.path.join(BASE,"pinned.json"), os.path.join(BASE,"messages.jsonl"),
       "root@72.61.245.204:/opt/leadgen/command_center/data/"]
r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
print("mirror scp rc:", r.returncode)
if r.stderr:
    print("scp stderr:", r.stderr[-300:])
print("GHANTI DONE")
