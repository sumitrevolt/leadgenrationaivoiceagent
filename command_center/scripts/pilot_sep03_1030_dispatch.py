#!/usr/bin/env python3
"""PILOT Sep-03 10:30 IST sweep — evidence-first REVENUE COMMAND GHANTI.
FRESH LIVE (10:30): /health 200 UP; WA flip LIVE containers=1 (worker+app Up14h); auto_sent TRUE=0
(NO msg-id — WA rail 0 real send day5); SIP 5 vars ALL EMPTY (SIP_HOST/USERNAME/PASSWORD/DID/len=0,
VOBIZ_CALLER_ID +911****6938 REVOKED CLI still) -> DID NOT landed; call_loop proc0 cron0 mtime Aug31
batch211 ok0/fail3 (dialer DEAD day5); leads/ dir ABSENT (ammo 0); .env mtime Sep2 12:42Z (no resize).
Revenue VERIFIED Rs1,999 Jiya sole (INV/2026-27/0001); GAP Rs4,98,001.
All 8 bots own tasks (07:35 assign, 10:00 gates MISSED ~30min, fleet ACK 0 ~53h).
GHANTI + ESCALATION bump only — no new TASK-ID (anti-spam, max 1/bot/run).
Apex bottleneck = WA-rail auto_send=0 (ENG-004); #2 genuine-intent close (SAL-005); #3 DID-land (PLT-005);
Jiya protect (SUC-004). Routes: leads 0->HNT; sends 0->ENG; intent->SAL; DID->PLT; digest->OPS; audit->GRD;
visual->BRD.
Appends messages.jsonl, updates tasks/bots/pinned."""
import json, os, datetime

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-03T10:30:00+05:30"

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")

# ---------- 1) messages.jsonl (message_agent channel) ----------
msgs = [
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "🎯 REVENUE COMMAND 10:30 IST (Sep3): TARGET Rs5,00,000 | VERIFIED Rs1,999 (Jiya INV/2026-27/0001 SOLE) | GAP Rs4,98,001 | PIPELINE wa_conversations 435 (0 genuine proven) + hot-queue 09-03 PRESENT (dirty rakho — 43-blast=0 buyer PROVEN) | HOT: Jiya P0 churn + GENUINE-intent threads | BOTTLENECK #1 WA-rail auto_send ZERO day5 (flip LIVE=1 par auto_sent true=0/2265, NO msg-id — link-only, WAHA sendText 0) -> 0 UPI | #2 DIALER DEAD day5 (SIP 5 vars EMPTY, CLI revoked, leads 0 ammo) | #3 DID vendor 0 proof | ACTION: engineer ENG-004 sendText fix=#1 gate | sales SAL-005 genuine-intent WA close (dirty blast HARD STOPPED) | platform PLT-005 DID-land+ammo | success SUC-004 Jiya retention (REVENUE-PROTECT) | hunter HNT-005 50 qualified CSV | NEXT: pehla REAL sendText msg-id -> genuine reply -> UPI close-kit -> ledger INV. PENDING/link NEHI PAID. 10:00 gates MISSED + fleet ACK 0 ~53h -> FINAL GHANTI, 30min me EVEIDENCE lao. ACK + EXECUTE. Evidence nahi = reassign. 🐦" },
    {"ts": TS, "from": "PILOT", "to": "engineering", "task_id": "ENG-004", "type": "GHANTI", "priority": "P0",
     "msg": "ENG-004 (10:30 FINAL GHANTI) — WA flip LIVE containers BOTH=1 (worker+app Up14h) par auto_sent TRUE abhi bhi 0/2265, NO msg-id anywhere — auto_outreach tick sirf wa_links_generated/calling_flagged karta hai, WAHA sendText (session:'default', X-Api-Key) 0. #1 EXECUTABLE REVENUE GATE day5. ACC 10:45 IST (ABHI): commit sha + >=1 auto_sent=true row WITH msg-id. 10:00 gate MISSED, 0 ACK ~53h. P0 — WA rail = SOLE live revenue engine. ACK + SHOW ME THE MSG-ID."},
    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "SAL-005", "type": "GHANTI", "priority": "P0",
     "msg": "SAL-005 (10:30 FINAL GHANTI) — dirty 86-list blast HARD STOP (guardian FAIL PROVEN). REDIRECT wa_conversations.jsonl 435 GENUINE-intent threads (product QUESTION/need, NOT newsletter/auto-rep/emoji) -> unpe MANUAL WAHA sendText close-kit (session:'default', msg-id 200 proof). ACC 10:45 IST: >=3 genuine-intent DELIVERED sends + 0 dirty + DID vendor status. 1-2 REAL closes beat 86 junk. 10:00 gate MISSED, 0 ACK. P0. ACK."},
    {"ts": TS, "from": "PILOT", "to": "platform", "task_id": "PLT-005", "type": "GHANTI", "priority": "P0",
     "msg": "PLT-005 (10:30 FINAL GHANTI) — FRESH LIVE re-verify: SIP 5 vars ALL EMPTY (SIP_HOST/USERNAME/DID/PROVIDER len=0, password 0), VOBIZ_CALLER_ID +911****6938 REVOKED CLI, call_loop proc0 cron0 mtime Aug31 batch211 ok0/fail3, leads/ ABSENT. DIALER DEAD day5. DID-land = #2 unlock (WA-rail ke baad) — vendor creds mile to env-swap + restart (WA-flip owner-approved/proven), phir first post-DID dial proof. 0 proof = vendor DID status + ETA documented. ACC 10:45 IST. 10:00 gate MISSED, 0 ACK. P0. ACK."},
    {"ts": TS, "from": "PILOT", "to": "success", "task_id": "SUC-004", "type": "GHANTI", "priority": "P0",
     "msg": "SUC-004 (10:30 FINAL GHANTI) — Jiya = SOLE payer Rs1,999 (INV/2026-27/0001), churn = REVENUE ZERO. Sep2 se 0 SMTP/WA proof, sab gates MISSED. ACC 10:45 IST: Hostinger SMTP recovery email SENT artifact (msg-id) + WA follow-up + retention offer. DID-independent — 0 gate, sirf execute. Aaj ka REVENUE-PROTECT rail P0. 0 proof day2 = failing. ACK + SEND."},
    {"ts": TS, "from": "PILOT", "to": "hunter", "task_id": "HNT-005", "type": "GHANTI", "priority": "P1",
     "msg": "HNT-005 (10:30 FINAL GHANTI) — leads/ dir ABSENT re-confirm (ammo 0, day5). 50 QUALIFIED mobile DND-scrubbed business-owner CSV (dirty reseller REJECT — hot-queue 86=0 buyer PROVEN). ACC 10:45 IST: CSV path + 50 verified MOBILE + DND-proof column + pool refill. DID aate hi dialer raw chahiye ammo. 10:00 gate MISSED, 0 ACK. P1. ACK."},
    {"ts": TS, "from": "PILOT", "to": "guardian", "task_id": "GRD-004", "type": "GHANTI", "priority": "P1",
     "msg": "GRD-004 (10:30 FINAL GHANTI) — pending verdicts file ABHI: (a) auto_sent=0/2265 link-only-vs-sendText PASS/FAIL (2 IS sahi 2 sabit karo — critical); (b) revenue-truth snap(active=3/MRR5997) vs ledger(Jiya sole 1999+voided) kaunsa REAL; (c) dialer-dead day5; (d) DID vendor 0 proof; (e) 43/43 09-02 PENDING + 0-genuine-buyer (ALREADY FAIL — dirty); (f) 09-03 queue PRESENT heal vindicate. Independent PASS/FAIL file in command_center/data. ACC 10:45 IST. 10:00 gate MISSED, 0 ACK. P1. ACK."},
    {"ts": TS, "from": "PILOT", "to": "operations", "task_id": "OPS-007", "type": "GHANTI", "priority": "P1",
     "msg": "OPS-007 (10:30 FINAL GHANTI) — GOOD: hot-queue 09-03 auto-generated (scheduler healed). Digest ABHI @10:30: WA auto_sent STILL 0/2265 (flip LIVE=1 par 0 sends day5); dialer DEAD day5 restart cadence (DID ke baad); watch 09-04 queue gen tomorrow 03:30. Digest file command_center/data. ACC 10:45 IST. 10:00 gate MISSED, 0 ACK. P1. ACK."},
    {"ts": TS, "from": "PILOT", "to": "board", "task_id": "BRD-003", "type": "GHANTI", "priority": "P2",
     "msg": "BRD-003 (10:30 FINAL GHANTI) — visualization ONLY: command_center mirror on VPS + /app/bot-command-center page verify (Sep3 10:30 state incl 09-03 hot-queue PRESENT + WA flip LIVE + dialer DEAD). PILOT fresh push abhi. ACC 10:45 IST page/mtime proof. P2 — NEVER command bots. ACK."},
]
with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("messages appended:", len(msgs))

# ---------- 2) bots.json ----------
bp = os.path.join(BASE, "bots.json")
bots = load(bp)
sts = {
    "Pilot": "10:30 IST Sep3: /health 200 UP (worker+app Up14h); WA flip LIVE containers=1 par auto_sent TRUE 0/2265 NO msg-id (link-only day5) -> 0 UPI; SIP 5 vars EMPTY DID NOT landed; dialer DEAD day5 (proc0 cron0 leads0); rev Rs1,999 Jiya sole; GAP Rs4,98,001. FINAL GHANTI all 8 10:45 gates — 10:00 MISSED, ACK 0 ~53h.",
    "engineering": "ENG-004 P0 (FINAL GHANTI): WA flip LIVE=1 par auto_send 0/2265 NO msg-id — link-only→sendText. #1 gate. 10:45.",
    "platform": "PLT-005 P0 (FINAL GHANTI): dialer day5 — SIP 5 vars empty, CLI revoked, leads 0. DID-land. 10:45.",
    "operations": "OPS-007 P1 (FINAL GHANTI): 09-03 queue PRESENT (root-cause CLOSED); WA auto_send 0 digest. 10:45.",
    "sales": "SAL-005 P0 (FINAL GHANTI): HOT — dirty 86 blast HARD STOP (guardian FAIL); work GENUINE wa_conversations intent close. 10:45.",
    "hunter": "HNT-005 P1 (FINAL GHANTI): leads/ 0 (ammo 0 day5); 50 qualified DND mobile CSV. 10:45.",
    "guardian": "GRD-004 P1 (FINAL GHANTI): verdicts file 10:45 — auto_send/rev-truth/dialer/DID/43-blast/09-03-heal.",
    "success": "SUC-004 P0 (FINAL GHANTI): Jiya sole payer retention SMTP+WA proof. 10:45.",
    "board": "BRD-003 P2 (FINAL GHANTI): VPS mirror + page verify Sep3 10:30. 10:45.",
}
for k, v in sts.items():
    if k in bots:
        bots[k]["status"] = v
save(bp, bots)
print("bots.json updated")

# ---------- 3) tasks.json evidence_tail for active tasks ----------
tp = os.path.join(BASE, "tasks.json")
tasks = load(tp)
tails = {
    "ENG-004": "PILOT 10:30 IST Sep3: auto_sent TRUE=0/2265 (NO msg-id) — WA flip LIVE=1 containers BOTH par sendText 0 day5. #1 gate 10:45. 10:00 MISSED, ACK 0.",
    "SAL-005": "PILOT 10:30 IST Sep3: dirty 86 blast HARD STOP. Redirect genuine wa_conversations intent -> manual sendText close. 10:45.",
    "PLT-005": "PILOT 10:30 IST Sep3: SIP 5 vars EMPTY re-confirm (DID NOT landed); CLI revoked; loop proc0 cron0 mtime Aug31 batch211 ok0/fail3; leads 0. Dialer day5. 10:45.",
    "SUC-004": "PILOT 10:30 IST Sep3: Jiya sole payer 1999; 0 SMTP/WA proof since Sep2 (day2). ACC 10:45 SMTP msg-id + WA follow-up.",
    "HNT-005": "PILOT 10:30 IST Sep3: leads/ ABSENT re-confirm (ammo 0 day5). 50 qualified DND mobile CSV 10:45.",
    "GRD-004": "PILOT 10:30 IST Sep3: verdicts file 10:45 (auto_send/rev-truth/dialer/DID/43-blast/09-03-heal).",
    "OPS-007": "PILOT 10:30 IST Sep3: 09-03 queue PRESENT (root-cause CLOSED); digest 10:45 WA auto_send 0 day5 + dialer dead cadence + 09-04 watch.",
    "BRD-003": "PILOT 10:30 IST Sep3: mirror + page verify 10:45.",
}
for t in tasks:
    if t["id"] in tails:
        t["evidence_tail"] = tails[t["id"]]
        t["updated_at"] = "2026-09-03T10:30:00+05:30"
save(tp, tasks)
print("tasks.json tails updated")

# ---------- 4) pinned.json ----------
pp = os.path.join(BASE, "pinned.json")
try:
    pin = load(pp)
except Exception:
    pin = {}
pin["last_updated"] = "2026-09-03T10:30+05:30"
pin["vps_status"] = ("HEALTHY (200, worker+app Up14h); VERIFIED rev Rs1,999 (Jiya INV/2026-27/0001 SOLE); "
                     "WA flip LIVE containers=1 par auto_sent 0/2265 (NO msg-id, link-only day5) -> 0 UPI; "
                     "hot-queue 09-03 PRESENT (scheduler healed); dialer DEAD day5 (SIP 5 vars EMPTY, CLI revoked, leads 0); "
                     "GAP Rs4,98,001. FINAL GHANTI all 8 10:45 gates — 10:00 MISSED ACK 0 ~53h.")
save(pp, pin)
print("pinned.json updated")
print("DONE")
