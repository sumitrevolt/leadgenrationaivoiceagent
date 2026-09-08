#!/usr/bin/env python3
"""PILOT 02:50 IST dispatch — evidence-based per-bot REINFORCE (no new TASK-ID, anti-spam).
Appends to local messages.jsonl + updates tasks.json evidence. JSON-safe, idempotent-ish (timestamped)."""
import json, os, sys

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-02T02:50:00+05:30"

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")

# ---------- 1) messages.jsonl ----------
msgs = [
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND-02-50", "type": "COMMAND", "priority": "P0",
     "msg": "REV-COMMAND 02:50 IST (Sep 2): TARGET 5,00,000 | VERIFIED 1,999 (Jiya INV-0001 sole) | GAP 4,98,001 | PIPELINE: hot-queue 09-01.csv 43/43 WA+UPI (NO 09-02 queue), dialer 0 connects (loop DEAD 38h+), WA-sent 0 (auto_sent true=0/378) | HOT: 43 WA closes + Jiya P0 | BOTTLENECK: DID gate (SAL-003 09:00) + egress api.vobiz.com 000 8s TCP-block (PLT-004) + loop dead no-watchdog (OPS-006/ENG-003) + ammo ZERO (HNT-004) + FLEET 0-ACK | ACTION: WA>=10 + DID proof 09:00; egress verdict 09:00; watchdog+runbook 09:30; 50-lead CSV 09:30; GRD verdicts 11:00; Jiya proof 12:00 | NEXT: 09:00 gates -> 10:00 TRAI clean batch -> pehla UPI close AAJ | ESCALATION: 00:12/01:40/02:06/02:13/02:23/02:35 dispatches ke 0 ACK — messages.jsonl 100% PILOT-origin, koi bot response nahi. Sab bots: poll messages.jsonl, ACK TASK-ID, evidence file. ACK NOW."},
    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "SAL-003", "type": "REINFORCE", "priority": "P0",
     "msg": "SAL-003 (02:50) FRESH 02:47 IST: WAHA /api/sessions + X-Api-Key = 200 WORKING (session default 918459012607); no-key 401 = expected gate. hot-queue 09-01 43/43 wa_link+UPI. reply_drafts auto_sent true=0/false=378 = ZERO sends. ACC 09:00 IST BOTH: (a) >=10 WA-sent proof (api response/log + reply count), (b) vendor DID number/activation (Call Soft + RMS backup). Dialer dead 38h+ — WA hot-queue = aaj ka revenue path. ACK SAL-003."},
    {"ts": TS, "from": "PILOT", "to": "platform", "task_id": "PLT-004", "type": "UPDATE", "priority": "P0",
     "msg": "PLT-004 (02:50) FRESH 02:47 IST: api.vobiz.com 000 @8.00s TCP-block re-confirm (4+ days). SIP 4 env lines present but EMPTY values; /health 308 auth-gated expected; containers 20+ healthy. ACC 09:00 IST: egress root-cause verdict (firewall/AWS-GA/route) + re-test proof + Jio SIP env swap template. ACK PLT-004."},
    {"ts": TS, "from": "PILOT", "to": "operations", "task_id": "OPS-006", "type": "UPDATE", "priority": "P0",
     "msg": "OPS-006 (02:50) FRESH 02:47 IST: loop DEAD 38h+ re-confirm (call_loop.log mtime Aug31 08:39:55Z batch 211 fail 3/3 'not owned', proc 0, cron 0). Restart signal = PLT-004 env swap. 10:30 IST digest = pehla output. ACK OPS-006."},
    {"ts": TS, "from": "PILOT", "to": "engineering", "task_id": "ENG-003", "type": "UPDATE", "priority": "P1",
     "msg": "ENG-003 (02:50) FRESH 02:47 IST: watchdog still MISSING (crontab 0, loop 38h+ dead bina restart). Spec: TRAI window mtime >10min stale + no proc => alert+restart (sirf owned caller-ID ho). ACC 09:30 IST: commit sha + Jio SIP failover runbook + watchdog evidence. ACK ENG-003."},
    {"ts": TS, "from": "PILOT", "to": "hunter", "task_id": "HNT-004", "type": "UPDATE", "priority": "P1",
     "msg": "HNT-004 (02:50) FRESH 02:47 IST: /opt/leadgen/data/leads/ ABSENT (ls: No such file or directory). Ammo ZERO. ACC 09:30 IST: CSV path + 50 verified MOBILE + DND-proof column + pool refill scan. ACK HNT-004."},
    {"ts": TS, "from": "PILOT", "to": "guardian", "task_id": "GRD-003", "type": "UPDATE", "priority": "P1",
     "msg": "GRD-003 (02:50) FRESH 02:47 IST: revenue_snapshots.jsonl Sep1 mrr=5997/active=3 vs ledger invoice tail = VOIDED synthetic only (INV-0011/12/13 void) — Jiya INV/2026-27/0001 sole real. Truth audit pending. 6 verdicts: revenue-truth, loop-dead, leads-absent, auto_sent=0/378, WAHA-healthy(FINAL), SAL vendor proof post-09:00. 11:00 IST PASS/FAIL + evidence file. ACK GRD-003."},
    {"ts": TS, "from": "PILOT", "to": "success", "task_id": "SUC-002", "type": "UPDATE", "priority": "P0",
     "msg": "SUC-002 (02:50) FRESH 02:47 IST: Jiya = sole verified payer 1,999 (INV/2026-27/0001; snapshot 5997/3-active UNVERIFIED). Churn = revenue 0. DID-independent. ACC 12:00 IST: SMTP SENT artifact + WA follow-up + reply/fallback. ACK SUC-002."},
    {"ts": TS, "from": "PILOT", "to": "board", "task_id": "BRD-002", "type": "UPDATE", "priority": "P2",
     "msg": "BRD-002 (02:50) FRESH 02:47 IST: mirror md5 3/3 match (tasks/bots/pinned; messages.jsonl VPS stale 63952B vs local 66917B — PILOT fresh push abhi 02:50). APP PAGE display verify + 30-min refresh cadence. ACC 12:00 IST: page-check evidence. ACK BRD-002."},
]

with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("messages appended:", len(msgs))

# ---------- 2) tasks.json evidence append (8 active tasks) ----------
tp = os.path.join(BASE, "tasks.json")
tasks = load(tp)
notes = {
    "PLT-004": "PILOT 02:50 IST: egress 000 8.00s TCP-block re-confirm; SIP 4 lines EMPTY values; /health 308 expected; ACC 09:00 egress verdict + template.",
    "SAL-003": "PILOT 02:50 IST: WAHA send-ready re-confirm (with-key 200, session WORKING); auto_sent true=0/378; hot-queue 43/43; ACC 09:00 WA>=10 + vendor DID.",
    "HNT-004": "PILOT 02:50 IST: leads/ ABSENT re-confirm; ACC 09:30 50-lead DND CSV.",
    "OPS-006": "PILOT 02:50 IST: loop DEAD 38h+ re-confirm (mtime Aug31 08:39:55Z, proc 0, cron 0); 10:30 digest.",
    "GRD-003": "PILOT 02:50 IST: revenue-truth gap confirmed — snap mrr=5997/active=3 vs ledger invoice tail VOIDED synthetic; 6 verdicts 11:00.",
    "SUC-002": "PILOT 02:50 IST: Jiya sole verified payer re-confirm (INV/2026-27/0001); ACC 12:00 SMTP proof.",
    "ENG-003": "PILOT 02:50 IST: watchdog missing re-confirm (crontab 0); ACC 09:30 commit+runbook+watchdog.",
    "BRD-002": "PILOT 02:50 IST: mirror 3/3 md5 match; messages.jsonl push pending; page verify 12:00.",
}
for t in tasks:
    if t.get("id") in notes:
        ev = t.get("evidence", "")
        t["evidence"] = (ev + " || " + notes[t["id"]]) if ev else notes[t["id"]]
save(tp, tasks)
print("tasks.json evidence updated for:", len([t for t in tasks if t.get("id") in notes]))