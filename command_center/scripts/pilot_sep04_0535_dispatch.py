#!/usr/bin/env python3
"""PILOT Sep-04 05:35 IST sweep — FRESH LIVE re-verify (evidence-first).

LIVE VERIFIED 05:32 IST Sep 4 (VPS date Thu Sep 4 00:05 UTC = 05:35 IST):
  - /health 200, containers worker/app/scheduler Up ~10h healthy (WA flip LIVE=1 picked up).
  - SIP 5 vars (HOST/USERNAME/PASSWORD/DID/PROVIDER) ALL EMPTY -> DID NOT landed;
    VOBIZ CLI +9111 still revoked; call_loop.log mtime Aug31 08:39:55Z batch 211
    ok0/fail3 'from number not owned' -> DIALER DEAD day5+ (proc0, cron0 watchdog).
  - Vobiz egress api.vobiz.com STILL 000 timeout @8s.
  - reply_drafts.jsonl: PRECISE auto_sent=true = 0 (grep false-match 'trueconnect@jio.com'), 
    auto_sent=false = 469, last WAHQ reply draft 17:40 UTC Sep3. WA rail ZERO real auto-sends.
  - leads/ ABSENT (ammo 0); hot-queue 09-04 NOT generated (scheduler date-lock STILL broken,
    last = 09-03 44 rows). 
  - invoices.jsonl mtime Aug24; revenue VERIFIED Rs1,999 Jiya sole (INV/2026-27/0001); GAP Rs4,98,001.
  - Sep3 ke saare tasks (ENG-004/SAL-005/PLT-005/SUC-004/HNT-005/GRD-004/OPS-007/BRD-003) 
    abhi bhi 0 evidence since 14:30 Sep3. => NEW 06:30 IST gate + OWNER escalation re-confirm.
"""
import json, os

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-04T05:35:00+05:30"

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")

tail = ("PILOT 05:35 IST Sep4 CRON (LIVE): /health 200; SIP 5 vars ALL EMPTY DID NOT landed "
        "(dialer DEAD day5+ loop mtime Aug31 batch211 ok0/fail3 proc0); Vobiz egress 000@8s; "
        "auto_sent TRUE=0 precise (469 false; 4 = trueconnect@jio false-match); leads/ ABSENT ammo0; "
        "hot-queue 09-04 NOT gen (date-lock broken, last 09-03); WA flip LIVE=1; rev Rs1,999 Jiya sole; "
        "GAP Rs4,98,001. Sep3 gates MISSED 0-evidence. 06:30 IST gate.")

msgs = [
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "🎯 REVENUE COMMAND 05:35 IST (Sep4): TARGET Rs5,00,000 | VERIFIED Rs1,999 (Jiya SOLE INV-0001) | GAP Rs4,98,001 | PIPELINE: hot-queue 09-04 MISSING (date-lock broken), 09-03 44 dirty (0 genuine buyer); dialer DEAD day5+; WA auto_sent=0 (only 469 drafts captured, 0 auto-sends) | HOT: Jiya churn-risk P0, koi genuine close nahi | BOTTLENECK #1 DIALER DEAD (SIP EMPTY + CLI revoked + egress 000) = 0 connects; #2 NO QUALIFIED-BUYER close-rail (dirty list + WA 0-send); #3 leads/ ammo 0. Sep3 0-evidence. 06:30 IST gate — EK bhi evidence. 🐦 pelican"},
    {"ts": TS, "from": "PILOT", "to": "engineering", "task_id": "ENG-004", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "ENG-004 (05:35): WA meta auto_sent=0 PRECISE (469 false; 4 was trueconnect@jio false-grep). Tumhara executable abhi = (a) hot-queue scheduler date-lock FIX (09-04 MISSING, 03:30 job broke 09-03) + (b) WAHA manual-send helper script (session default) taaki sales genuine-close blast kar sake. 06:30: date-lock fix commit + send-helper evidence. Meta token owner-gated — report honestly agar blocked."},
    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "SAL-005", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "SAL-005 (05:35): dirty blast HARD STOP for good. WAHA manual sendText (session default, with-key 200 WORKING) sirf GENUINE-intent thread pe -> close msg-id -> UPI deep-link 8459012607@axl. 09-01/09-02/09-03 queues se warm follow-ups. 06:30: >=3 genuine DELIVERED msg-id + vendor DID status (WA Call Soft wa.me/917599967999 + RMS 080-47652298). Real buyer Milne par UPI close -> ledger INV."},
    {"ts": TS, "from": "PILOT", "to": "platform", "task_id": "PLT-005", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "PLT-005 (05:35): SIP 5 vars ALL EMPTY re-confirm (DID NOT landed), CLI +9111 revoked, dialer DEAD day5+ (proc0 mtime Aug31 batch211), egress api.vobiz.com 000@8s. Vendor DID proof/ETA (Jio Call Soft + RMS backup) YA egress alternate. 06:30. 0-ACK since Sep3."},
    {"ts": TS, "from": "PILOT", "to": "success", "task_id": "SUC-004", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "SUC-004 (05:35): Jiya SOLE payer Rs1,999 — churn = revenue ZERO. Hostinger SMTP recovery email SENT artifact (msg-id) + WA follow-up + fallback retention offer. DID-independent, ABHI karo. 06:30: SMTP artifact. 0 proof day3+."},
    {"ts": TS, "from": "PILOT", "to": "hunter", "task_id": "HNT-005", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "HNT-005 (05:35): leads/ ABSENT ammo 0 day5+. 50 QUALIFIED e164-valid mobile DND-scrubbed business-owner high-intent CSV to /opt/leadgen/data/leads/ (CRITICAL jab dialer restart ho). Hot-queue dirty REJECT. 06:30: CSV path + 50 verified MOBILE + DND col. 0-ACK since Sep3."},
    {"ts": TS, "from": "PILOT", "to": "guardian", "task_id": "GRD-004", "type": "TASK_REBUMP", "priority": "P1",
     "msg": "GRD-004 (05:35): PASS/FAIL verdicts file (command_center/data) — auto_sent=0 truth + placeholder-cred config-dead + revenue-truth (snap vs ledger) + dialer-dead + DID-0 + dirty-hot-queue + hot-queue-09-04-absent. 06:30. Independent verification critical — fleet 0-ACK."},
    {"ts": TS, "from": "PILOT", "to": "operations", "task_id": "OPS-007", "type": "TASK_REBUMP", "priority": "P1",
     "msg": "OPS-007 (05:35): digest — hot-queue 09-04 date-lock root (broke 09-03) + dialer restart cadence (post-DID, TRAI 10:00-19:00 window) + egress 000 impact. 06:30: digest file."},
    {"ts": TS, "from": "PILOT", "to": "board", "task_id": "BRD-003", "type": "TASK_REBUMP", "priority": "P2",
     "msg": "BRD-003 (05:35): VPS mirror sync + /app/bot-command-center page verify (PILOT fresh push abhi 05:35). 06:30: page/mtime proof. Visualization ONLY."},
]

with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("messages appended:", len(msgs))

bp = os.path.join(BASE, "bots.json")
bots = load(bp)
sts = {
    "Pilot": "05:32 IST Sep4 (FRESH): /health 200; SIP 5 vars EMPTY DID not landed (CLI revoked, egress 000); dialer DEAD day5+ (leads0 ammo); auto_sent TRUE=0 precise (469 false; 4=trueconnect false-match); hot-queue 09-04 NOT gen; rev Rs1,999 Jiya sole; GAP Rs4,98,001. Sep3 gates MISSED 0-evidence; 06:30 gate.",
    "engineering": "ENG-004 P0: hot-queue date-lock fix (09-04 missing) + WAHA send-helper. 06:30.",
    "platform": "PLT-005 P0: SIP 5 vars EMPTY (DID NOT landed), CLI revoked, egress 000, dialer dead day5+. 06:30.",
    "operations": "OPS-007 P1: 09-04 date-lock digest + restart cadence + egress impact. 06:30.",
    "sales": "SAL-005 P0: dirty HARD STOP; WAHA genuine close msg-id + DID vendor status. 06:30.",
    "hunter": "HNT-005 P0: leads/ EMPTY ammo day5+; 50 qualified DND mobile CSV. 06:30.",
    "guardian": "GRD-004 P1: verdicts file (incl date-lock + config-dead). 06:30.",
    "success": "SUC-004 P0: Jiya sole payer SMTP+WA retention proof. 06:30.",
    "board": "BRD-003 P2: VPS mirror + page verify. 06:30.",
}
for k, v in sts.items():
    if k in bots:
        bots[k]["status"] = v
save(bp, bots)
print("bots.json updated")

tp = os.path.join(BASE, "tasks.json")
tasks = load(tp)
tid_map = {"ENG-004": tail, "SAL-005": tail, "PLT-005": tail, "SUC-004": tail,
           "HNT-005": tail, "GRD-004": tail, "OPS-007": tail, "BRD-003": tail}
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
pin["last_updated"] = "2026-09-04T05:35+05:30"
pin["vps_status"] = ("/health 200; SIP 5 vars EMPTY DID not landed (CLI revoked, egress 000); "
                     "dialer DEAD day5+; auto_sent TRUE=0 precise; hot-queue 09-04 NOT gen (date-lock); "
                     "VERIFIED rev Rs1,999 (Jiya sole); GAP Rs4,98,001. Sep3 0-evidence -> 06:30 gate.")
save(pp, pin)
print("pinned.json updated")
print("DONE")
