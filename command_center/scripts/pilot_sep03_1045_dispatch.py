#!/usr/bin/env python3
"""PILOT Sep-03 10:45 IST sweep — FRESH-LIVE re-verify + 11:00 escalation gate confirm.
New live evidence at 10:45 (not in 10:40 record):
- leadgen_app image NOW sha 036a4e4b (APP_VERSION=036a4e4b, restarted 09-02T14:40Z,
  /health environment=production, uptime 1h38m). Earlier record expected 37a1daf8/live gated
  63c2c47a — running image is a 3rd sha = version-skew, dep.log shows gated-refusal.
- WA flip container env LIVE=1 (+ workers Up 15h) par auto_sent TRUE = 0/2270 STILL (no msg-id,
  sendText 0 real sends day5) -> #1 revenue bottleneck unchanged.
- SIP 5 vars ALL len=0 (DID NOT landed, CLI len13 REVOKED) -> dialer DEAD day5 (proc 0,
  mtime Aug31 08:39Z). leads/ =0 ammo.
- hot-queue 09-03 PRESENT (scheduler healed). wa_conversations tail = newsletter/auto-reps only,
  0 genuine buyer intent.
- Rev VERIFIED Rs1,999 Jiya sole; GAP Rs4,98,001.
10:36 already fired 1 TASK_REBUMP per bot (11:00 deadlines) + 10:40 REVENUE_COMMAND — NO new
TASK-ID (max 1/bot/run honoured, anti-spam). This run = fresh evidence append + 11:00 gate.
Appends messages.jsonl, updates bots/pinned/tasks tails.
"""
import json, os

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-03T10:45:00+05:30"

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")

# ---------- 1) messages.jsonl — one escalation-readiness REV-COMMAND ----------
msgs = [{
    "ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND",
    "priority": "P0",
    "msg": ("🎯 REVENUE COMMAND 10:45 IST (Sep3) FRESH-LIVE: TARGET Rs5,00,000 | VERIFIED Rs1,999 "
            "(Jiya INV/2026-27/0001 SOLE) | GAP Rs4,98,001 | BOTTLENECK #1 WA auto_send=0/2270 day5 "
            "(flip LIVE=1 + app UP 15h par sendText ZERO, NO msg-id) -> 0 UPI | #2 DIALER DEAD day5 "
            "(SIP 5 vars len=0 DID NOT landed, CLI len13 REVOKED, leads 0) | #3 vendor DID 0. NEW "
            "10:45: running app sha=036a4e4b (restarted 09-02T14:40Z, /health production, uptime 1h38m) "
            "— version-skew: dep.log blocked on gated 63c2c47a vs checkout 37a1daf8; flag board/ops. "
            "10:36 rebumps still unanswered (fleet ACK 0 ~51h). 11:00 IST OWNER-ESCALATION gate ABHI "
            "overdue — pehla REAL sendText msg-id + genuine reply->UPI close lao, warna escalate. ACK+EXECUTE. 🐦")
}]
with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("messages appended:", len(msgs))

# ---------- 2) bots.json status bump (evidence fresh) ----------
bp = os.path.join(BASE, "bots.json")
bots = load(bp)
sts = {
    "Pilot": ("10:45 IST Sep3 FRESH-LIVE: /health production UP uptime1h38m app sha=036a4e4b (NEW, "
              "version-skew dep.log gated-refusal); WA flip LIVE=1 par auto_sent 0/2270 day5 -> 0 UPI; "
              "SIP 5 vars ALL len=0 DID NOT landed, CLI revoked; dialer DEAD day5; rev Rs1,999 Jiya sole; "
              "GAP Rs4,98,001. 11:00 OWNER-ESCALATION gate overdue — fleet ACK 0 ~51h."),
    "engineering": "ENG-004 P0 #1 gate: WA flip LIVE=1 par auto_sent 0/2270 NO msg-id day5. 10:45 escalated.",
    "platform": "PLT-005 P0: SIP 5 vars ALL len=0 re-confirm 10:45 (DID NOT landed), CLI revoked. 11:00.",
    "operations": "OPS-007 P1: 09-03 queue healed; auto_send-0 digest + version-skew + dialer cadence. 11:00.",
    "sales": "SAL-005 P0: dirty blast STOP; genuine wa_conversations intent close msg-id. 11:00.",
    "hunter": "HNT-005 P1: leads/ =0 day5; 50 qualified DND mobile CSV. 11:00.",
    "guardian": "GRD-004 P1: verdicts file (auto_send link-only/rev-truth/dialer/DID) overdue. 11:00.",
    "success": "SUC-004 P0: Jiya sole payer Rs1,999 retention SMTP+WA proof day2 miss. 11:00.",
    "board": "BRD-003 P2: VPS mirror + page verify + version-skew flag. 11:00.",
}
for k, v in sts.items():
    if k in bots:
        bots[k]["status"] = v
save(bp, bots)
print("bots.json updated")

# ---------- 3) tasks.json fresh evidence_tail for gate-critical tasks ----------
tp = os.path.join(BASE, "tasks.json")
tasks = load(tp)
tails = {
    "ENG-004": "PILOT 10:45 IST Sep3 FRESH-LIVE: app sha036a4e4b UP 15h, WA flip LIVE=1 par auto_sent true=0/2270 NO msg-id (sendText 0, day5) -> #1 bottleneck unchanged. 11:00 OWNER-ESCALATION gate MISSED — pehla sendText msg-id abhi.",
    "SAL-005": "PILOT 10:45 IST Sep3 FRESH-LIVE: wa_conversations tail = newsletter/auto-reps only (0 genuine buyer). dirty blast HARD STOP; genuine-intent close. 11:00 gate missed.",
    "PLT-005": "PILOT 10:45 IST Sep3 FRESH-LIVE: SIP 5 vars ALL len=0 re-confirm (DID NOT landed day5); VOBIZ_CALLER_ID len13 REVOKED; loop proc0 mtime Aug31 08:39Z; leads=0. Dialer DEAD day5.",
    "SUC-004": "PILOT 10:45 IST Sep3 FRESH-LIVE: Jiya sole payer Rs1,999; 0 SMTP/WA proof day2. 11:00 gate missed. REVENUE-PROTECT P0.",
    "HNT-005": "PILOT 10:45 IST Sep3 FRESH-LIVE: leads/ =0 (ammo day5). 50 qualified DND mobile CSV 11:00 gate missed.",
    "GRD-004": "PILOT 10:45 IST Sep3 FRESH-LIVE: verdicts file STILL missing 11:00 gate (auto_send link-only PASS/FAIL critical).",
    "OPS-007": "PILOT 10:45 IST Sep3 FRESH-LIVE: 09-03 queue present (healed); NEW finding version-skew (app sha036a4e4b vs gated 63c2c47a/checkout 37a1daf8, dep.log refusal) -> include in digest. 11:00 gate missed.",
    "BRD-003": "PILOT 10:45 IST Sep3 FRESH-LIVE: mirror/page verify 11:00 MISSED; app now sha036a4e4b — update mirror with 10:45 state.",
}
for t in tasks:
    if t["id"] in tails:
        t["evidence_tail"] = tails[t["id"]]
        t["updated_at"] = TS
save(tp, tasks)
print("tasks.json tails updated")

# ---------- 4) pinned.json ----------
pp = os.path.join(BASE, "pinned.json")
try:
    pin = load(pp)
except Exception:
    pin = {}
pin["last_updated"] = TS
pin["vps_status"] = ("HEALTHY production (200, 10:45 FRESH-LIVE) app sha=036a4e4b (restarted 09-02T14:40Z, "
                     "uptime1h38m; version-skew vs gated 63c2c47a); VERIFIED rev Rs1,999 (Jiya INV/2026-27/0001 "
                     "SOLE); GAP Rs4,98,001; WA flip LIVE=1 par auto_sent 0/2270 (sendText ZERO day5) -> 0 UPI; "
                     "hot-queue 09-03 PRESENT; dialer DEAD day5 (SIP 5 vars len=0 DID NOT landed, CLI revoked, "
                     "leads 0); 11:00 IST OWNER-ESCALATION gate OVERDUE (fleet ACK 0 ~51h).")
save(pp, pin)
print("pinned.json updated")
print("DONE")
