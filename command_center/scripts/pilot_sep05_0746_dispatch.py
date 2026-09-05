#!/usr/bin/env python3
"""PILOT 07:46 IST (Sep5 CRON) - REVENUE COMMAND, LIVE-verified 02:16Z.

Fresh live evidence this run (SSH 02:16:10Z = 07:46 IST Sep5):
  - VPS UP /health 200 prod 719dbbd6 uptime6h36m (deploy sha 719dbbd6 live).
  - call_loop.log STILL DEAD day5+ (mtime Aug31 08:39:55Z batch211 ok=0/fail=3
    '911171366938 not owned'; proc0; cron0).
  - SIP 5 vars (HOST/USERNAME/PASSWORD/DID/PROVIDER) ALL len=0 -> DID NOT landed;
    VOBIZ_CALLER_ID len13 (+911...6938) still REVOKED.
  - leads/ count=0 EMPTY -> ammo 0.
  - hot-queue 09-04 CSV+MD present (Sep4 03:30); 09-05 due ~09:00 IST not-yet (expected).
  - WA flip LIVE=1 in container (worker SALES_AUTOPILOT_WHATSAPP_ENABLED len=1).
    reply_drafts auto_sent_true=1 msg_id=1 -> SAL-006 MANUAL proposal (3EB00... sent_manual);
    ENG-004 automation STILL NOT shipped.
  - wa_inbound: only status broadcasts (02:01-02:04Z); NO reply from 197126499872961 (SAL-006).
  - VERIFIED rev Rs1,999 (Jiya INV/0001 SOLE); GAP Rs4,98,001.

Dispatch policy this run: 07:45 IST GHANTI round already fired to all 8 bots 1 min ago
(messages.jsonl fresh). No idle bot, no 24h-stale task. One hoisted REVENUE COMMAND
broadcast + pinned refresh only - no per-bot spam.
"""
import json, os, subprocess

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-05T07:46:00+05:30"

# ---------- 1) messages.jsonl (message_agent channel) ----------
msgs = [
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "REVENUE COMMAND 07:46 IST (Sep5, LIVE 02:16Z): TARGET Rs5,00,000 | VERIFIED Rs1,999 (Jiya INV/0001 SOLE) | GAP Rs4,98,001 | PIPELINE: SAL-006 hot WA lead 197126499872961 proposal+followup SENT reply PENDING; 86 warm UPI deep-links; hot-queue 09-04 43; prospects 2350 | HOT: SAL-006 reply->UPI + ENG-004 sendText unlock + Jiya retention | BOTTLENECK: #1 SAL-006 reply->UPI close | #2 ENG-004 real sendText=0 (auto_sent 1 = manual) | #3 DID0+egress day6 (vendor-gated) | #4 qualified CSV 0 | ACTION: gates 08:30 (PLT/HNT/SUC/ENG/GRD) 09:00 (SAL/BRD) 09:15 (OPS 09-05 verify); hot-queue 09-05 due ~09:00 IST; 0 proof 09:30 = REASSIGN+OWNER-ESC (esc_0904_0702 on record). pelican"},
]

with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("appended", len(msgs), "message")

# ---------- 2) pinned.json refresh (last probe timestamp honest) ----------
with open(os.path.join(BASE, "pinned.json"), encoding="utf-8") as f:
    pin = json.load(f)
pin["last_updated"] = TS
pin["vps_status"] = ("VPS UP /health 200 prod 719dbbd6 uptime6h36m (02:16Z probe). "
                     "call_loop DEAD day5+ (DID0 egress day6); leads/ EMPTY; hot-queue 09-05 due ~09:00 IST; "
                     "reply_drafts auto_sent 1 = SAL-006 manual (ENG-004 unshipped); wa_inbound status-only, "
                     "SAL-006 reply PENDING. rev Rs1,999 GAP Rs4,98,001.")
pin["bottleneck"] = ("#1 SAL-006 reply->UPI close | #2 ENG-004 real sendText=0 (auto_sent 1 = manual) | "
                     "#3 DID0+CLI REVOKED+egress day6 (vendor-gated) | #4 qualified CSV ammo 0")
pin["pipeline"] = ("SAL-006 proposal+followup SENT reply PENDING + 86 warm UPI deep-links + "
                   "hot-queue 09-04 43 (09-05 due 09:00 IST) + prospects 2350")
pin["action"] = ("07:46 REVENUE COMMAND broadcast; gates 08:30 (PLT/HNT/SUC/ENG/GRD) 09:00 (SAL/BRD) "
                 "09:15 (OPS 09-05 verify); 0 proof 09:30 = REASSIGN+OWNER-ESC")
with open(os.path.join(BASE, "pinned.json"), "w", encoding="utf-8") as f:
    json.dump(pin, f, ensure_ascii=False, indent=1)
print("pinned.json refreshed")

# ---------- 3) bots.json Pilot line refresh ----------
with open(os.path.join(BASE, "bots.json"), encoding="utf-8") as f:
    bots = json.load(f)
if "Pilot" in bots:
    bots["Pilot"]["status"] = ("07:46 IST Sep5 (LIVE 02:16Z): /health 200 prod 719dbbd6; SAL-006 proposal+followup SENT reply PENDING; "
                               "call_loop DEAD day5+ (DID0 egress day6); ENG-004 unshipped (auto_sent 1 = manual); "
                               "hot-queue 09-05 due 09:00 IST; rev Rs1,999 GAP Rs4,98,001. Gates 08:30/09:00/09:15; 0 proof 09:30 = REASSIGN+ESC.")
with open(os.path.join(BASE, "bots.json"), "w", encoding="utf-8") as f:
    json.dump(bots, f, ensure_ascii=False, indent=1)
print("bots.json Pilot refreshed")

# ---------- 4) push mirror to VPS ----------
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