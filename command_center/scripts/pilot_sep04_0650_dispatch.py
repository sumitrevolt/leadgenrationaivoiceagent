#!/usr/bin/env python3
"""PILOT 06:50 IST (Sep4 CRON) — LIVE re-verify + lean evidence refresh.

State UNCHANGED vs 06:40/06:36 runs (all 8 bots already TASK_REBUMP'd with 07:30 gates,
REVENUE_COMMAND sent). NO new dispatch/spam — only timestamp fresh 06:50 live verification
so command center board tracks current proof. Anti-spam: fleet just re-bumped 10min ago.
"""
import json, os, subprocess

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-04T06:50:00+05:30"

# ---------- 1) messages.jsonl: lean REVENUE_COMMAND refresh (no per-bot spam, gates stand) ----------
msg = {
    "ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND",
    "priority": "P0",
    "msg": "🎯 REVENUE COMMAND 06:50 IST (Sep4, LIVE re-verify 06:50 — state frozen vs 06:40): "
           "TARGET ₹5,00,000 | VERIFIED ₹1,999 (Jiya INV/0001 SOLE) | GAP ₹4,98,001 | "
           "PIPELINE: WA rail 0 msg-id/0 auto_sent of 2298 (ENG-004 link-only->sendText NOT shipped) "
           "| hot-queue 09-04 ABSENT 2nd day (date-lock break, last 09-03) | dialer DEAD day5 "
           "(SIP 5 vars EMPTY, CLI 911171366938 REVOKED 'not owned', mtime Aug31 batch211 proc0) "
           "| leads/ EMPTY ammo 0. | HOT: genuine WA inbound 1258806323 warm. | "
           "BOTTLENECK: #1 ENG-004 WA sendText msgid=0 #1b HNT-005 qualified+WA-reachable ammo 0 "
           "#2 PLT-005 DID not landed #3 SAL close-kit buyer 0 #4 SUC-004 Jiya churn. | "
           "ACTION: barriers wahi hain — 07:30 IST gates STAND (all 8 bots re-bumped 06:40). "
           "Fleet 0-ACK ~52h. 07:30 ke baad 0 proof = OWNER-ESC. 🐦",
}
with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    f.write(json.dumps(msg, ensure_ascii=False) + "\n")
print("appended REVENUE_COMMAND refresh")

# ---------- 2) tasks.json evidence_tail timestamp (no status churn) ----------
with open(os.path.join(BASE, "tasks.json"), encoding="utf-8") as f:
    tasks = json.load(f)
EV = "PILOT 06:50 IST Sep4 (LIVE re-verify 06:50: state frozen — WA flip=1 but auto_sent/msgid=0 of 2298, ENG-004 not shipped; hot-queue 09-04 ABSENT 2nd day; SIP 5 vars EMPTY DID not landed, dialer DEAD day5 mtime Aug31 batch211 proc0; leads 0 ammo; rev ₹1,999 Jiya sole GAP ₹4,98,001; fleet 0-ACK ~52h -> 07:30 OWNER-ESC)"

for t in tasks:
    if t["id"] in {"ENG-004","HNT-005","PLT-005","SAL-005","SUC-004","GRD-004","OPS-007","BRD-003"}:
        t["evidence_tail"] = EV
with open(os.path.join(BASE, "tasks.json"), "w", encoding="utf-8") as f:
    json.dump(tasks, f, ensure_ascii=False, indent=1)
print("tasks.json evidence ts refreshed")

# ---------- 3) bots.json ----------
with open(os.path.join(BASE, "bots.json"), encoding="utf-8") as f:
    bots = json.load(f)
st = {
    "Pilot": "06:50 IST Sep4 (LIVE re-verify): VPS UP /health 37a1daf8 healthy uptime10h50m; WA flip=1 PAR auto_sent=0 AND msgid=0 of 2298 (ENG-004 NOT shipped = #1 bottleneck); hot-queue 09-04 ABSENT 2nd day; SIP 5 vars EMPTY DID not landed (CLI 911171366938 REVOKED), dialer DEAD day5, leads 0 ammo; rev ₹1,999 Jiya sole GAP ₹4,98,001. Fleet 0-ACK ~52h -> 07:30 OWNER-ESC. All 8 bots re-bumped 06:40 (gates stand).",
    "engineering": "ENG-004 P0: flip=1 par msgid=0/auto_sent=0 — ship sendText+msgid+reachability. #1 gate 07:30.",
    "platform": "PLT-005 P0: SIP 5 vars EMPTY DID not landed, CLI REVOKED, dialer DEAD day5. vendor proof/ETA 07:30.",
    "operations": "OPS-007 P1: hot-queue 09-04 ABSENT 2nd day date-lock root-cause + restart cadence digest 07:30.",
    "sales": "SAL-005 P0: genuine WA inbound 1258806323 + reachable-only UPI close once ENG/HNT land + DID 2nd rail 07:30.",
    "hunter": "HNT-005 P0: leads/ EMPTY ammo day5; 50 QUALIFIED WA-REACHABLE DND opt-in CSV 07:30.",
    "guardian": "GRD-004 P1: verdicts file (ENG not shipped FAIL, SIP blank, date-lock, rev-truth) 07:30.",
    "success": "SUC-004 P0: Jiya sole payer SMTP+WA proof day3+. DID-independent 07:30.",
    "board": "BRD-003 P2: VPS mirror + page live verify Sep4 06:50. 07:30.",
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
pin["last_updated"] = "2026-09-04T06:50+05:30"
pin["vps_status"] = ("VPS UP /health 37a1daf8 healthy uptime10h50m; containers WA flip=1 PAR auto_sent=0 + msgid=0 of 2298 "
                     "(ENG-004 sendText NOT shipped day5+); hot-queue 09-04 ABSENT (date-lock 2nd day, last 09-03); "
                     "SIP 5 vars EMPTY DID not landed (CLI 911171366938 REVOKED), dialer DEAD day5, leads 0; "
                     "VERIFIED rev ₹1,999 (Jiya INV/0001 SOLE), GAP ₹4,98,001. Fleet 0-ACK ~52h -> 07:30 OWNER-ESC.")
pin["bottleneck"] = "#1 WA auto_send 0 msg-id (ENG-004 link-only->sendText NOT shipped) | #1b qualified+WA-reachable lead 0 (HNT-005) | #2 DID not landed->dialer dead (CLI REVOKED) | #3 no close-kit buyer"
pin["pipeline"] = "reply_drafts 2298 (auto_sent=0, msgid=0); hot-queue 09-04 ABSENT (last 09-03 dirty); dialer 0 connects; genuine WA inbound 1258806323 warm; Jiya P0 retention"
pin["action"] = "07:30 IST gates STAND: ENG-004 ship sendText+msgid+reachability; HNT-005 50 qualified WA-reachable CSV; SAL reachable-only->UPI + genuine inbound; PLT DID-land+restart; SUC Jiya proof; GRD verdicts; OPS 09-04 date-lock; BRD mirror. 0 proof = OWNER-ESC."
with open(os.path.join(BASE, "pinned.json"), "w", encoding="utf-8") as f:
    json.dump(pin, f, ensure_ascii=False, indent=1)
print("pinned.json updated")

# ---------- 5) push mirror to VPS ----------
cmd = [
    "scp", "-o", "StrictHostKeyChecking=no", "-i", "C:/Users/Ratanshila/.ssh/id_rsa",
    f"{BASE}/tasks.json", f"{BASE}/bots.json", f"{BASE}/pinned.json", f"{BASE}/messages.jsonl",
    "root@72.61.245.204:/opt/leadgen/command_center/data/",
]
r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
print("mirror scp rc:", r.returncode)
if r.stderr:
    print("scp stderr:", r.stderr[-400:])

print("DONE")
