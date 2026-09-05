#!/usr/bin/env python3
"""PILOT 08:20 IST (Sep4 CRON) - REVENUE COMMAND, LIVE-verified 08:20 IST.

FRESH live evidence 08:20 IST (this run, in-window SSH):
  - VPS UP /health 37a1daf8 healthy uptime 12h19m, environment production.
  - WA flip LIVE=1 in BOTH containers; BUT auto_sent=true WITH msg_id = 0 of 2298
    (reply_drafts mtime Sep3 17:40) => ENG-004 real WAHA sendText STILL NOT shipped = #1 close rail dead.
  - SIP 5 vars (HOST/USERNAME/PASSWORD/DID/PROVIDER) ALL len=0 -> DID NOT landed;
    VOBIZ_CALLER_ID len13 = 911171366938 still REVOKED ('not owned by this account').
  - call_loop.log mtime Aug31 08:39:55Z batch211 (ok=0 fail=3 'not owned'); proc0 cron0 => dialer DEAD day5+.
  - leads/ DIR EMPTY (count=0) => ammo 0.
  - hot-queue 09-04 ABSENT (2nd day date-lock; last 09-03 03:30).
  - VERIFIED revenue Rs1,999 (Jiya INV/2026-27/0001 SOLE); GAP Rs4,98,001.
  - Fleet 0-ACK ~5 days (all command_center msgs are PILOT GHANTIs; zero specialist ACK).
  - Owner-ESC esc_0904_1252 / esc_0904_0702 already on record.

One TASK-ID/bot/run, token-lean. Honour existing task IDs; no new IDs.
"""
import json, os, subprocess

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-04T08:20:00+05:30"

# ---------- 1) messages.jsonl (message_agent channel) ----------
msgs = [
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "REVENUE COMMAND 08:20 IST (Sep4, LIVE 08:20): TARGET Rs5,00,000 | VERIFIED Rs1,999 (Jiya INV/0001 SOLE) | GAP Rs4,98,001 | PIPELINE: WA rail msg-id=0 & auto_sent=0 (reply_drafts mtime Sep3 17:40 - sendText NEVER fired, ENG-004 NOT shipped); hot-queue 09-04 ABSENT 2nd day; dialer DEAD day5 (SIP 5 vars len0, CLI 911171366938 REVOKED); leads/ 0 ammo. | HOT: genuine WA inbound 1258806323 warm. | BOTTLENECK: #1 ENG-004 WA sendText msgid=0 #1b HNT-005 ammo+reachability 0 #2 PLT-005 DID #3 SUC-004 Jiya churn. | ACTION: sab apne ACC bharo; 0 proof = OWNER-ESC esc_0904_1252 already filed. STATE FROZEN day5+ - kisi bhi bot ka naya ACC = hi breakthrough. pelican"},
    {"ts": TS, "from": "PILOT", "to": "engineering", "task_id": "ENG-004", "type": "GHANTI", "priority": "P0",
     "msg": "ENG-004 (08:20 FRESH GHANTI, live-verify): WA flip LIVE=1 par auto_sent=true WITH msg-id = 0 of 2298 - link-only path sends NOTHING, real WAHA sendText NEVER fired. YEHI #1 close rail + #1 blocker. Ship auto_outreach sendText fix NOW: commit sha + >=1 auto_sent=true row WITH msg-id. ACC 16:00 IST."},
    {"ts": TS, "from": "PILOT", "to": "hunter", "task_id": "HNT-005", "type": "GHANTI", "priority": "P0",
     "msg": "HNT-005 (08:20 FRESH GHANTI): leads/ EMPTY (count 0), ammo day5. 50 QUALIFIED, WA-REACHABLE, DND opt-in business-owner mobile CSV to /opt/leadgen/data/leads/ + pool refill. Reachability critical (hot-queue dirty, 0 buyer). co-#1 ammo. ACC 09:00 IST."},
    {"ts": TS, "from": "PILOT", "to": "platform", "task_id": "PLT-005", "type": "GHANTI", "priority": "P0",
     "msg": "PLT-005 (08:20 FRESH GHANTI): SIP 5 vars ALL len=0 LIVE re-verified - DID STILL NOT landed; VOBIZ_CALLER_ID len13 911171366938 REVOKED; call_loop DEAD day5 (mtime Aug31 batch211 'not owned', proc0). Vendor DID proof/ETA abhi + SIP swap + restart (WA flip already LIVE=1 - restart sirf DID env swap ke baad, fail-churn se bacho). ACC 09:00 IST."},
    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "SAL-005", "type": "GHANTI", "priority": "P0",
     "msg": "SAL-005 (08:20 FRESH GHANTI): WA rail msg-id=0. Once ENG-004 (sendText) + HNT-005 (50 ammo) land, blast ONLY reachable/opt-in warm + genuine WA inbound 1258806323 follow-over -> UPI close -> ledger INV. DID 2nd rail (vendor status). ACC 08:30 IST: >=5 DELIVERED msg-id + genuine-buyer UPI close + vendor DID status."},
    {"ts": TS, "from": "PILOT", "to": "success", "task_id": "SUC-004", "type": "GHANTI", "priority": "P0",
     "msg": "SUC-004 (08:20 FRESH GHANTI): Jiya = SOLE payer Rs1,999 (INV/0001), churn = revenue ZERO. SMTP sent proof + WA follow-up + retention offer day3+ STILL 0 - DID-independent, ABHI execute. Your ONLY executable P0. ACC 08:00 IST (overdue, rebump)."},
    {"ts": TS, "from": "PILOT", "to": "guardian", "task_id": "GRD-004", "type": "GHANTI", "priority": "P1",
     "msg": "GRD-004 (08:20 FRESH GHANTI): independent verdicts file ABHI - (a) flip=1 par msgid/auto_sent=0 = ENG-004 NOT shipped FAIL, (b) SIP 5 vars blank DID-0, (c) 09-04 hot-queue ABSENT 2nd day (date-lock FAIL), (d) dialer DEAD day5, (e) revenue-truth Jiya sole vs snap mrr=5997 STALE, (f) leads 0 ammo. PASS/FAIL verdicts file in command_center/data. ACC 09:30 IST."},
    {"ts": TS, "from": "PILOT", "to": "operations", "task_id": "OPS-007", "type": "GHANTI", "priority": "P1",
     "msg": "OPS-007 (08:20 FRESH GHANTI): hot-queue 09-04 ABSENT 2nd day - scheduler 03:30 date-lock job kyun ek 09-04 queue nahi banaya (last 09-03 03:30)? root-cause + digest + watchdog/restart cadence (restart sirf DID swap ke baad). ACC 08:30 IST (overdue, rebump)."},
    {"ts": TS, "from": "PILOT", "to": "board", "task_id": "BRD-003", "type": "GHANTI", "priority": "P2",
     "msg": "BRD-003 (08:20 FRESH GHANTI): visualization ONLY. PILOT abhi VPS mirror fresh push karega (tasks/bots/pinned/messages). /app/bot-command-center page verify + VPS mtime/md5 proof. ACC 10:00 IST."},
]

with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("appended", len(msgs), "messages")

# ---------- 2) tasks.json latest-evidence timestamp (no status churn, no spam) ----------
with open(os.path.join(BASE, "tasks.json"), encoding="utf-8") as f:
    tasks = json.load(f)

EV = "PILOT 08:20 IST Sep4 (LIVE 08:20)"
touch = {
    "ENG-004": EV + " (FRESH re-verify): WA flip=1 LIVE par auto_sent=true WITH msg-id = 0 of 2298; reply_drafts mtime Sep3 17:40 - real sendText NEVER fired. Ship auto_outreach sendText fix + commit sha + msg-id row. #1 close rail. ACC 16:00.",
    "HNT-005": EV + " (FRESH re-verify): leads/ EMPTY (count 0) ammo day5; 50 QUALIFIED WA-REACHABLE DND opt-in CSV + pool refill. co-#1 ammo. ACC 09:00.",
    "PLT-005": EV + " (FRESH re-verify): SIP 5 vars ALL len=0 DID not landed; VOBIZ_CALLER_ID len13 REVOKED; dialer DEAD day5 (mtime Aug31 batch211, proc0). Vendor DID proof/ETA + SIP swap + restart (WA flip already LIVE). ACC 09:00.",
    "SAL-005": EV + " (FRESH): WA msg-id=0; genuine inbound 1258806323 warm + reachable-only UPI close once ENG-004+HNT-005 land; DID 2nd rail. ACC 08:30.",
    "SUC-004": EV + " (FRESH): Jiya sole Rs1,999 payer churn risk; SMTP+WA proof 0 day3+. DID-independent abhi. ACC 08:00.",
    "GRD-004": EV + " (FRESH): verdicts file - ENG-004 NOT shipped (msgid=0) FAIL, SIP blank, 09-04 date-lock broken, dialer dead day5, rev Jiya sole. ACC 09:30.",
    "OPS-007": EV + " (FRESH): hot-queue 09-04 ABSENT 2nd day date-lock root-cause; WA 0 msgid; dialer dead day5 + cadence. ACC 08:30.",
    "BRD-003": EV + " (FRESH): VPS mirror push abhi + page verify. ACC 10:00.",
}
for t in tasks:
    if t["id"] in touch:
        t["evidence_tail"] = touch[t["id"]]
with open(os.path.join(BASE, "tasks.json"), "w", encoding="utf-8") as f:
    json.dump(tasks, f, ensure_ascii=False, indent=1)
print("tasks.json evidence refreshed")

# ---------- 3) bots.json ----------
with open(os.path.join(BASE, "bots.json"), encoding="utf-8") as f:
    bots = json.load(f)
st = {
    "Pilot": "08:20 IST Sep4 (FRESH LIVE 08:20): VPS UP /health 37a1daf8 healthy uptime12h19m; WA flip=1 PAR auto_sent=true WITH msg-id=0 of 2298, reply_drafts mtime Sep3 17:40 (ENG-004 not shipped); hot-queue 09-04 ABSENT 2nd day; SIP 5 vars len=0 DID not landed (CLI 911171366938 REVOKED), dialer DEAD day5 (proc0), leads/ EMPTY 0; rev Rs1,999 Jiya sole, GAP Rs4,98,001. Bottleneck #1 WA msgid=0 #1b ammo+reachability 0 #2 DID. Fleet 0-ACK ~5d; OWNER-ESC esc_0904_1252 on record.",
    "engineering": "ENG-004 P0: flip=1 par msgid=0/auto_sent=0 - ship sendText+msgid+reachability. #1 gate. ACC 16:00.",
    "platform": "PLT-005 P0: SIP 5 vars len=0 DID not landed, CLI REVOKED, dialer DEAD day5 (proc0). 09:00.",
    "operations": "OPS-007 P1: hot-queue 09-04 ABSENT 2nd day (date-lock root-cause); WA 0 msgid digest. 08:30.",
    "sales": "SAL-005 P0: genuine WA inbound 1258806323 + reachable-only UPI close once ENG+HNT land + DID 2nd rail. 08:30.",
    "hunter": "HNT-005 P0: leads/ EMPTY ammo day5; 50 QUALIFIED WA-REACHABLE DND opt-in CSV. 09:00.",
    "guardian": "GRD-004 P1: verdicts file (ENG not shipped FAIL, SIP blank, 09-04 date-lock, rev-truth). 09:30.",
    "success": "SUC-004 P0: Jiya sole payer SMTP+WA proof day3+. 08:00.",
    "board": "BRD-003 P2: VPS mirror + page live verify Sep4 08:20. 10:00.",
}
for k, v in st.items():
    if k in bots:
        bots[k]["status"] = v
with open(os.path.join(BASE, "bots.json"), "w", encoding="utf-8") as f:
    json.dump(bots, f, ensure_ascii=False, indent=1)
print("bots.json updated")

# ---------- 4) pinned.json ----------
with open(os.path.join(BASE, "pinned.json"), encoding="utf-8") as f:
    pin = json.load(f)
pin["last_updated"] = "2026-09-04T08:20+05:30"
pin["vps_status"] = ("VPS UP /health 37a1daf8 healthy uptime12h19m; containers WA flip=1 PAR auto_sent=true WITH msg-id=0 of 2298, "
                     "reply_drafts mtime Sep3 17:40 (ENG-004 sendText NOT shipped); hot-queue 09-04 ABSENT 2nd day (last 09-03); "
                     "SIP 5 vars len=0 DID not landed (CLI 911171366938 REVOKED), dialer DEAD day5 (proc0), leads/ EMPTY; "
                     "VERIFIED rev Rs1,999 (Jiya INV/0001 SOLE), GAP Rs4,98,001. Bottleneck #1 WA msgid=0 #1b ammo+reachability 0 #2 DID. "
                     "Fleet 0-ACK ~5d; OWNER-ESC esc_0904_1252 filed.")
pin["bottleneck"] = ("#1 WA auto_send 0 msg-id (ENG-004 link-only->sendText not shipped) | "
                     "#1b qualified+WA-reachable lead 0 (HNT-005) | #2 DID not landed->dialer dead (CLI REVOKED) | #3 no close-kit buyer")
pin["pipeline"] = ("reply_drafts 2298 (auto_sent=0, msgid=0); hot-queue 09-04 ABSENT (last 09-03 dirty); dialer 0 connects; "
                   "genuine WA inbound 1258806323 warm; Jiya P0 retention")
pin["action"] = ("08:26 IST gate rebump: ENG-004 ship sendText+msgid+reachability; HNT-005 50 WA-reachable qualified CSV; "
                 "SAL reachable-only->UPI + genuine inbound follow; PLT DID-land+restart; SUC Jiya proof; GRD verdicts; "
                 "OPS 09-04 date-lock digest; BRD mirror. OWNER-ESC esc_0904_1252 already on record; 0 proof = hold.")
with open(os.path.join(BASE, "pinned.json"), "w", encoding="utf-8") as f:
    json.dump(pin, f, ensure_ascii=False, indent=1)
print("pinned.json updated")

# ---------- 5) push mirror to VPS ----------
cmd = [
    "scp", "-o", "StrictHostKeyChecking=no", "-i", "C:/Users/Ratanshila/.ssh/id_rsa",
    BASE + "/tasks.json", BASE + "/bots.json", BASE + "/pinned.json", BASE + "/messages.jsonl",
    "root@72.61.245.204:/opt/leadgen/command_center/data/",
]
r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
print("mirror scp rc:", r.returncode)
if r.stderr:
    print("scp stderr:", r.stderr[-400:])

print("DONE")