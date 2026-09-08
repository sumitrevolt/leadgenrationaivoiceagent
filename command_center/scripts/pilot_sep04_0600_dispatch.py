#!/usr/bin/env python3
"""PILOT 06:00 IST (Sep4 CRON) — REVENUE COMMAND + bottleneck re-route, LIVE-verified 05:58 IST.

LIVE VERIFIED 05:58 IST (00:28 UTC) of VPS:
  - /health 200 production (auth-gated 308 on direct) — VPS UP.
  - WA rail STILL ZERO-DELIVERY despite restart: containers restarted 2026-09-03 14:30:40Z
    (WA flip LIVE=1 in BOTH worker+app) BUT reply_drafts auto_sent=true = 0 AND msg_id=0
    of 2298 totals. => ENG-004 link-only->sendText fix NOT shipped yet; #1 close-rail STILL dead.
  - hot-queue 09-04 NOT generated (last file 09-03; date-lock still broken).
  - dialer STILL DEAD day5+: SIP 5 vars EMPTY (DID not landed), VOBIZ_CALLER_ID +911****6938 revoked,
    call_loop mtime Aug31 08:39:55Z proc0 cron0, leads/ empty (ammo 0).
  - Revenue VERIFIED Rs1,999 (Jiya INV/2026-27/0001 SOLE); GAP Rs4,98,001.
  - Fleet ACK 0 ~51h (0 proof, 0 ACK across Sep3/Sep4).

BOTTLENECK ladder: #1 WA rail zero-msgid (ENG-004) => no genuine send => no UPI => no ledger.
#1b leads ammo 0 (HNT-005). #2 DID not landed (PLT-005). #3 Jiya churn (SUC-004).
One TASK-ID/bot/run honoured (rebump existing; no new IDs).
"""
import json, os, subprocess

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-04T06:00:00+05:30"

# ---------- 1) messages.jsonl (message_agent channel) ----------
msgs = [
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "🎯 REVENUE COMMAND 06:00 IST (Sep4): TARGET ₹5,00,000 | VERIFIED ₹1,999 (Jiya INV/0001 SOLE) | GAP ₹4,98,001 | PIPELINE: WA rail 0 msg-id/0 auto_sent of 2298 (link-only day5+, containers ALREADY restarted Sep3 14:30Z flip=1 -> code-fix missing); hot-queue 09-03 last (09-04 NOT gen); dialer DEAD day5 (SIP empty, CLI revoked); leads 0. | HOT: genuine WA msg-id -> reply -> UPI. | BOTTLENECK: #1 ENG-004 WA sendText code-fix (0 msg-id = 0 closes) #1b HNT-005 ammo 0 #2 PLT-005 DID #3 SUC-004 Jiya churn. | ACTION: ENG-004 ship sendText+msgid+reachability; HNT-005 50 qualified CSV; PLT DID land+restart; SAL reachable-only UPI close; SUC Jiya proof; GRD verdicts; OPS digest; BRD mirror. NEXT: msg-id -> genuine reply -> UPI -> ledger INV. FLEET 0-ACK ~51h -> next gate OWNER-ESC. 🐦"},
    {"ts": TS, "from": "PILOT", "to": "engineering", "task_id": "ENG-004", "type": "ESCALATION", "priority": "P0",
     "msg": "ENG-004 06:00 IST (LIVE 05:58): WA flip LIVE=1 (containers restarted Sep3 14:30Z) PAR auto_sent true=0 AND msg_id=0 of 2298 — link-only path STILL sends nothing. SHIP the real WAHA sendText wiring (link->sendText, msgid capture, e164 reachability, SKIP-not-FAIL). This is THE #1 close rail (dialer dead). Commit sha + first msg-id proof. 07:00. 🐦"},
    {"ts": TS, "from": "PILOT", "to": "hunter", "task_id": "HNT-005", "type": "ESCALATION", "priority": "P0",
     "msg": "HNT-005 06:00 IST P0 (LIVE 05:58): leads/ EMPTY ammo day5+. Deliver 50 QUALIFIED e164-valid (91XXXXXXXXXX) WA-reachable DND-scrubbed opt-in business-owner mobile CSV to /opt/leadgen/data/leads/. Co-#1 ammo for once sendText ships. 07:00. 🐦"},
    {"ts": TS, "from": "PILOT", "to": "platform", "task_id": "PLT-005", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "PLT-005 06:00 IST (LIVE 05:58): SIP_USERNAME/SIP_DID BLANK — DID STILL not landed; VOBIZ_CALLER_ID +911****6938 revoked; dialer DEAD day5 (mtime Aug31). Vendor DID proof/ETA + SIP swap + restart + first post-DID dial batch. 07:00. 🐦"},
    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "SAL-005", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "SAL-005 06:00 IST: WA rail 0 msg-id (code-fix pending) — do NOT blast raw. Once ENG-004 ships + HNT-005 reachable CSV, sendText reachable-only -> genuine reply -> UPI close -> ledger INV. Vendor DID 2nd rail (Jio Call Soft/RMS). 07:00 msg-id. 🐦"},
    {"ts": TS, "from": "PILOT", "to": "success", "task_id": "SUC-004", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "SUC-004 06:00 IST: Jiya = SOLE ₹1,999 payer — churn = REVENUE ZERO. SMTP SENT artifact + WA follow-up + retention offer. DID-independent, 0 proof day3+. 07:00. 🐦"},
    {"ts": TS, "from": "PILOT", "to": "guardian", "task_id": "GRD-004", "type": "TASK_REBUMP", "priority": "P1",
     "msg": "GRD-004 06:00 IST (LIVE 05:58): NEW verdict — containers restarted Sep3 14:30Z flip=1 PAR auto_sent=0 AND msg_id=0 = ENG-004 not shipped (PASS/FAIL code-fix). + SIP blank, dialer dead, leads 0, health 200. Independent PASS/FAIL verdicts file. Fleet 0-ACK ~51h. 07:00. 🐦"},
    {"ts": TS, "from": "PILOT", "to": "operations", "task_id": "OPS-007", "type": "TASK_REBUMP", "priority": "P1",
     "msg": "OPS-007 06:00 IST digest: WA 0 msg-id / auto_sent 0; hot-queue 09-04 NOT gen (date-lock broken, last 09-03); dialer DEAD day5 + restart cadence post-DID; watchdog. 07:00. 🐦"},
    {"ts": TS, "from": "PILOT", "to": "board", "task_id": "BRD-003", "type": "TASK_REBUMP", "priority": "P2",
     "msg": "BRD-003 06:00 IST: visualization ONLY — VPS mirror of Sep4 06:00 state + /app/bot-command-center page live verify. PILOT mirror push abhi. 07:00. 🐦"},
]

with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("appended", len(msgs), "messages")

# ---------- 2) tasks.json evidence update ----------
with open(os.path.join(BASE, "tasks.json"), encoding="utf-8") as f:
    tasks = json.load(f)

EV = "PILOT 06:00 IST Sep4 (LIVE 05:58)"
updates = {
    "PLT-005": ("BLOCKED", f"{EV}: SIP 5 vars EMPTY DID not landed, VOBIZ_CALLER_ID +911****6938 revoked, dialer DEAD day5 (mtime Aug31 proc0). Vendor DID proof/ETA + SIP swap + restart + first post-DID dial. 07:00."),
    "ENG-004": ("RUNNING", f"{EV}: containers restarted Sep3 14:30Z flip=1 PAR auto_sent=0 AND msg_id=0 of 2298 (link-only still sends nothing). Ship sendText+msgid+reachability. #1 close rail. 07:00."),
    "SAL-005": ("RUNNING", f"{EV}: WA rail 0 msg-id — no raw blast; reachable-only close once ENG-004+HNT-005 land + DID 2nd rail. 07:00."),
    "SUC-004": ("RUNNING", f"{EV}: Jiya sole ₹1,999 payer churn risk; SMTP+WA proof 0 day3+. 07:00."),
    "HNT-005": ("BLOCKED", f"{EV}: leads/ EMPTY ammo day5; 50 QUALIFIED e164-valid WA-reachable DND opt-in CSV. co-#1 ammo. 07:00."),
    "GRD-004": ("RUNNING", f"{EV}: NEW verdict — restart+flip done PAR msgid=0/auto_sent=0 = ENG not shipped (PASS/FAIL). + SIP blank + health 200. verdicts 07:00."),
    "OPS-007": ("RUNNING", f"{EV}: WA 0 msg-id; hot-queue 09-04 NOT gen (date-lock); dialer DEAD day5 + restart cadence; watchdog. 07:00 digest."),
    "BRD-003": ("RUNNING", f"{EV}: VPS mirror + page live verify of Sep4 06:00 state. 07:00."),
}
for t in tasks:
    if t["id"] in updates:
        st, tail = updates[t["id"]]
        t["status"] = st
        t["updated_at"] = TS
        t["evidence_tail"] = tail
with open(os.path.join(BASE, "tasks.json"), "w", encoding="utf-8") as f:
    json.dump(tasks, f, ensure_ascii=False, indent=1)
print("tasks.json updated")

# ---------- 3) bots.json ----------
with open(os.path.join(BASE, "bots.json"), encoding="utf-8") as f:
    bots = json.load(f)
st = {
    "Pilot": f"06:00 IST Sep4 (FRESH): /health 200 UP; containers restarted Sep3 14:30Z WA flip=1 par auto_sent 0 AND msg_id 0 of 2298 (link-only day5+ — ENG-004 NOT shipped); hot-queue 09-04 NOT gen; SIP 5 vars EMPTY DID not landed; dialer DEAD day5+ (leads 0); rev Rs1,999 Jiya sole; GAP Rs4,98,001. Bottleneck #1 WA msgid=0 #1b ammo 0 #2 DID. Fleet 0-ACK ~51h; 07:00 OWNER-ESC gate.",
    "engineering": "ENG-004 P0: containers flip=1 par msgid=0/auto_sent=0 — ship sendText+msgid. #1 gate. 07:00.",
    "platform": "PLT-005 P0: SIP blank DID not landed, dialer DEAD day5. 07:00.",
    "operations": "OPS-007 P1: hot-queue 09-04 NOT gen (date-lock); WA 0 msgid digest. 07:00.",
    "sales": "SAL-005 P0: no raw blast; reachable-only→UPI once ENG+HNT land + DID 2nd rail. 07:00.",
    "hunter": "HNT-005 P0: leads/ EMPTY ammo day5; 50 QUALIFIED WA-reachable DND opt-in CSV. 07:00.",
    "guardian": "GRD-004 P1: +verdict restart+flip done par msgid=0 = ENG not shipped. verdicts 07:00.",
    "success": "SUC-004 P0: Jiya sole payer SMTP+WA proof day3+. 07:00.",
    "board": "BRD-003 P2: VPS mirror + page live verify Sep4 06:00. 07:00.",
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
pin["last_updated"] = "2026-09-04T06:00+05:30"
pin["vps_status"] = ("VPS 200 production UP; containers restarted Sep3 14:30Z WA flip=1 PAR auto_sent=0 AND msg_id=0 of 2298 "
                     "(link-only day5+, ENG-004 NOT shipped); hot-queue 09-04 NOT gen; SIP empty DID not landed, dialer DEAD day5, "
                     "leads 0; VERIFIED rev ₹1,999 (Jiya INV/0001 SOLE), GAP ₹4,98,001. Bottleneck #1 WA msgid=0 #1b ammo 0 #2 DID. "
                     "Fleet 0-ACK ~51h -> 07:00 OWNER-ESC gate.")
pin["bottleneck"] = "#1 WA auto_send 0 msg-id (ENG-004 link-only->sendText NOT shipped) | #1b qualified+WA-reachable lead 0 | #2 DID not landed->dialer dead | #3 no close-kit buyer"
pin["pipeline"] = "reply_drafts 2298 (auto_sent=0, msgid=0, non-reachable list); hot-queue 09-03 44 dirty; dialer 0 connects; Jiya P0 retention"
pin["action"] = "07:00 IST: ENG-004 ship sendText+msgid+reachability; HNT-005 50 qualified CSV; SAL reachable-only→UPI; PLT DID-land+restart; SUC Jiya proof; GRD verdicts; OPS digest; BRD mirror. 0 proof = OWNER escalation."
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
