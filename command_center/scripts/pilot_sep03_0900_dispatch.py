#!/usr/bin/env python3
"""PILOT Sep-03 09:00 IST sweep — evidence-first REVENUE COMMAND.
FRESH LIVE (09:00): /health 036a4e4b healthy uptime6h40m; WA flip LIVE containers=1 CONFIRMED
(both worker+app); auto_sent true=0/2262 (still link-only, no sendText); hot-queue 09-03 NOW PRESENT
(44 rows — OPS-007 root-cause RESOLVED, scheduler back up); wa_conversations 435 last Sep2 17:06, 0 Sep3
(43/43 09-02 sends still PENDING, dirty newsletter list, 0 genuine buyer); SIP 5 vars EMPTY, VOBIZ
REVOKED CLI +911****6938 still in env, call_loop mtime Aug31 batch211, leads/ ABSENT (DID day4);
revenue VERIFIED Rs1,999 Jiya sole (INV/2026-27/0001), GAP Rs4,98,001.
KEY SHIFT THIS RUN: all 8 bots already own tasks (07:35 assign, 10:00 gates) — NO idle bot. So this is
GHANTI/UPDATE (evidence bump), not new TASK-IDs. Max-1-TASK-ID-per-bot honored. Notable POSITIVE:
09-03 queue auto-generated (scheduler healed). Notable WARNING: SAL-005 dirty-list blast pre-empted by
GRD-004 (reputation+compliance burn). Appends messages.jsonl, updates tasks/bots/pinned."""
import json, os

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-03T09:00:00+05:30"

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")

# ---------- 1) messages.jsonl (destination bots poll this = message_agent channel) ----------
msgs = [
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "🎯 REVENUE COMMAND 09:00 IST (Sep3): TARGET Rs5,00,000 | VERIFIED Rs1,999 (Jiya INV/2026-27/0001 SOLE; 0002-13 voided) | GAP Rs4,98,001 | PIPELINE: 43 warm 09-02 (0 delivered), hot-queue 09-03 NOW PRESENT 44 rows (scheduler healed) | HOT: Jiya P0 churn + genuine intent threads in wa_conversations 435 (NOT dirty 43) | BOTTLENECK #1: WA-rail auto_send ZERO (flip LIVE=1 par auto_sent true=0/2262, link-only no sendText) -> 0 UPI | #2 DIALER DEAD day4 (SIP 5 vars EMPTY, CLI REVOKED, leads/ ABSENT) | #3 dirty-list reputation burn (guardian-flagged, 43-blast=0 buyer) | ACTION: engineering auto_send sendText fix (ENG-004 #1 gate); sales work GENUINE wa_conversations intent threads not dirty blast; platform DID-land+ammo; success Jiya retention; hunter 50 qualified CSV | NEXT: pehla REAL auto/DELIVERED WA send -> genuine reply -> UPI close kit -> ledger INV. PENDING/link ≠ PAID. ACK + EXECUTE, 10:00 gate. Evidence mile to report, nahi to reassign."},
    {"ts": TS, "from": "PILOT", "to": "engineering", "task_id": "ENG-004", "type": "UPDATE", "priority": "P0",
     "msg": "ENG-004 (09:00 GHANTI) — WA flip LIVE RE-CONFIRMED containers BOTH =1 (worker+app), restart hua health 036a4e4b. Par auto_sent true STILL 0/2262 (reply_drafts mtime Sep2 23:30) — tick 'succeeds' but produces wa_links_generated/calling_flagged only, NEVER WAHA sendText. #1 EXECUTABLE GATE: auto_outreach ka WA branch ko real sendText (session:'default', X-Api-Key, msg-id, 200 proof) pe le jao. ACC 10:00: commit sha + >=1 auto_sent=true row with msg-id in reply_drafts. Ab WA-rail = SOLE live revenue engine (dialer dead day4). P0."},
    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "SAL-005", "type": "UPDATE", "priority": "P0",
     "msg": "SAL-005 (09:00 GHANTI) — STOP do NOT blind-blast dirty 09-02 43 hot-queue: guardian GRD-004 proved it = newsletter/dirty list, 0 genuine buyer, 43/43 sends STILL PENDING 6d+. That = reputation+compliance burn (wa_suppression risk), NOT qualified pipeline. REDIRECT: wa_conversations.jsonl 435 threads mein se GENUINE intent leads nikalo (product-question/product-need replies, NOT '😂'/newsletter-auto-rep) -> unpe MANUAL WAHA sendText close-kit (session:'default', msg-id proof). Plus vendor DID status. ACC 10:00: >=3 genuine-thread sends delivered + 0 dirty blast + DID status. 1-2 quality closes >> 43 junk sends. P0."},
    {"ts": TS, "from": "PILOT", "to": "platform", "task_id": "PLT-005", "type": "UPDATE", "priority": "P0",
     "msg": "PLT-005 (09:00 GHANTI) — FRESH: SIP 5 vars ALL EMPTY (SIP_HOST/USERNAME/PASSWORD/DID/PROVIDER=DID not landed); VOBIZ_CALLER_ID +911****6938 REVOKED CLI STILL in env; call_loop mtime Aug31 batch211 proc0; leads/ ABSENT. DIALER DEAD day4. DID-land = aaj ka #2 unlock (WA-rail ke baad). Vendor creds mile to env-swap + container restart (WA-flip path already owner-approved/proven). 0 proof = DID vendor status + ETA. ACC 10:00. P0."},
    {"ts": TS, "from": "PILOT", "to": "success", "task_id": "SUC-004", "type": "UPDATE", "priority": "P0",
     "msg": "SUC-004 (09:00 GHANTI) — Jiya = SOLE payer Rs1,999 (INV/2026-27/0001), churn = verified revenue -> Rs0. Sep2 se 0 SMTP/WA proof, deadlines missed. ACC 10:00: Hostinger SMTP recovery email SENT artifact (msg-id) + WA follow-up + retention offer. DID-independent — iska koi gate nahi, sirf execution. Aaj ka REVENUE-PROTECT rail. P0."},
    {"ts": TS, "from": "PILOT", "to": "hunter", "task_id": "HNT-005", "type": "UPDATE", "priority": "P1",
     "msg": "HNT-005 (09:00 GHANTI) — leads/ STILL ABSENT (ammo 0, day4). 50 QUALIFIED mobile-DND-scrubbed business-owner CSV (dirty reseller REJECT — hot-queue 43 = 0 buyer proven). ACC 10:00: CSV path + 50 verified MOBILE + DND-proof column + pool refill. DID aate hi dialer raw — turant ammo. P1."},
    {"ts": TS, "from": "PILOT", "to": "guardian", "task_id": "GRD-004", "type": "UPDATE", "priority": "P1",
     "msg": "GRD-004 (09:00 GHANTI) — pending verdicts at 10:00: (a) auto_sent=0/2262 link-only-vs-sendText PASS/FAIL; (b) revenue-truth snap(active=3/MRR5997) vs ledger(Jiya sole 1999+voided) — kaunsa real; (c) dialer-dead day4; (d) DID vendor 0 proof; (e) 43/43 09-02 PENDING + 0 genuine buyer verdict (ALREADY FAIL — ki dirty list); (f) 09-03 queue now PRESENT (did scheduler heal?). Independent file in command_center/data. ACC 10:00. P1."},
    {"ts": TS, "from": "PILOT", "to": "operations", "task_id": "OPS-007", "type": "UPDATE", "priority": "P1",
     "msg": "OPS-007 (09:00 GHANTI) — GOOD NEWS: hot-queue 09-03 NOW PRESENT (44 rows Sep3 03:30) — scheduler date-lock issue SELF-HEALED, us root-cause ko CLOSE. NEW digest at 10:00: WA auto_sent STILL 0/2262 (flip LIVE=1 par 0 sends); dialer DEAD day4 restart cadence (DID ke baad); watch 09-04 queue generation tomorrow 03:30. Digest file. P1."},
    {"ts": TS, "from": "PILOT", "to": "board", "task_id": "BRD-003", "type": "UPDATE", "priority": "P2",
     "msg": "BRD-003 (09:00 GHANTI) — visualization only: command_center mirror on VPS + /app/bot-command-center page verify (Sep3 09:00 state incl 09-03 hot-queue + WA flip LIVE). PILOT fresh push abhi. ACC 10:00 page/mtime proof. P2 — NEVER command bots."},
]
with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("messages appended:", len(msgs))

# ---------- 2) bots.json ----------
bp = os.path.join(BASE, "bots.json")
bots = load(bp)
sts = {
    "Pilot": "09:00 IST Sep3: WA flip LIVE (containers=1) re-confirm; auto_sent=0/2262 (link-only no sendText) -> 0 UPI; hot-queue 09-03 PRESENT (scheduler healed); dialer DEAD day4 (SIP empty, CLI revoked, leads abs); rev Rs1,999 Jiya sole; GAP Rs4,98,001. Ghanti ENG-004/SAL-005/PLT-005/SUC-004/HNT-005/GRD-004/OPS-007/BRD-003 10:00 gates.",
    "engineering": "ENG-004 P0 (GHANTI): WA flip LIVE=1 par auto_send 0/2262 — link-only→sendText. #1 gate. 10:00.",
    "platform": "PLT-005 P0 (GHANTI): dialer day4 — SIP 5 vars empty, CLI revoked, leads abs. DID-land. 10:00.",
    "operations": "OPS-007 P1 (GHANTI): 09-03 queue PRESENT (root-cause CLOSED); WA auto_send 0 digest. 10:00.",
    "sales": "SAL-005 P0 (GHANTI): HOT — STOP dirty 43 blast (guardian FAIL); work GENUINE wa_conversations intent. 10:00.",
    "hunter": "HNT-005 P1 (GHANTI): leads/ ABSENT (ammo 0); 50 qualified DND mobile CSV. 10:00.",
    "guardian": "GRD-004 P1 (GHANTI): verdicts 10:00 — auto_send/rev-truth/dialer/DID/43-blast/09-03-heal.",
    "success": "SUC-004 P0 (GHANTI): Jiya sole payer retention SMTP+WA proof. 10:00.",
    "board": "BRD-003 P2 (GHANTI): mirror+page verify Sep3. 10:00.",
}
for k, v in sts.items():
    if k in bots:
        bots[k]["status"] = v
save(bp, bots)
print("bots.json updated")

# ---------- 3) pinned.json ----------
pp = os.path.join(BASE, "pinned.json")
try:
    pin = load(pp)
except Exception:
    pin = {}
pin["last_updated"] = "2026-09-03T09:00+05:30"
pin["vps_status"] = ("HEALTHY (036a4e4b, uptime6h40m); VERIFIED rev Rs1,999 (Jiya INV/2026-27/0001 SOLE); "
                     "WA flip LIVE containers=1 par auto_sent 0/2262 (link-only, no sendText) -> 0 UPI; "
                     "hot-queue 09-03 PRESENT (scheduler healed); dialer DEAD day4 (SIP empty, CLI revoked, leads abs); "
                     "GAP Rs4,98,001. Ghanti all 8 bots 10:00 gates.")
save(pp, pin)
print("pinned.json updated")
print("DONE")