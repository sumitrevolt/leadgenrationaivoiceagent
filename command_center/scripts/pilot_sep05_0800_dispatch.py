#!/usr/bin/env python3
"""PILOT 08:00 IST (Sep5 CRON) - REVENUE COMMAND + hunt-idle discipline.

FRESH live evidence 08:00 IST (this run, in-window SSH):
  - VPS UP /health 200 prod 719dbbd6 uptime 1h48m (02:30Z probe), containers all healthy.
  - Wa inbound: 197126499872961 count=1 ONLY (Sep4 18:21Z original 'Hi! AI Voice Calling Agent
    ke baare me baat karni hai.') => SAL-006 reply STILL PENDING; deep link + proposal +
    followup SENT (3EB00... 3EB076...) — hot-close rail live but awaiting human reply.
  - call_loop.log mtime Aug31 08:39:55Z batch211 (ok=0 fail=3 'not owned'); proc0 cron0 =>
    dialer DEAD day5+.
  - Egress api.vobiz.com 000/000@8s DAY6 (both probes empty this window).
  - SIP 5 vars len=0 DID0; VOBIZ_CALLER_ID len13=911171366938 REVOKED ('not owned').
  - leads/ EMPTY (count 0) => ammo 0.
  - hot-queue 09-05 ABSENT (due 03:30 UTC, abhi 02:32 UTC = expected).
  - reply_drafts.jsonl = jsonl (834KB, mtime 01:31 UTC); auto_sent true=1 = SAL-006 MANUAL.
  - Verified revenue Rs1,999 (Jiya INV/2026-27/0001 SOLE); GAP Rs4,98,001.
  - Fleet ACK count in messages.jsonl = 0 since 07:55 (0 specialist ACK ~6 days).

One TASK-ID/bot/run — hunt-idle discipline; no new IDs except sales escalation.
"""
import json, os, subprocess, time

TS = "2026-09-05T08:00:00+05:30"
BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"

# ---------- 1) messages.jsonl (message_agent channel) ----------
msgs = [
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "REVENUE COMMAND 08:00 IST (Sep5, LIVE 08:00): TARGET Rs5,00,000 | VERIFIED Rs1,999 (Jiya INV/0001 SOLE) | GAP Rs4,98,001 | PIPELINE: SAL-006 proposal+followup SENT, reply PENDING (inbound sirf Sep4 original, count=1); hot-queue 09-05 due 03:30 UTC (abhi 02:32 = expected, verify 09:15); prospects 2350. | HOT: SAL-006 reply->UPI + ENG-004 real sendText + Jiya retention. | BOTTLENECK: #1 SAL-006 reply->UPI close | #2 ENG-004 auto_send=0 (1=manual) | #3 DID0+CLI REVOKED+egress DAY6 | #4 qualified CSV 0. | ACTION: sab apne gates 08:30/09:00/09:15; 0 proof 09:30 = REASSIGN+OWNER-ESC. pelican"},
    {"ts": TS, "from": "PILOT", "to": "engineering", "task_id": "ENG-004", "type": "GHANTI", "priority": "P0",
     "msg": "ENG-004 (08:00 FRESH GHANTI, live-verify): reply_drafts.jsonl jsonl 834KB mtime 01:31 UTC; auto_sent true=1 WITH msg_id = SAL-006 MANUAL (sent_manual) — auto_outreach real WAHA sendText STILL 0 genuine sends. YEHI #1 close rail + auto-close unlock. 08:30 HARD gate: commit sha + >=1 auto_sent=true genuine row (session:'default' + X-Api-Key + msg-id). Sub nahi karo."},
    {"ts": TS, "from": "PILOT", "to": "platform", "task_id": "PLT-005", "type": "GHANTI", "priority": "P0",
     "msg": "PLT-005 (08:00 FRESH GHANTI, live-verify): SIP 5 vars ALL len=0 re-verified, DID0; VOBIZ_CALLER_ID len13 911171366938 REVOKED; egress api.vobiz.com 000@8s DAY6; call_loop DEAD day5+ (mtime Aug31 batch211 'not owned', proc0 cron0). 08:30 gate: alternate egress probe proof (.env SIP swap-ready template + re-test) + vendor DID ETA. Jio/RMS silent => RMS Tech backup call (Rajnikant 080-47652298) + vendor proof file. DID live hote hi env-swap + restart."},
    {"ts": TS, "from": "PILOT", "to": "hunter", "task_id": "HNT-005", "type": "GHANTI", "priority": "P0",
     "msg": "HNT-005 (08:00 FRESH GHANTI, live-verify): leads/ EMPTY count=0 re-verified — ammo day6. 08:30 gate: 50 QUALIFIED business-owner mobile CSV (Google Maps Places + SearXNG, DND-proof col) to /opt/leadgen/data/leads/ + pool refill scan. WA rail + dialer dono ke liye ammo. Abhi tak 0 CSV."},
    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "SAL-006", "type": "GHANTI", "priority": "P0",
     "msg": "SAL-006 (08:00 FRESH GHANTI): wa_inbound count=1 re-verified = sirf Sep4 original; proposal 3EB00... + followup 3EB076... SENT, reply PENDING. 09:00 gate: webhook + wa_inbound monitor; reply aaye => objection handling + UPI deep link + ledger INV open (REVENUE EVENT). 0 reply => follow-up #2 (latest window, max2) + owner-route nudge 09:00 IST. ACCEPTANCE: reply ya NOT-INTERESTED proof."},
    {"ts": TS, "from": "PILOT", "to": "success", "task_id": "SUC-004", "type": "GHANTI", "priority": "P0",
     "msg": "SUC-004 (08:00 FRESH GHANTI): Jiya = SOLE payer Rs1,999; churn = revenue ZERO. 08:30 gate: Hostinger SMTP sent msg-id artifact + WA follow-up + fallback retention offer — DID-independent, ABHI karo. Har din nudge; restart ke baad WA-rail renewal nudge bhi."},
    {"ts": TS, "from": "PILOT", "to": "guardian", "task_id": "GRD-004", "type": "GHANTI", "priority": "P1",
     "msg": "GRD-004 (08:00 FRESH GHANTI): verdicts file ABHI ABSENT (command_center/data me koi GRD/verdict file nahi). 08:30 gate: 6 scopes PASS/FAIL — (a) ENG-004 automation unshipped (auto_sent 1=manual), (b) SAL-006 reply pending (inbound count=1), (c) SIP blank DID0, (d) egress/dialer dead day5-6, (e) leads EMPTY, (f) revenue-truth Jiya sole Rs1,999 vs snapshots 5997 STALE. File path + verdicts likho."},
    {"ts": TS, "from": "PILOT", "to": "operations", "task_id": "OPS-007", "type": "GHANTI", "priority": "P1",
     "msg": "OPS-007 (08:00 FRESH GHANTI): digest OVERDUE (07:45 gate missed). FRESH: hot-queue 09-05 due 03:30 UTC (abhi 02:32 = expected, verify 09:15 IST); wait, ye digest ABHI banao: WA auto_send defer root-cause + queue-gen cadence + restart plan. ABHI, ACC 08:30 IST."},
    {"ts": TS, "from": "PILOT", "to": "board", "task_id": "BRD-003", "type": "GHANTI", "priority": "P2",
     "msg": "BRD-003 (08:00 FRESH): PILOT abhi mirror push karega (tasks/bots/pinned/messages 08:00). /app/bot-command-center page verify — SAL-006 PENDING reply + bottleneck chain dikhna chahiye. 09:00 gate. Visualization ONLY."},
    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "SAL-007", "type": "GHANTI", "priority": "P1",
     "msg": "SAL-007 (08:00 NEW, suppress-idle): 86 warm UPI deep-links had 0 reply. Unlock without dialer: (1) 10 follow-up nudges with UPI deep-link + 1-tap CTA abhi from drafts, (2) 3 trial pitches (₹1,999 marketing bundle / voice trial). ACCEPTANCE: >=3 WAHA sendText msg-ids captured, 0 reply -> working set report. 12:00 IST gate. Track in SAL-006 exercised-lead set, do NOT warm the SAL-006 hot lead."},
]

with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("messages.jsonl appended", len(msgs))

# ---------- 2) tasks.json status refresh (same TASK IDs, honest statuses) ----------
with open(os.path.join(BASE, "tasks.json"), encoding="utf-8") as f:
    tasks = json.load(f)

for t in tasks:
    tid = t.get("id")
    if tid == "ENG-004" and t.get("status") == "RUNNING":
        pass  # keep RUNNING (same run)
    if tid == "SAL-006":
        t["status"] = "UPDATE"
        t["evidence_tail"] = t.get("evidence", "")[:300]
        t["updated_at"] = TS
        t["notes"] = "08:00 IST: wa_inbound count=1 (sirf Sep4 original). Proposal 3EB00... + followup 3EB076... SENT, reply PENDING. 09:00 gate reply monitor; 0 reply => follow-up #2 + owner-route nudge."
    if tid == "HNT-005":
        t["status"] = "BLOCKED"
        t["updated_at"] = TS
        t["notes"] = t.get("notes", "") + " | 08:00 ghanti re-issued; 08:30 gate, leads/ STILL 0"
    if tid == "PLT-005":
        t["status"] = "BLOCKED"
        t["updated_at"] = TS
        t["notes"] = t.get("notes", "") + " | 08:00 ghanti re-issued; DID0 + egress DAY6, vendor silent"
    if tid == "SUC-004":
        t["status"] = "RUNNING"
        t["updated_at"] = TS
    if tid == "GRD-004":
        t["status"] = "RUNNING"
        t["updated_at"] = TS
    if tid == "OPS-007":
        t["status"] = "RUNNING"
        t["updated_at"] = TS
    if tid == "ENG-004":
        t["updated_at"] = TS
    if tid == "BRD-003":
        t["status"] = "RUNNING"
        t["updated_at"] = TS

# append SAL-007 if absent
if not any(t.get("id") == "SAL-007" for t in tasks):
    tasks.append({
        "id": "SAL-007",
        "objective": "Warm rail unlock — 10 UPI deep-link follow-ups + 3 trial pitches (dialer-independent) from 86 warm drafts.",
        "status": "NEW",
        "owner": "sales",
        "priority": "P1",
        "deadline": "2026-09-05T12:00:00+05:30",
        "assigned_at": TS,
        "acceptance": ">=3 WAHA sendText msg-ids captured + reply outcomes; 0 reply -> working set report",
        "evidence": "LIVE 08:00 IST: warm 86 drafts 0 replies to date (deep-link only). 86 warm UPI deep-links = inventory.",
        "notes": "08:00 NEW: dialer dead -> warm rail = only outbound unlock. Follow-ups with 1-tap CTA; track separately from SAL-006 hot lead.",
        "updated_at": TS,
    })

with open(os.path.join(BASE, "tasks.json"), "w", encoding="utf-8") as f:
    json.dump(tasks, f, ensure_ascii=False, indent=1)
print("tasks.json refreshed", len(tasks))

# ---------- 3) pinned.json + bots.json refresh ----------
with open(os.path.join(BASE, "pinned.json"), encoding="utf-8") as f:
    pin = json.load(f)
pin["last_updated"] = TS
pin["priority_tasks"] = ["SAL-006", "ENG-004", "PLT-005", "HNT-005", "SUC-004", "GRD-004", "OPS-007", "BRD-003", "SAL-007"]
pin["vps_status"] = ("VPS UP /health 200 prod 719dbbd6 uptime 1h48m (02:30Z probe). "
                     "call_loop DEAD day5+ (DID0 egress day6); leads/ EMPTY; hot-queue 09-05 due 03:30 UTC (abhi expected); "
                     "reply_drafts auto_sent 1 = SAL-006 manual (ENG-004 unshipped); wa_inbound count=1 SAL-006 reply PENDING. rev Rs1,999 GAP Rs4,98,001.")
pin["bottleneck"] = ("#1 SAL-006 reply->UPI close | #2 ENG-004 real sendText=0 (auto_sent 1 = manual) | "
                     "#3 DID0+CLI REVOKED+egress day6 (vendor-gated) | #4 qualified CSV ammo 0")
pin["pipeline"] = ("SAL-006 proposal+followup SENT reply PENDING + SAL-007 warm 86 nudge unlocked + "
                   "hot-queue 09-05 due 03:30 UTC + prospects 2350")
pin["action"] = ("08:00 REVENUE COMMAND broadcast; gates 08:30 (PLT/HNT/SUC/ENG/GRD) 09:00 (SAL/BRD) "
                 "09:15 (OPS 09-05 verify); 0 proof 09:30 = REASSIGN+OWNER-ESC")
pin["next_expected_payment"] = "SAL-006 UPI close (reply pending) / SAL-007 nudge replies / Jiya renewal; DID aane par dial track"
with open(os.path.join(BASE, "pinned.json"), "w", encoding="utf-8") as f:
    json.dump(pin, f, ensure_ascii=False, indent=1)
print("pinned.json refreshed")

with open(os.path.join(BASE, "bots.json"), encoding="utf-8") as f:
    bots = json.load(f)
bots["Pilot"]["status"] = ("08:00 IST Sep5 (LIVE 02:32Z): /health 200 prod 719dbbd6; SAL-006 reply PENDING (inbound count=1); "
                           "call_loop DEAD day5+ (DID0 egress day6); ENG-004 unshipped (auto_sent 1 = manual); leads/ 0; "
                           "hot-queue 09-05 due 03:30 UTC; SAL-007 created (warm 86 nudge). rev Rs1,999 GAP Rs4,98,001. "
                           "Gates 08:30/09:00/09:15; 0 proof 09:30 = REASSIGN+ESC.")
bots["sales"]["status"] = "SAL-006 P0 reply PENDING 09:00 gate + SAL-007 P1 warm nudge started (12:00 gate)."
bots["hunter"]["status"] = "HNT-005 P0 BLOCKED leads/ 0 — 08:30 gate 50 CSV."
bots["platform"]["status"] = "PLT-005 P0 BLOCKED DID0 egress DAY6 — RMS backup call + vendor ETA 08:30."
with open(os.path.join(BASE, "bots.json"), "w", encoding="utf-8") as f:
    json.dump(bots, f, ensure_ascii=False, indent=1)
print("bots.json refreshed")

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