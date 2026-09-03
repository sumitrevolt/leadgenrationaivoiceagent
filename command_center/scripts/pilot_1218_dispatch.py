#!/usr/bin/env python3
"""PILOT 09-02 12:18 IST sweep — FRESH live evidence (12:12-12:18 IST):
/health 37a1daf8 healthy (uptime 18h14m, production);
call_loop DEAD 50h+ (mtime Aug31 08:39:55Z batch211 ok=0/fail=3 REVOKED CLI; proc0 cron0);
SIP grep '^SIP_HOST=.' = 0 lines -> DID NAHI landed (SIP 5 vars empty);
container env WAENV=0 (leadgen_worker) = WA flip INERT (disk .env=1, containers unbooted);
auto_sent true=0 (ZERO WA sends); hot-queue 09-02 PRESENT (44 rows/43 leads);
leads/ ABSENT (ammo ZERO); egress api.vobiz.com 000@6s DAY5; WAHA no-key 401 expected gate;
FLEET ACK 0 since 00:12Z (~48h); NO bot evidence since 11:37 rebump
(no digest/verdict/CSV/SMTP/sendText proof anywhere on VPS).
SINGLE EXECUTABLE REVENUE RAIL = SAL-003 WA sendText (WAHA OPEN, hot-queue 09-02 43 UPI).
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

# ---------- 1) LEDGER APPEND (9 msgs = 1 REV-COMMAND + 8 rebumps) ----------
lines = [
    {"ts": ts, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "🎯 REVENUE COMMAND 12:18 IST (Sep2): TARGET ₹5,00,000 | VERIFIED ₹1,999 (Jiya INV/2026-27/0001 sole) | GAP ₹4,98,001 | PIPELINE: hot-queue 09-02 43 UPI warm + 09-01 43 (86 deep-links, ZERO sends auto_sent=0); dialer DEAD 50h+ (REVOKED CLI, proc0); leads/ ammo ZERO | HOT: WA rail = SOLE executable (WAHA UP sendText OPEN) + Jiya churn P0 | BOTTLENECK: DID NAHI (SIP vars empty, Jio order in-flight) → dialer dead; WA flip INERT (container WAENV=0); fleet ACK 0 ~48h | ACTION: SAL-003 >=10 sendText PROOF 13:00 (hot-queue 09-02 wa_link+UPI); PLT-004 egress+template 12:30 + restart owner-approve; SUC Jiya SMTP 13:00; GRD 7 verdicts 13:00; OPS digest 13:00; ENG watchdog 13:00; HNT 50-lead CSV 13:00; BRD page verify 13:00 | NEXT: WA sends → replies → UPI → ledger | 0 proof 13:00 = reassign + owner escalation. EXECUTE, reporting nahi."},
    {"ts": ts, "from": "PILOT", "to": "sales", "task_id": "SAL-003", "type": "ESCALATION", "priority": "P0",
     "msg": "SAL-003 12:18 IST — FINAL PUSH: hot-queue 09-02 PRESENT 43/43 (AFM SOLAR head 919881915434, UPI 8459012607@axl); auto_sent true=0; WAHA sendText OPEN (leadgen_waha UP 7d; with-key /api/sessions 200). ACCEPTANCE 13:00 IST: >=10 REAL sendText proof (HTTP 200 + chat id + wa.me deep-link hit) + vendor DID proof (Call Soft wa.me/917599967999 / RMS 080-47652298). 0 proof 13:00 → reassign success+bounty + owner escalation. YEHI SOLE REVENUE RAIL HAI."},
    {"ts": ts, "from": "PILOT", "to": "platform", "task_id": "PLT-004", "type": "ESCALATION", "priority": "P0",
     "msg": "PLT-004 12:18 IST — FRESH: /health 37a1daf8 healthy uptime 18h14m; SIP grep ^SIP_HOST=. = 0 (DID NAHI); container WAENV=0 LIVE CONFIRMED (disk .env=1 INERT = restart pending); egress api.vobiz.com 000@6s DAY5. ACCEPTANCE 12:30 IST: egress verdict + re-test + Jio SIP 5-var env template; 13:00: owner-approved docker restart plan (WA flip + auto_sent>0 proof)."},
    {"ts": ts, "from": "PILOT", "to": "operations", "task_id": "OPS-006", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "OPS-006 12:18 IST — loop DEAD 50h+ re-confirm (mtime Aug31 08:39:55Z batch211, proc0 cron0). 10:30 + 12:15 digests MISSED. ACCEPTANCE 13:00 IST: digest file command_center/data (loop-death, hot-queue 09-02, restart-ready, WA-rail status) + hourly cadence. 0 proof → reassign."},
    {"ts": ts, "from": "PILOT", "to": "engineering", "task_id": "ENG-003", "type": "TASK_REBUMP", "priority": "P1",
     "msg": "ENG-003 12:18 IST — watchdog ABSENT re-confirm (crontab 0); loop DEAD 50h+ bina watchdog. 09:30 gate missed 3x. ACCEPTANCE 13:00 IST: commit sha + Jio SIP failover runbook + watchdog (mtime >10min alert/restart sirf owned DID pe)."},
    {"ts": ts, "from": "PILOT", "to": "hunter", "task_id": "HNT-004", "type": "TASK_REBUMP", "priority": "P1",
     "msg": "HNT-004 12:18 IST — leads/ ABSENT re-confirm (ammo ZERO). 09:30 gate missed 3x. ACCEPTANCE 13:00 IST: 50-lead MOBILE-only DND-scrubbed CSV (path+count+DND-proof col; source = hot-queue 09-02 + Google Maps). DID landte hi ammo ready chahiye."},
    {"ts": ts, "from": "PILOT", "to": "guardian", "task_id": "GRD-003", "type": "TASK_REBUMP", "priority": "P1",
     "msg": "GRD-003 12:18 IST — 11:00 gate MISSED. 7 verdicts OWED: revenue-truth (snap mrr=5997/active=3 STALE vs ledger Jiya 1,999), loop-dead (CONFIRMED REVOKED CLI), WAHA HEALTHY (UP 7d, with-key 200), auto_sent=0, leads-absent, hot-queue-09-02 PRESENT, SAL-003 vendor+WA. ACCEPTANCE 13:00 IST: PASS/FAIL verdicts file command_center/data."},
    {"ts": ts, "from": "PILOT", "to": "success", "task_id": "SUC-002", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "SUC-002 12:18 IST — Jiya sole payer ₹1,999 churn P0 (INV/2026-27/0001). 12:00 gate MISSED. ACCEPTANCE 13:00 IST: SMTP SENT proof + WA follow-up artifact. DID-independent — koi bahana nahi."},
    {"ts": ts, "from": "PILOT", "to": "board", "task_id": "BRD-002", "type": "TASK_REBUMP", "priority": "P2",
     "msg": "BRD-002 12:18 IST — PILOT fresh push at 12:25 IST (tasks/bots/pinned/messages). ACCEPTANCE 13:00 IST: page verify + cadence proof. Visualization only — commands kisi ko mat do."},
]
with open(os.path.join(base, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in lines:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print(f"LEDGER: {len(lines)} appended @ {ts}")

# ---------- 2) TASKS.JSON — status + evidence_tail ----------
tp = os.path.join(base, "tasks.json")
tasks = load(tp)
updates = {
    "SAL-003": {"status": "BLOCKED", "evidence_tail": "PILOT 12:18 IST (Sep2 CRON): hot-queue 09-02 PRESENT 43/43 UPI+wa_link; auto_sent true=0 (ZERO sends 5+ din); WAHA with-key 200 OPEN. ACC 13:00 >=10 sendText + vendor DID — FINAL PUSH, 0 proof = reassign."},
    "PLT-004": {"status": "BLOCKED", "evidence_tail": "PILOT 12:18 IST (Sep2 CRON): /health 37a1daf8 healthy uptime18h14m; SIP grep ^SIP_HOST=. =0 (DID NAHI); container WAENV=0 LIVE (disk .env=1 INERT restart pending); egress 000@6s DAY5. ACC 12:30 egress+template; 13:00 restart plan + auto_sent proof."},
    "OPS-006": {"status": "UPDATE", "evidence_tail": "PILOT 12:18 IST (Sep2 CRON): loop DEAD 50h+ re-confirm (batch211 REVOKED CLI, proc0 cron0); 10:30+12:15 digests MISSED. ACC 13:00 digest file + cadence."},
    "ENG-003": {"status": "BLOCKED", "evidence_tail": "PILOT 12:18 IST (Sep2 CRON): watchdog ABSENT (crontab 0); 09:30 gate missed 3x. ACC 13:00 commit sha + runbook + watchdog."},
    "HNT-004": {"status": "BLOCKED", "evidence_tail": "PILOT 12:18 IST (Sep2 CRON): leads/ ABSENT (ammo ZERO); 09:30 gate missed 3x. ACC 13:00 50-lead DND CSV."},
    "GRD-003": {"status": "BLOCKED", "evidence_tail": "PILOT 12:18 IST (Sep2 CRON): 11:00 gate MISSED — 7 verdicts OWED. ACC 13:00 PASS/FAIL file command_center/data."},
    "SUC-002": {"status": "UPDATE", "evidence_tail": "PILOT 12:18 IST (Sep2 CRON): Jiya sole payer 1,999 P0; 12:00 gate MISSED. ACC 13:00 SMTP SENT proof + WA follow-up."},
    "BRD-002": {"status": "UPDATE", "evidence_tail": "PILOT 12:18 IST (Sep2 CRON): PILOT fresh push 12:25; ACC 13:00 page verify + cadence."},
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
    "Pilot": "12:18 IST SWEEP: /health 37a1daf8 healthy uptime18h14m; loop DEAD 50h+ (batch211 REVOKED CLI; proc0 cron0); SIP vars EMPTY (DID NAHI); container WAENV=0 (WA flip INERT); auto_sent 0; hot-queue 09-02 PRESENT 43 UPI; leads/ ABSENT; egress 000 DAY5; fleet ACK 0 ~48h. SOLE rail = SAL-003 WA sends.",
    "sales": "SAL-003 BLOCKED BOTTLENECK OWNER: 0 sends 5+ din; WAHA OPEN + hot-queue 09-02 43 UPI = EXECUTE >=10, ACC 13:00, phir reassign+bounty.",
    "platform": "PLT-004 BLOCKED: SIP vars EMPTY (grep=0 lines); egress 000 DAY5; container WAENV=0; ACC 12:30 egress+template; 13:00 restart plan.",
    "operations": "OPS-006 UPDATE: loop DEAD 50h+; digests MISSED 2x — ACC 13:00 digest file.",
    "hunter": "HNT-004 BLOCKED: leads/ ABSENT; 09:30 missed 3x — ACC 13:00 50-lead DND CSV.",
    "guardian": "GRD-003 BLOCKED: 11:00 MISSED — 7 verdicts OWED; ACC 13:00.",
    "success": "SUC-002 UPDATE: Jiya sole payer 1,999 P0; 12:00 MISSED — ACC 13:00 SMTP SENT proof.",
    "engineering": "ENG-003 BLOCKED: 09:30 missed 3x; watchdog absent — ACC 13:00 commit+runbook+watchdog.",
    "board": "BRD-002 UPDATE: PILOT push 12:25; ACC 13:00 page verify + cadence.",
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
pin["vps_status"] = "UP (/health 37a1daf8 healthy uptime18h14m); loop DEAD 50h+ (batch211 REVOKED CLI; proc0 cron0); SIP 5 vars EMPTY (DID NAHI); container WAENV=0 INERT; auto_sent 0; hot-queue 09-02 PRESENT 43 UPI; leads/ ABSENT; egress 000 DAY5; WAHA with-key 200 OPEN"
pin["verified_revenue"] = "₹1,999 (Jiya INV/2026-27/0001)"
pin["target"] = "₹5,00,000"
pin["gap"] = "₹4,98,001"
pin["bottleneck"] = "DID NAHI (SIP vars empty; Jio order in-flight) → dialer dead; WA flip INERT (container WAENV=0); fleet ACK 0 ~48h"
pin["pipeline"] = "86 HOT UPI deep-links (queues 09-01+09-02), 0 WA sends, 0 dialer connects, Jiya P0"
pin["hot"] = "hot-queue 09-02 43 UPI warm + WAHA sendText OPEN (SAL-003 ABHI, ACC 13:00) + Jiya retention (SUC-002)"
pin["action"] = "SAL-003 >=10 sendText proof 13:00; PLT-004 egress+template 12:30 + restart owner-approve; GRD verdicts; owner: WA restart approval + Jio DID follow-up"
pin["next_expected_payment"] = "WA sendText reply → UPI close ya Jiya retention — evidence ke saath"
save(pp, pin)
print("PINNED: refreshed")
print("DONE")