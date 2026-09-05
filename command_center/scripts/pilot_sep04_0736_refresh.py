#!/usr/bin/env python3
"""PILOT 07:36 IST (Sep4 CRON) — lean evidence refresh, NO message spam.

Live re-verify 07:36 IST this run (not stale): state UNCHANGED vs 07:21 dispatch.
  - VPS UP, leadgen_app/worker/scheduler Up12h healthy.
  - WA flip LIVE=1 PAR auto_sent=true WITH msg-id = 0 of 2298 (ENG-004 NOT shipped).
  - SIP 5 vars (HOST/USERNAME/PASSWORD/DID/PROVIDER) ALL EMPTY -> DID NOT landed;
    VOBIZ_CALLER_ID len13 REVOKED, call_loop mtime Aug31 08:39:55Z batch211 => dialer DEAD day5.
  - leads/ dir ABSENT => ammo 0.
  - hot-queue last 09-03 03:30; 09-04 ABSENT 2nd day (date-lock).
  - VERIFIED rev Rs1,999 (Jiya sole INV/0001); GAP Rs4,98,001.
  - Fleet 0-ACK ~5d; 07:21 GHANTIs + 07:35 REV-COMMAND already in channel.
NO new GHANTIs appended (nothing changed 15min -> avoid spam). Just touch timestamps + mirror.
"""
import json, os, subprocess

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-04T07:36:00+05:30"
EV = "PILOT 07:36 IST Sep4 (LIVE 07:36, state frozen): leadgen_app Up12h healthy; WA flip=1 par msg-id=0/auto_sent=0 (ENG-004 sendText NEVER shipped); SIP 5 vars EMPTY DID NOT landed (CLI 911171366938 REVOKED, dialer DEAD day5 mtime Aug31 batch211); leads/=0 ammo; hot-queue 09-04 ABSENT 2nd day; rev Rs1,999 Jiya sole; GAP Rs4,98,001. Fleet 0-ACK ~5d; 07:21 GHANTIs + 07:35 REV-COMMAND stand."

# tasks.json — refresh evidence_tail + updated_at (no status churn, no dup messages)
with open(os.path.join(BASE, "tasks.json"), encoding="utf-8") as f:
    tasks = json.load(f)
ids = {"ENG-004","HNT-005","PLT-005","SAL-005","SUC-004","GRD-004","OPS-007","BRD-003"}
for t in tasks:
    if t["id"] in ids:
        t["evidence_tail"] = EV
        t["updated_at"] = TS
with open(os.path.join(BASE, "tasks.json"), "w", encoding="utf-8") as f:
    json.dump(tasks, f, ensure_ascii=False, indent=1)
print("tasks.json refreshed", len(ids), "tasks")

# bots.json
with open(os.path.join(BASE, "bots.json"), encoding="utf-8") as f:
    bots = json.load(f)
for k in bots:
    if isinstance(bots[k], dict) and "status" in bots[k]:
        bots[k]["status"] = bots[k]["status"].split("|")[0].strip() + f" | {EV}"
with open(os.path.join(BASE, "bots.json"), "w", encoding="utf-8") as f:
    json.dump(bots, f, ensure_ascii=False, indent=1)
print("bots.json refreshed")

# pinned.json
with open(os.path.join(BASE, "pinned.json"), encoding="utf-8") as f:
    pin = json.load(f)
pin["last_updated"] = TS
pin["vps_status"] = "VPS UP leadgen_app Up12h healthy; WA flip=1 PAR auto_sent WITH msg-id=0 of 2298 (ENG-004 NOT shipped); SIP 5 vars EMPTY DID not landed (CLI REVOKED) dialer DEAD day5; leads 0; hot-queue 09-04 ABSENT 2nd day; rev Rs1,999 (Jiya sole) GAP Rs4,98,001. Fleet 0-ACK ~5d."
pin["bottleneck"] = "#1 WA msg-id=0 (ENG-004 sendText never fired) | #1b lead 0 (HNT-005) | #2 DID not landed->dialer dead (PLT-005)"
pin["pipeline"] = "reply_drafts 2298 auto_sent=0/msgid=0; hot-queue 09-04 ABSENT; dialer 0 connects; genuine WA inbound 1258806323 warm; Jiya P0"
pin["action"] = "07:21 GHANTIs + 07:35 REV-COMMAND STAND. gates: SUC-004 08:00 | SAL-005/OPS-007 08:30 | PLT-005/HNT-005 09:00 | GRD-004 09:30 | ENG-004 16:00. 0-proof = OWNER-ESC on record."
with open(os.path.join(BASE, "pinned.json"), "w", encoding="utf-8") as f:
    json.dump(pin, f, ensure_ascii=False, indent=1)
print("pinned.json refreshed")

# push mirror to VPS
cmd = ["scp", "-o", "StrictHostKeyChecking=no", "-i", "C:/Users/Ratanshila/.ssh/id_rsa",
       f"{BASE}/tasks.json", f"{BASE}/bots.json", f"{BASE}/pinned.json",
       "root@72.61.245.204:/opt/leadgen/command_center/data/"]
r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
print("mirror scp rc:", r.returncode)
if r.stderr:
    print("scp stderr:", r.stderr[-300:])
print("DONE")
