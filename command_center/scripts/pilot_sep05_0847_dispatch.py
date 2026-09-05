#!/usr/bin/env python3
"""PILOT 08:47 IST (Sep5 CRON) - REVENUE COMMAND + fleet ghanti (09:00 gates).

FRESH live evidence 08:47 IST (this run, in-window SSH 03:17Z):
  - VPS UP (curl /health HTTP 308 auth-gated; prod containers Up; earlier window 200 719dbbd6).
  - call_loop.log mtime Aug31 08:39:55Z batch211 (ok=0 fail=3 'not owned'); proc0 cron0 -> dialer DEAD day5+.
  - SIP_5 vars ALL len=0 (disk re-check); VOBIZ_CALLER_ID len13=911171366938 REVOKED; egress api.vobiz.com DAY6.
  - leads/ EMPTY (count 0) -> ammo 0.
  - hot-queue 09-05 NOT-YET (due 03:30 UTC ~09:00 IST; abhi 03:17 = expected, verify 09:15).
  - reply_drafts auto_sent true=1 msg_id=3EB00CFC09FB70376AA279 = SAL-006 MANUAL (sent_manual); ENG-004 auto=0.
  - wa_inbound hot lead 197126499872961 count=1 ONLY (Sep4 18:21Z original) => SAL-006 reply STILL PENDING.
  - invoices tail = synthetic VOIDED only; Jiya INV/2026-27/0001 SOLE verified Rs1,999; GAP Rs4,98,001.
  - CC mirror VPS fresh (tasks/bots/pinned 03:03Z = 08:33 IST push).

One TASK-ID/bot/run — hunt-idle discipline; no new IDs (all 9 bots task-owned).
"""
import json, os, subprocess

TS = "2026-09-05T08:47:00+05:30"
BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
EV = ("LIVE 08:47 IST Sep5 (FRESH 03:17Z probe): /health 308 auth-gated UP; call_loop DEAD day5+ "
      "(mtime Aug31 08:39:55Z batch211 ok=0/fail=3 'not owned', proc0 cron0); SIP_5 vars len=0 DID0 "
      "(VOBIZ_CALLER_ID len13 REVOKED); egress api.vobiz.com DAY6; leads/ EMPTY ammo0; hot-queue 09-05 "
      "due 03:30 UTC not-yet (expected 09:00 IST, verify 09:15); reply_drafts auto_sent true=1 msg-id=3EB00CFC... "
      "= SAL-006 MANUAL (sent_manual), ENG-004 auto=0; wa_inbound count=1 hot lead 197126499872961 "
      "NO reply yet; rev VERIFIED Rs1,999 Jiya sole; GAP Rs4,98,001.")

# ---------- 1) messages.jsonl (fleet message channel) ----------
msgs = [
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "🎯 REVENUE COMMAND 08:47 IST (Sep5): TARGET Rs5,00,000 | VERIFIED Rs1,999 (Jiya INV/0001 SOLE) | "
            "GAP Rs4,98,001 | PIPELINE: SAL-006 proposal+followup SENT reply PENDING (inbound count=1); "
            "SAL-007 warm 86 nudge in flight; hot-queue 09-05 due ~09:00 IST (verify 09:15); prospects 2350. "
            "HOT: SAL-006 reply->UPI close | ENG-004 real auto sendText | Jiya retention. "
            "BOTTLENECK: #1 SAL-006 reply->UPI | #2 ENG-004 auto_send=0 (1=manual) | #3 DID0+CLI REVOKED+egress DAY6 | "
            "#4 qualified CSV ammo 0. ACTION: gates 09:00 (SAL-006/SUC-004/ENG-004/PLT-005/HNT-005/GRD-004/OPS-007) "
            "09:15 (OPS 09-05 queue verify) 09:30 (BRD-003/SAL-007 check); 0 proof 10:00 = REASSIGN+OWNER-ESC. pelican"},
    {"ts": TS, "from": "PILOT", "to": "engineering", "task_id": "ENG-004", "type": "GHANTI", "priority": "P0",
     "msg": "ENG-004 (08:47 FRESH GHANTI): reply_drafts auto_sent true=1 = SAL-006 MANUAL (msg-id 3EB00CFC... "
            "sent_manual); auto_outreach real WAHA sendText = 0 genuine auto sends — YEHI #1 close-rail unlock. "
            "09:00 HARD gate: commit sha + >=1 auto_sent=true genuine row (session:'default' + X-Api-Key + msg-id). "
            "0 proof 10:00 = reassign+ESC."},
    {"ts": TS, "from": "PILOT", "to": "platform", "task_id": "PLT-005", "type": "GHANTI", "priority": "P0",
     "msg": "PLT-005 (08:47 FRESH GHANTI): SIP_5 vars len=0 re-verified, DID0; VOBIZ_CALLER_ID len13 REVOKED; "
            "egress api.vobiz.com timeout DAY6; call_loop DEAD day5+. 09:00 gate: alternate egress probe proof "
            "+ vendor DID ETA. Jio/RMS silent => RMS Tech backup call (Rajnikant 080-47652298) + vendor proof file. "
            "DID live hote hi env-swap + restart (WA flip already LIVE=1)."},
    {"ts": TS, "from": "PILOT", "to": "hunter", "task_id": "HNT-005", "type": "GHANTI", "priority": "P0",
     "msg": "HNT-005 (08:47 FRESH GHANTI): leads/ EMPTY count=0 re-verified — ammo day6. 09:00 gate: 50 QUALIFIED "
            "business-owner mobile CSV (Google Maps Places + SearXNG, DND-proof col) to /opt/leadgen/data/leads/ + "
            "pool refill scan. Abhi tak 0 CSV."},
    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "SAL-006", "type": "GHANTI", "priority": "P0",
     "msg": "SAL-006 (08:47 FRESH GHANTI): wa_inbound count=1 re-verified = sirf Sep4 original; proposal 3EB00... + "
            "followup 3EB076... SENT, reply PENDING. 09:00 gate: webhook + wa_inbound monitor; reply aaye => "
            "objection handling + UPI deep link + ledger INV open (💰 REVENUE EVENT). 0 reply => follow-up #2 "
            "(latest window, max2) + owner-route nudge 09:00 IST. ACCEPTANCE: reply ya NOT-INTERESTED proof."},
    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "SAL-007", "type": "GHANTI", "priority": "P1",
     "msg": "SAL-007 (08:47 bump): 86 warm UPI deep-links 0 reply to date. 10 follow-up nudges (1-tap CTA) + 3 trial "
            "pitches ABHI dialer-independent. ACCEPTANCE: >=3 WAHA sendText msg-ids captured; 0 reply -> working set "
            "report. 12:00 IST gate. Track in SAL-006 exercised-lead set, do NOT warm the SAL-006 hot lead."},
    {"ts": TS, "from": "PILOT", "to": "success", "task_id": "SUC-004", "type": "GHANTI", "priority": "P0",
     "msg": "SUC-004 (08:47 FRESH GHANTI): Jiya = SOLE payer Rs1,999; churn = revenue ZERO. Sep2 se 0 proof — 3 din "
            "miss. 09:00 gate: Hostinger SMTP sent msg-id artifact + WA follow-up + fallback retention offer — "
            "DID-independent, ABHI karo. Har din nudge; restart ke baad WA-rail renewal nudge bhi."},
    {"ts": TS, "from": "PILOT", "to": "guardian", "task_id": "GRD-004", "type": "GHANTI", "priority": "P1",
     "msg": "GRD-004 (08:47 FRESH GHANTI): verdicts file ABHI ABSENT (command_center/data me koi GRD/verdict file "
            "nahi). 09:00 gate: 6 scopes PASS/FAIL — (a) ENG-004 automation unshipped (auto_sent 1=manual), "
            "(b) SAL-006 reply pending (inbound count=1), (c) SIP blank DID0, (d) egress/dialer dead day5-6, "
            "(e) leads EMPTY, (f) revenue-truth Jiya sole Rs1,999 vs snapshots 5997 STALE. File path + verdicts likho."},
    {"ts": TS, "from": "PILOT", "to": "operations", "task_id": "OPS-007", "type": "GHANTI", "priority": "P1",
     "msg": "OPS-007 (08:47 FRESH GHANTI): digest STILL OVERDUE. ABHI banao: (1) WA auto_send defer root-cause "
            "(flip=1 but auto=0), (2) hot-queue 09-05 verify @09:15 IST (due 03:30 UTC — confirm presence/absence + "
            "date-lock diagnosis), (3) restart cadence (restart sirf DID swap ke baad). ACC 09:15 IST."},
    {"ts": TS, "from": "PILOT", "to": "board", "task_id": "BRD-003", "type": "GHANTI", "priority": "P2",
     "msg": "BRD-003 (08:47 FRESH): PILOT abhi mirror push karega (tasks/bots/pinned/messages 08:47). "
            "/app/bot-command-center page verify — SAL-006 PENDING reply + bottleneck chain dikhna chahiye. "
            "09:30 gate. Visualization ONLY."},
]

with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("messages.jsonl appended", len(msgs))

# ---------- 2) tasks.json status refresh (same TASK IDs, honest statuses + fresh tail) ----------
with open(os.path.join(BASE, "tasks.json"), encoding="utf-8") as f:
    tasks = json.load(f)

UPD = {
    "ENG-004": ("RUNNING", "08:47 ghanti; auto_sent true=1 = SAL-006 MANUAL 3EB00CFC; auto=0 still. 09:00 HARD gate: commit sha + >=1 genuine auto_sent row."),
    "SAL-006": ("UPDATE", "08:47 IST: wa_inbound count=1 (sirf Sep4 original). Proposal 3EB00... + followup 3EB076... SENT, reply PENDING. 09:00 gate reply monitor; 0 reply => follow-up #2 + owner-route nudge."),
    "SAL-007": ("NEW", "08:47 bump: 10 nudge + 3 trial in flight; ACC >=3 msg-ids 12:00."),
    "SUC-004": ("RUNNING", "08:47 ghanti; SMTP sent artifact + WA follow-up due 09:00 — 3 din 0 proof."),
    "HNT-005": ("BLOCKED", "08:47 ghanti re-issued; leads/ STILL 0, 50 qualified CSV due 09:00."),
    "PLT-005": ("BLOCKED", "08:47 ghanti; DID0 + egress DAY6, vendor silent; RMS Tech backup + ETA due 09:00."),
    "GRD-004": ("RUNNING", "08:47 ghanti; verdicts file ABSENT, due 09:00."),
    "OPS-007": ("RUNNING", "08:47 ghanti; digest OVERDUE + 09-05 queue verify @09:15."),
    "BRD-003": ("RUNNING", "08:47 ghanti; mirror push now, page verify 09:30."),
}

for t in tasks:
    tid = t.get("id")
    if tid in UPD:
        st, note = UPD[tid]
        t["status"] = st
        t["notes"] = note
        t["evidence_tail"] = EV
        t["updated_at"] = TS

with open(os.path.join(BASE, "tasks.json"), "w", encoding="utf-8") as f:
    json.dump(tasks, f, ensure_ascii=False, indent=1)
print("tasks.json refreshed", len(tasks))

# ---------- 3) pinned.json + bots.json refresh ----------
with open(os.path.join(BASE, "pinned.json"), encoding="utf-8") as f:
    pin = json.load(f)
pin["last_updated"] = TS
pin["priority_tasks"] = ["SAL-006", "ENG-004", "PLT-005", "HNT-005", "SUC-004", "GRD-004", "OPS-007", "BRD-003", "SAL-007"]
pin["vps_status"] = ("VPS UP /health 308 auth-gated (prod 719dbbd6 earlier window). call_loop DEAD day5+ "
                     "(DID0 egress DAY6); leads/ EMPTY; hot-queue 09-05 due 03:30 UTC (verify 09:15); "
                     "reply_drafts auto_sent 1 = SAL-006 manual (ENG-004 auto=0); wa_inbound count=1 SAL-006 "
                     "reply PENDING. rev Rs1,999 GAP Rs4,98,001.")
pin["bottleneck"] = ("#1 SAL-006 reply->UPI close | #2 ENG-004 real auto sendText=0 (auto_sent 1 = manual) | "
                     "#3 DID0+CLI REVOKED+egress DAY6 (vendor-gated) | #4 qualified CSV ammo 0")
pin["pipeline"] = ("SAL-006 proposal+followup SENT reply PENDING + SAL-007 warm 86 nudge in flight + "
                   "hot-queue 09-05 due 03:30 UTC (verify 09:15) + prospects 2350")
pin["action"] = ("08:47 REVENUE COMMAND broadcast; gates 09:00 (ENG/PLT/HNT/SAL/SUC/GRD/OPS) "
                 "09:15 (OPS 09-05 verify) 09:30 (BRD/SAL-007 check); 0 proof 10:00 = REASSIGN+OWNER-ESC")
pin["next_expected_payment"] = "SAL-006 UPI close (reply pending) / SAL-007 nudge replies / Jiya renewal; DID aane par dial track"
with open(os.path.join(BASE, "pinned.json"), "w", encoding="utf-8") as f:
    json.dump(pin, f, ensure_ascii=False, indent=1)
print("pinned.json refreshed")

with open(os.path.join(BASE, "bots.json"), encoding="utf-8") as f:
    bots = json.load(f)
bots["Pilot"]["status"] = ("08:47 IST Sep5 (LIVE 03:17Z): /health 308 auth-gated UP; SAL-006 reply PENDING "
                           "(inbound count=1); call_loop DEAD day5+ (DID0 egress DAY6); ENG-004 auto=0 "
                           "(1 manual); leads/ 0; hot-queue 09-05 due 03:30 UTC (verify 09:15). "
                           "rev Rs1,999 GAP Rs4,98,001. Gates 09:00/09:15/09:30; 0 proof 10:00 = REASSIGN+ESC.")
bots["sales"]["status"] = "SAL-006 P0 reply PENDING 09:00 gate + SAL-007 P1 warm nudge in flight (12:00 gate)."
bots["hunter"]["status"] = "HNT-005 P0 BLOCKED leads/ 0 — 09:00 gate 50 CSV."
bots["platform"]["status"] = "PLT-005 P0 BLOCKED DID0 egress DAY6 — RMS backup call + vendor ETA 09:00."
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