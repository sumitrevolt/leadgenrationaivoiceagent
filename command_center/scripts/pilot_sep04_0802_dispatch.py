#!/usr/bin/env python3
"""PILOT 08:02 IST (Sep4 CRON) — decisive GHANTI re-issue on #1 executable blocker + stand-notes refresh.

Live re-verify 08:01 IST THIS run (independent): state FROZEN day5+ vs 08:00 esc.
  - /health 37a1daf8 healthy uptime12h0m env=production.
  - WA flip LIVE=1 par msg_id=0 / auto_sent true=0 of 2298 -> ENG-004 sendText NEVER shipped (#1 blocker).
  - SIP 5 vars EMPTY (DID not landed), VOBIZ_CALLER_ID len13 REVOKED, call_loop mtime Aug31 08:39:55Z batch211 -> dialer DEAD day5. leads/ ABSENT ammo 0. hot-queue last 09-03 (09-04 ABSENT 2nd day).
  - VERIFIED rev Rs1,999 (Jiya sole INV/2026-27/0001); GAP Rs4,98,001.
  - Fleet 0-ACK ~5d; 08:00 OWNER-ESC on record.

Action: re-issue DECISIVE GHANTI to ENGINEERING (ENG-004) — single highest-value executable action
(WA sendText firing = pehla real UPI close-rail). Stand-notes for other owners refreshed. Mirror pushed.
"""
import json, os, subprocess, datetime

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).strftime("%Y-%m-%dT%H:%M:%S+05:30")

EV = ("PILOT 08:02 IST Sep4 (LIVE 08:01 SSH): /health 37a1daf8 healthy uptime12h0m prod; "
      "WA flip=1 par msg_id=0/auto_sent TRUE=0 of 2298 (ENG-004 sendText NEVER fired — #1 blocker); "
      "SIP 5 vars EMPTY DID not landed (VOBIZ_CALLER_ID len13 REVOKED, dialer DEAD day5 mtime Aug31 batch211); "
      "leads/ ABSENT ammo 0; hot-queue 09-04 ABSENT 2nd day; rev Rs1,999 Jiya sole; GAP Rs4,98,001. "
      "Fleet 0-ACK ~5d; 08:00 OWNER-ESC on record.")

with open(os.path.join(BASE, "tasks.json"), encoding="utf-8") as f:
    tasks = json.load(f)

for t in tasks:
    if t["id"] == "ENG-004":
        # DECISIVE GHANTI re-issue — #1 executable revenue path
        t["status"] = "RUNNING"
        t["updated_at"] = TS
        t["evidence_tail"] = EV
        t["notes"] = ("GHANTI 08:02 IST (Sep4 CRON) DECISIVE: WA flip LIVE=1 BOTH containers par auto_sent TRUE=0/msg_id=0 of 2298 — "
                      "sendText kisi bhi tarah fire nahi hua. YEHI #1 executable close-path #1 blocker hai. "
                      "FIX auto_outreach -> real WAHA sendText (session:'default'+X-Api-Key, capture msg-id). "
                      "HARD ACC 16:00 IST: >=1 reply_drafts row auto_sent=true WITH msg-id + commit sha. "
                      "0-proof = task to GUARDIAN for reassign + OWNER-ESC.")
    elif t["id"] in {"PLT-005","HNT-005","SUC-004","SAL-005","GRD-004","OPS-007","BRD-003"}:
        t["updated_at"] = TS
        t["evidence_tail"] = EV
        # keep status as-is (RUNNING/BLOCKED); re-pin standing gate
        t["notes"] = (t.get("notes","") + f" || 08:02 IST GAte STANDS: {t['id']} owner — deliver ACC, 0-proof = OWNER-ESC on record (08:00).").strip()

with open(os.path.join(BASE, "tasks.json"), "w", encoding="utf-8") as f:
    json.dump(tasks, f, ensure_ascii=False, indent=1)
print("tasks.json updated (ENG-004 decisive GHANTI + stand-notes)")

with open(os.path.join(BASE, "bots.json"), encoding="utf-8") as f:
    bots = json.load(f)
for k, v in bots.items():
    if isinstance(v, dict) and "status" in v:
        v["status"] = v["status"].split("|")[0].strip() + f" | {EV}"
with open(os.path.join(BASE, "bots.json"), "w", encoding="utf-8") as f:
    json.dump(bots, f, ensure_ascii=False, indent=1)
print("bots.json refreshed")

with open(os.path.join(BASE, "pinned.json"), encoding="utf-8") as f:
    pin = json.load(f)
pin["last_updated"] = TS
pin["vps_status"] = "VPS UP leadgen_app healthy uptime12h; WA flip=1 PAR auto_sent WITH msg-id=0 (ENG-004 sendText never fired); SIP EMPTY DID not landed dialer DEAD day5; leads 0; hot-queue 09-04 ABSENT; rev Rs1,999 (Jiya sole) GAP Rs4,98,001."
pin["bottleneck"] = "#1 WA msg-id=0 (ENG-004 sendText) | #1b lead 0 (HNT-005) | #2 DID->dialer dead (PLT-005) | Jiya churn P0 (SUC-004)"
pin["pipeline"] = "reply_drafts 2298 auto_sent=0/msgid=0; hot-queue 09-04 ABSENT; dialer 0 connects; genuine WA warm inbound; Jiya P0"
pin["action"] = "08:02 DECISIVE GHANTI ENG-004 (16:00 UPI-close gate). Stand gates: SUC-004 08:00 | SAL-005/OPS-007 08:30 | PLT-005/HNT-005 09:00 | GRD-004 09:30. Fleet 0-ACK ~5d; 08:00 OWNER-ESC filed."
with open(os.path.join(BASE, "pinned.json"), "w", encoding="utf-8") as f:
    json.dump(pin, f, ensure_ascii=False, indent=1)
print("pinned.json updated")

cmd = ["scp","-o","StrictHostKeyChecking=no","-i","C:/Users/Ratanshila/.ssh/id_rsa",
       f"{BASE}/tasks.json", f"{BASE}/bots.json", f"{BASE}/pinned.json",
       "root@72.61.245.204:/opt/leadgen/command_center/data/"]
r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
print("mirror scp rc:", r.returncode)
if r.stderr:
    print("scp stderr:", r.stderr[-300:])
print("DONE")
