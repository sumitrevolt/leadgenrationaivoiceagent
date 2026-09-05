#!/usr/bin/env python3
"""PILOT 06:40 IST (Sep4 CRON) — REVENUE COMMAND refresh + final-gate reconfirm, LIVE-verified 06:40 IST.

State unchanged since 06:36 run (4 min earlier, all 8 bots have fresh 07:30 gates):
  - VPS UP /health 37a1daf8 healthy uptime 10h39m.
  - WA flip LIVE=1 in BOTH containers; but auto_sent true=0 AND msg_id=0 of 2298
    (link-only path sends nothing) — ENG-004 sendText fix NOT shipped = #1 close rail.
  - hot-queue 09-04 ABSENT (date-lock broken 2nd day, last 09-03).
  - dialer DEAD day5+: SIP 5 vars ALL EMPTY (DID not landed), VOBIZ_CALLER_ID 911171366938 REVOKED
    (log: "not owned by this account"), call_loop mtime Aug31 08:39:55Z batch211 proc0 cron0.
  - leads/ EMPTY (ammo 0). Revenue VERIFIED ₹1,999 (Jiya INV/2026-27/0001 SOLE); GAP ₹4,98,001.
  - Fleet 0-ACK ~52h. This is the last cadence before 07:30 OWNER-ESC gate.

One TASK-ID/bot/run, token-lean. Honour existing task IDs; no new IDs.
"""
import json, os, subprocess

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-04T06:40:00+05:30"

# ---------- 1) messages.jsonl (message_agent channel) ----------
msgs = [
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "🎯 REVENUE COMMAND 06:40 IST (Sep4, LIVE 06:40): TARGET ₹5,00,000 | VERIFIED ₹1,999 (Jiya INV/0001 SOLE) | GAP ₹4,98,001 | PIPELINE: WA rail 0 msg-id/0 auto_sent of 2298 (link-only, ENG-004 not shipped); hot-queue 09-04 ABSENT (date-lock 2nd day, last 09-03); dialer DEAD day5 (SIP empty, CLI 911171366938 REVOKED); leads 0 ammo. | HOT: genuine WA inbound 1258806323 warm signal. | BOTTLENECK: #1 ENG-004 WA sendText msgid=0 #1b HNT-005 ammo+reachability 0 #2 PLT-005 DID #3 SUC-004 Jiya churn. | ACTION: sab 07:30 gates ke hisaab se chalo — ENG ship sendText+msgid+reachability; HNT 50 WA-reachable CSV; PLT DID-land+restart; SAL reachable-only UPI + genuine inbound; SUC Jiya proof; GRD verdicts; OPS 09-04 date-lock digest; BRD mirror. 0 proof incl 07:30 = OWNER-ESC. 🐦"},
]

with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("appended", len(msgs), "messages")

# ---------- 2) tasks.json latest-evidence timestamp (no status churn, no spam) ----------
with open(os.path.join(BASE, "tasks.json"), encoding="utf-8") as f:
    tasks = json.load(f)

EV = "PILOT 06:40 IST Sep4 (LIVE 06:40)"
touch = {
    "ENG-004": f"{EV}: WA flip=1 PAR auto_sent=0 AND msgid=0 of 2298 (link-only sends NOTHING). Ship sendText+msgid+reachability. #1 close rail. 07:30.",
    "HNT-005": f"{EV}: leads/ EMPTY ammo day5; 50 QUALIFIED WA-REACHABLE DND opt-in CSV (reachability critical). co-#1 ammo. 07:30.",
    "PLT-005": f"{EV}: SIP 5 vars ALL EMPTY — DID not landed; CLI 911171366938 REVOKED, dialer DEAD day5. Vendor proof/ETA + SIP swap + restart + dial. 07:30.",
    "SAL-005": f"{EV}: WA rail 0 msg-id; GENUINE WA inbound 1258806323 + reachable-only UPI close once ENG-004+HNT-005 land; DID 2nd rail. 07:30.",
    "SUC-004": f"{EV}: Jiya sole ₹1,999 payer churn risk; SMTP+WA proof 0 day3+. DID-independent abhi karo. 07:30.",
    "GRD-004": f"{EV}: verdicts — flip=1 par msgid/auto_sent=0 = ENG not shipped (FAIL); SIP blank; 09-04 date-lock broken; rev Jiya sole. 07:30.",
    "OPS-007": f"{EV}: hot-queue 09-04 ABSENT 2nd day date-lock root-cause; WA 0 msgid; dialer dead day5 + cadence + watchdog. 07:30 digest.",
    "BRD-003": f"{EV}: VPS mirror Sep4 06:40 + page verify. 07:30.",
}
for t in tasks:
    if t["id"] in touch:
        t["evidence_tail"] = touch[t["id"]]  # keep status as-is; only refresh evidence
with open(os.path.join(BASE, "tasks.json"), "w", encoding="utf-8") as f:
    json.dump(tasks, f, ensure_ascii=False, indent=1)
print("tasks.json evidence refreshed")

# ---------- 3) bots.json ----------
with open(os.path.join(BASE, "bots.json"), encoding="utf-8") as f:
    bots = json.load(f)
st = {
    "Pilot": "06:40 IST Sep4 (FRESH): VPS UP /health 37a1daf8 healthy uptime10h39m; WA flip=1 PAR auto_sent 0 + msgid 0 of 2298 (ENG-004 not shipped); hot-queue 09-04 ABSENT; SIP 5 vars EMPTY DID not landed (CLI 911171366938 REVOKED), dialer DEAD day5+, leads 0; rev ₹1,999 Jiya sole, GAP ₹4,98,001. Bottleneck #1 WA msgid=0 #1b ammo+reachability 0 #2 DID. Fleet 0-ACK ~52h -> 07:30 OWNER-ESC gate.",
    "engineering": "ENG-004 P0: flip=1 par msgid=0/auto_sent=0 — ship sendText+msgid+reachability. #1 gate. 07:30.",
    "platform": "PLT-005 P0: SIP 5 vars EMPTY DID not landed, CLI REVOKED, dialer DEAD day5. 07:30.",
    "operations": "OPS-007 P1: hot-queue 09-04 ABSENT 2nd day (date-lock root-cause); WA 0 msgid digest. 07:30.",
    "sales": "SAL-005 P0: genuine WA inbound 1258806323 + reachable-only UPI close once ENG+HNT land + DID 2nd rail. 07:30.",
    "hunter": "HNT-005 P0: leads/ EMPTY ammo day5; 50 QUALIFIED WA-REACHABLE DND opt-in CSV. 07:30.",
    "guardian": "GRD-004 P1: verdicts file (ENG not shipped FAIL, SIP blank, 09-04 date-lock, rev-truth). 07:30.",
    "success": "SUC-004 P0: Jiya sole payer SMTP+WA proof day3+. 07:30.",
    "board": "BRD-003 P2: VPS mirror + page live verify Sep4 06:40. 07:30.",
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
pin["last_updated"] = "2026-09-04T06:40+05:30"
pin["vps_status"] = ("VPS UP /health 37a1daf8 healthy uptime10h39m; containers WA flip=1 PAR auto_sent=0 + msgid=0 of 2298 "
                     "(link-only day5+, ENG-004 not shipped); hot-queue 09-04 ABSENT (date-lock 2nd day, last 09-03); "
                     "SIP 5 vars EMPTY DID not landed (CLI 911171366938 REVOKED), dialer DEAD day5, leads 0; "
                     "VERIFIED rev ₹1,999 (Jiya INV/0001 SOLE), GAP ₹4,98,001. Bottleneck #1 WA msgid=0 #1b ammo+reachability 0 #2 DID. "
                     "Fleet 0-ACK ~52h -> 07:30 OWNER-ESC gate.")
pin["bottleneck"] = "#1 WA auto_send 0 msg-id (ENG-004 link-only->sendText not shipped) | #1b qualified+WA-reachable lead 0 (HNT-005) | #2 DID not landed->dialer dead (CLI REVOKED) | #3 no close-kit buyer"
pin["pipeline"] = "reply_drafts 2298 (auto_sent=0, msgid=0); hot-queue 09-04 ABSENT (last 09-03 dirty); dialer 0 connects; genuine WA inbound 1258806323 warm; Jiya P0 retention"
pin["action"] = "07:30 IST: ENG-004 ship sendText+msgid+reachability; HNT-005 50 WA-reachable qualified CSV; SAL reachable-only->UPI + genuine inbound follow; PLT DID-land+restart; SUC Jiya proof; GRD verdicts; OPS 09-04 date-lock digest; BRD mirror. 0 proof = OWNER escalation."
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
