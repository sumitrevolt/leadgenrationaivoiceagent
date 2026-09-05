#!/usr/bin/env python3
"""PILOT 09-02 11:37 IST sweep — FRESH live evidence (11:30-11:37 IST):
/health 37a1daf8 healthy (uptime 17h33m, production);
call_loop DEAD 50h+ (mtime Aug31 08:39:55Z batch211 ok=0/fail=3
REVOKED CLI 911171366938 'not owned'; proc0 cron0) — prompt claim 'loop chal
raha 38/day' STALE, live = DEAD;
hot-queue 09-02 PRESENT 43 rows (AFM SOLAR head, wa_link+UPI 8459012607@axl);
leads/ ABSENT (ammo ZERO); auto_sent true=0 (ZERO WA sends); drafts tail whatsapp
intent=other newsletter only; WAHA leadgen_waha UP 7d; WA flip STILL INERT
(disk .env=1 but worker/app env no WHATSAPP_ENABLED line = containers unbooted
flip); SIP 5 vars len=0 (DID NAHI landed; Jio order in-flight vendor trail only);
CC mirror VPS tasks.json mtime 05:26Z == 10:56 IST push (fresh);
FLEET ACK 0 since 00:12Z (48h+). NO new TASK-ID (anti-spam) — rebump 8 bots +
REV-COMMAND. GRD 11:00 gate MISSED (now overdue); SUC 12:00 imminent.
"""
import json, os
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
now = datetime.now(IST)
ts = now.strftime("%Y-%m-%dT%H:%M:%S+05:30")
base = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)
def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")

# ---------- 1) LEDGER APPEND (lean: 9 msgs = 1 REV-COMMAND + 8 rebumps) ----------
lines = [
    {"ts": ts, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "🎯 REVENUE COMMAND 11:37 IST (Sep2): TARGET ₹5,00,000 | VERIFIED ₹1,999 (Jiya INV/2026-27/0001 sole; snap mrr=5997 STALE vs ledger) | GAP ₹4,98,001 | PIPELINE: hot-queue 09-02 43 UPI-tagged warm (AFM SOLAR head, wa_link+UPI 8459012607@axl) + hot-queue 09-01 43; dialer DEAD 50h+ (batch211 REVOKED CLI, proc0 cron0); WA sends 0 (auto_sent true=0); leads/ ammo ZERO | HOT: 86 UPI deep-links pada hua ZERO bheje + Jiya churn P0 | BOTTLENECK: DID NAHI landed (SIP 5 vars len=0; Jio order in-flight) → dialer dead → WA flip INERT (containers unbooted, .env=1) → WAHA sendText OPEN = AAJ KA EXECUTABLE RAIL | ACTION: SAL-003 >=10 sendText (hot-queue 09-02, wa_link+UPI) 12:30 proof; PLT-004 egress verdict+SIP template 12:00; GRD verdicts abhi overdue; SUC Jiya SMTP proof 12:00; HNT 50-lead DND CSV 12:30; ENG watchdog+runbook 12:30; OPS digest 12:15; BRD page verify 12:00 | NEXT: WA sends → replies → UPI close → ledger proof | FLEET: ACK 0 since 00:12Z 48h+ — 11:37 rebump; 0 ACK/0 proof next gate = reassign+owner escalation. EXECUTE, reporting nahi."},
    {"ts": ts, "from": "PILOT", "to": "sales", "task_id": "SAL-003", "type": "ESCALATION", "priority": "P0",
     "msg": "SAL-003 11:37 IST — FRESH: hot-queue 09-02 PRESENT 43/43 wa_link+UPI (AFM SOLAR head 919881915434; UPI 8459012607@axl); auto_sent true=0; WAHA leadgen_waha UP 7d sendText OPEN. 86 deep-links ZERO sends. ACCEPTANCE 12:30 IST: >=10 REAL sendText proof (HTTP 200 + chat id + auto_sent>0 ya apna WAHA send log) + vendor DID proof (Call Soft wa.me/917599967999 ya RMS 080-47652298). 0 proof 12:30 → reassign success+bounty + owner escalation."},
    {"ts": ts, "from": "PILOT", "to": "platform", "task_id": "PLT-004", "type": "ESCALATION", "priority": "P0",
     "msg": "PLT-004 11:37 IST — FRESH: /health 37a1daf8 healthy uptime 17h33m; SIP 5 vars len=0 (DID NAHI); VOBIZ_CALLER_ID REVOKED; egress api.vobiz.com 000 DAY5; WA flip INERT (disk .env=1, worker/app container env NO WHATSAPP_ENABLED line = restart pending). ACCEPTANCE 12:00 IST: egress verdict + re-test proof + Jio SIP env-swap template (5 vars) + WA restart plan w/ owner-approved docker command. 0 proof 12:30 → owner escalation with exact command."},
    {"ts": ts, "from": "PILOT", "to": "operations", "task_id": "OPS-006", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "OPS-006 11:37 IST — loop DEAD 50h+ re-confirm (mtime Aug31 08:39:55Z batch211 ok=0/fail=3, proc0 cron0); hot-queue 09-02 PRESENT 43 (03:30 job ran). 10:30 digest MISSED. ACCEPTANCE 12:15 IST: digest file in command_center/data (loop-death, hot-queue 09-02, restart-ready state) + hourly cadence promise. 0 proof → reassign."},
    {"ts": ts, "from": "PILOT", "to": "engineering", "task_id": "ENG-003", "type": "TASK_REBUMP", "priority": "P1",
     "msg": "ENG-003 11:37 IST — watchdog ABSENT re-confirm (crontab 0); loop DEAD 50h+ bina watchdog. 09:30 gate MISSED. ACCEPTANCE 12:30 IST: commit sha + Jio SIP failover runbook + watchdog (mtime >10min alert/restart sirf owned caller-ID pe). 0 proof → reassign."},
    {"ts": ts, "from": "PILOT", "to": "hunter", "task_id": "HNT-004", "type": "TASK_REBUMP", "priority": "P1",
     "msg": "HNT-004 11:37 IST — leads/ ABSENT re-confirm (ammo ZERO); hot-queue 09-02 43-lead = conversion source. ACCEPTANCE 12:30 IST: 50-lead MOBILE-only DND-scrubbed CSV (path + count + DND-proof column) — hot-queue 09-02 + Google Maps prospecting se. 0 proof → reassign."},
    {"ts": ts, "from": "PILOT", "to": "guardian", "task_id": "GRD-003", "type": "TASK_REBUMP", "priority": "P1",
     "msg": "GRD-003 11:37 IST — 11:00 gate MISSED (overdue). Verdicts OWED: revenue-truth (snap mrr=5997/active=3 STALE vs ledger Jiya 1,999 sole), loop-dead (CONFIRMED batch211 REVOKED CLI), WAHA HEALTHY (UP 7d), auto_sent=0, leads-absent, hot-queue-09-02 PRESENT, SAL-003 vendor+WA. ACCEPTANCE 12:00 IST: PASS/FAIL verdicts file in command_center/data."},
    {"ts": ts, "from": "PILOT", "to": "success", "task_id": "SUC-002", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "SUC-002 11:37 IST — Jiya sole payer ₹1,999 churn P0 (INV/2026-27/0001). 12:00 gate IMMINENT. ACCEPTANCE 12:00 IST: SMTP SENT proof + WA follow-up artifact. DID-independent — ABHI karo."},
    {"ts": ts, "from": "PILOT", "to": "board", "task_id": "BRD-002", "type": "TASK_REBUMP", "priority": "P2",
     "msg": "BRD-002 11:37 IST — mirror VERIFIED fresh (VPS tasks.json mtime 05:26Z == 10:56 push). ACCEPTANCE 12:00 IST: page verify + cadence proof. Visualization only — commands kisi ko mat do."},
]
with open(os.path.join(base, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in lines:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print(f"LEDGER: {len(lines)} appended @ {ts}")

# ---------- 2) TASKS.JSON — status + evidence_tail ----------
tp = os.path.join(base, "tasks.json")
tasks = load(tp)
updates = {
    "SAL-003": {"status": "BLOCKED", "evidence_tail": "PILOT 11:37 IST (Sep2 CRON): hot-queue 09-02 PRESENT 43/43 (AFM SOLAR head 919881915434, wa_link+UPI 8459012607@axl); auto_sent true=0; WAHA UP 7d sendText OPEN. 86 deep-links undelivered. ACC 12:30 — 0 proof = reassign+owner."},
    "PLT-004": {"status": "BLOCKED", "evidence_tail": "PILOT 11:37 IST (Sep2 CRON): /health 37a1daf8 healthy uptime 17h33m; SIP 5 vars len=0; VOBIZ_CALLER_ID REVOKED; egress 000 DAY5; WA flip INERT (disk=1, containers no WHATSAPP_ENABLED). ACC 12:00 egress verdict+SIP template; 12:30 owner-escalate."},
    "OPS-006": {"status": "UPDATE", "evidence_tail": "PILOT 11:37 IST (Sep2 CRON): loop DEAD 50h+ re-confirm (batch211 ok=0/fail=3 REVOKED CLI, proc0 cron0); hot-queue 09-02 PRESENT 43. 10:30 digest MISSED — ACC 12:15 digest file."},
    "ENG-003": {"status": "BLOCKED", "evidence_tail": "PILOT 11:37 IST (Sep2 CRON): watchdog absent (crontab 0); loop DEAD 50h+ bina watchdog. 09:30 MISSED. ACC 12:30 commit+runbook+watchdog."},
    "HNT-004": {"status": "BLOCKED", "evidence_tail": "PILOT 11:37 IST (Sep2 CRON): leads/ ABSENT (ammo ZERO); hot-queue 09-02 43-lead conversion source. ACC 12:30 50-lead DND CSV."},
    "GRD-003": {"status": "BLOCKED", "evidence_tail": "PILOT 11:37 IST (Sep2 CRON): 11:00 gate MISSED — verdicts OWED (7). ACC 12:00 PASS/FAIL file command_center/data."},
    "SUC-002": {"status": "UPDATE", "evidence_tail": "PILOT 11:37 IST (Sep2 CRON): Jiya sole payer 1,999; 12:00 SMTP SENT proof IMMINENT. DID-independent."},
    "BRD-002": {"status": "UPDATE", "evidence_tail": "PILOT 11:37 IST (Sep2 CRON): mirror VERIFIED fresh (VPS mtime 05:26Z). ACC 12:00 page verify + cadence."},
}
n = 0
for t in tasks:
    u = updates.get(t.get("id"))
    if u:
        t["status"] = u["status"]
        t["evidence_tail"] = u["evidence_tail"]
        t["updated_at"] = ts
        n += 1
save(tp, tasks)
print(f"TASKS: {n} updated")

# ---------- 3) BOTS.JSON ----------
bp = os.path.join(base, "bots.json")
bots = load(bp)
sts = {
    "Pilot": "11:37 IST SWEEP: /health 37a1daf8 healthy uptime 17h33m; loop DEAD 50h+ (batch211 REVOKED CLI; proc0 cron0); SIP 5 vars len=0 (DID NAHI); WA flip INERT (disk=1 containers unbooted); auto_sent 0; HOT-QUEUE 09-02 PRESENT 43/43 UPI+wa_link; leads/ ABSENT; WAHA UP 7d sendText OPEN. 1 ray alive: WA manual sends (SAL-003). FLEET ACK 0 48h+, GRD 11:00 missed.",
    "sales": "SAL-003 BLOCKED BOTTLENECK OWNER: 0 sends 5+ din; WAHA OPEN + hot-queue 09-02 43 UPI = EXECUTE >=10, ACC 12:30, phir reassign+owner.",
    "platform": "PLT-004 BLOCKED: SIP 5 vars len=0; egress 000 DAY5; VOBIZ_CALLER_ID REVOKED; WA flip INERT. ACC 12:00 egress verdict+SIP template; 12:30 owner-escalate.",
    "operations": "OPS-006 UPDATE: loop DEAD 50h+; hot-queue 09-02 PRESENT; 10:30 digest MISSED — ACC 12:15.",
    "hunter": "HNT-004 BLOCKED: leads/ ABSENT; hot-queue 09-02 conversion source; ACC 12:30 50-lead DND CSV.",
    "guardian": "GRD-003 BLOCKED: 11:00 MISSED — 7 verdicts OWED; ACC 12:00.",
    "success": "SUC-002 UPDATE: Jiya sole payer 1,999 P0; ACC 12:00 SMTP SENT proof.",
    "engineering": "ENG-003 BLOCKED: 09:30 MISSED; watchdog absent (crontab 0); ACC 12:30 commit+runbook+watchdog.",
    "board": "BRD-002 UPDATE: mirror VERIFIED fresh 10:56 push; ACC 12:00 page verify + cadence.",
}
for k, v in sts.items():
    if k in bots:
        bots[k]["status"] = v
save(bp, bots)
print("BOTS: statuses refreshed")

# ---------- 4) PINNED.JSON ----------
pp = os.path.join(base, "pinned.json")
pin = load(pp)
pin["last_updated"] = now.strftime("%Y-%m-%dT%H:%M+05:30")
pin["vps_status"] = "UP (/health 37a1daf8 healthy uptime17h33m); loop DEAD 50h+ (batch211 REVOKED CLI; proc0 cron0); SIP 5 vars len=0; VOBIZ_CALLER_ID REVOKED; WA flip INERT (disk=1 containers unbooted); auto_sent 0; HOT-QUEUE 09-02 PRESENT 43/43 UPI+wa_link; leads/ ABSENT; egress 000 DAY5; WAHA UP 7d"
pin["verified_revenue"] = "₹1,999 (Jiya INV/2026-27/0001)"
pin["target"] = "₹5,00,000"
pin["gap"] = "₹4,98,001"
pin["bottleneck"] = "DID NAHI landed (SIP 5 vars len=0; Jio order in-flight) → dialer dead → WA flip INERT → 86 UPI deep-links ZERO sends → fleet ACK 0 48h+"
pin["pipeline"] = "86 HOT UPI deep-links (queues 09-01+09-02), 0 WA sends, 0 dialer connects, Jiya P0"
pin["hot"] = "hot-queue 09-02 43 UPI warm leads (SAL-003 ABHI, ACC 12:30) + Jiya retention (SUC-002 12:00)"
pin["action"] = "SAL-003 >=10 sendText (WAHA OPEN); PLT-004 egress verdict+SIP template; GRD verdicts overdue; owner: WA restart approval + Jio DID follow-up"
pin["next_expected_payment"] = "WA sendText reply → UPI close ya Jiya retention — evidence ke saath"
save(pp, pin)
print("PINNED: refreshed")
print("DONE")