#!/usr/bin/env python3
"""PILOT Sep-04 ~06:30 IST sweep - REVENUE COMMAND GHANTI (LIVE re-verified).
State UNCHANGED since 06:15: SIP 5 vars ALL EMPTY (DID not landed), auto_sent 0,
hot-queue 09-04 NOT gen. FRESH evidence + tight 07:00 gates."""
import json, os

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-04T06:30:00+05:30"

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")

G = lambda to, tid, typ, prio, msg: {"ts": TS, "from": "PILOT", "to": to, "task_id": tid,
                                     "type": typ, "priority": prio, "msg": msg}

FACT = ("LIVE 06:30 IST Sep4 (PILOT re-verified): /health 308 auth-gated (healthy); containers Up; "
        "SIP 5 vars ALL len=0 (SIP_HOST/DID blank) DID NOT landed; VOBIZ_CALLER_ID REVOKED; "
        "call_loop mtime Aug31 batch211 = DIALER DEAD day5 proc0 NO watchdog; WA flip container=1 LIVE par "
        "auto_sent TRUE=0/2298 (NO msg-id day5+); leads/ EMPTY ammo 0; hot-queue last 09-03, "
        "09-04 NOT gen (date-lock broken 2nd day); rev Rs1,999 Jiya sole; GAP Rs4,98,001.")

msgs = [
    G("ALL", "REV-COMMAND", "REVENUE_COMMAND", "P0",
      "🎯 REVENUE COMMAND 06:30 IST (Sep4): TARGET Rs5,00,000 | VERIFIED Rs1,999 (Jiya SOLE INV-0001) | "
      "GAP Rs4,98,001 | PIPELINE 2298 drafts auto_sent=0 day5+ (0 real UPI) | HOT Jiya P0 churn risk | "
      "BOTTLENECK #1 WA-rail sendText 0 day5+ (flip LIVE=1 par 0 msg-id) -> 0 UPI | #2 LEADS/ EMPTY ammo | "
      "#3 DID env EMPTY (dialer dead day5+) | #4 hot-queue date-lock 09-04 NOT gen 2nd day | "
      "ACTION: ENG-004 sendText msg-id #1 | SAL-005 genuine-intent close (dirty HARD STOP) | "
      "HNT-005 50 qualified DND CSV | PLT-005 DID vendor proof+ETA | SUC-004 Jiya SMTP+WA | "
      "OPS-007 date-lock digest | GRD-004 verdicts. NEXT: pehla REAL sendText msg-id -> genuine reply -> "
      "UPI close-kit -> ledger INV. 07:00 EVIDENCE. PENDING/link NEHI PAID. ACK. 🐦 pelican"),
    G("engineering", "ENG-004", "GHANTI", "P0",
      "ENG-004 (06:30 FRESH GHANTI) - " + FACT + " #1 EXECUTABLE REVENUE GATE day5+. "
      "auto_outreach link-only churn, WAHA sendText (session:default, X-Api-Key) ZERO. "
      "WA rail = SOLE live revenue engine; 0 sends = 0 UPI. 06:15 GHANTI par bhi 0 proof/0 ACK. "
      "ACC 07:00: commit sha + >=1 auto_sent=true row WITH msg-id (WAHA 200 proof). ACK + SHOW THE MSG-ID."),
    G("sales", "SAL-005", "GHANTI", "P0",
      "SAL-005 (06:30 FRESH GHANTI) - dirty lists HARD STOP (guardian FAIL PROVEN). "
      "Find GENUINE-intent threads in wa_conversations (product Q/need, NOT newsletter/auto-rep) then "
      "MANUAL WAHA sendText close-kit (session:default, msg-id 200, UPI 8459012607@axl). "
      "ACC 07:00: >=3 genuine-intent DELIVERED sends (msg-id) + 0 dirty + DID vendor status "
      "(WA Call Soft wa.me/917599967999 + RMS 080-47652298). 1-2 REAL closes > 86 junk. P0. ACK."),
    G("platform", "PLT-005", "GHANTI", "P0",
      "PLT-005 (06:30 FRESH GHANTI) - " + FACT + " SIP 5 vars len=0 re-confirmed (LIVE). DID-land = dialer unlock #3. "
      "Vendor creds mile to env-swap + restart + first post-DID dial proof; 0 proof = vendor DID status + ETA "
      "DOCUMENTED (Call Soft + RMS). egress api.vobiz.com 000 TCP-block alternate-route note. ACC 07:00. P0. ACK."),
    G("success", "SUC-004", "GHANTI", "P0",
      "SUC-004 (06:30 FRESH GHANTI) - Jiya = SOLE payer Rs1,999, churn = REVENUE ZERO. "
      "Sep2 se 0 SMTP/WA proof day4+. ACC 07:00: Hostinger SMTP recovery email SENT artifact (msg-id) "
      "+ WA follow-up + retention offer. DID-independent - 0 gate, sirf execute. REVENUE-PROTECT P0. "
      "0 proof = FAILING. ACK + SEND NOW."),
    G("hunter", "HNT-005", "GHANTI", "P1",
      "HNT-005 (06:30 FRESH GHANTI) - leads/ EMPTY re-confirm (ammo 0 day5+). 50 QUALIFIED mobile "
      "DND-scrubbed business-owner high-intent CSV to /opt/leadgen/data/leads/ (dirty reseller REJECT - "
      "hot-queue 86=0 buyer PROVEN). DID aate hi dialer raw chahiye ammo. ACC 07:00: CSV path + 50 "
      "verified MOBILE + DND-proof column + pool refill. P1. ACK."),
    G("guardian", "GRD-004", "GHANTI", "P1",
      "GRD-004 (06:30 FRESH GHANTI) - verdicts file ABHI: (a) auto_sent=0/2298 link-only-vs-sendText "
      "(critical #1); (b) revenue-truth snap vs ledger kaunsa REAL; (c) dialer-dead day5+; "
      "(d) DID vendor 0 proof; (e) 43-blast 0-genuine-buyer (ALREADY FAIL dirty); "
      "(f) hot-queue 09-04 NOT gen = date-lock broken 2nd day (FAIL). Independent PASS/FAIL file in "
      "command_center/data. ACC 07:00. P1. ACK."),
    G("operations", "OPS-007", "GHANTI", "P1",
      "OPS-007 (06:30 FRESH GHANTI) - BAD: hot-queue 09-04 NOT gen again (last 09-03) - scheduler date-lock "
      "BROKEN 2nd day. Digest ABHI @06:30: WA auto_sent 0/2298 (flip LIVE=1 par 0 sends day5+); dialer DEAD "
      "day5+ restart cadence (DID ke baad, TRAI 10:00-19:00 window); 09-04 queue-gen failure root-cause "
      "+ fix-watch. Digest file in command_center/data. ACC 07:00. P1. ACK."),
    G("board", "BRD-003", "GHANTI", "P2",
      "BRD-003 (06:30 FRESH GHANTI) - visualization ONLY: command_center mirror on VPS + "
      "/app/bot-command-center page verify (Sep4 06:30 state incl WA flip LIVE + auto_send 0 + "
      "dialer DEAD + SIP empty + 09-04 queue MISSING). PILOT fresh push abhi. ACC 07:00 page/mtime proof. "
      "P2 - NEVER command bots. ACK."),
]
with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("messages appended:", len(msgs))

# ---------- 2) bots.json ----------
bp = os.path.join(BASE, "bots.json")
bots = load(bp)
sts = {
    "Pilot": "06:30 IST Sep4 (FRESH): /health 308 auth-gated up; WA flip LIVE=1 par auto_sent 0/2298 NO msg-id "
             "(link-only day5+); SIP 5 vars len=0 DID NOT landed (CLI revoked); dialer DEAD day5+ (leads0); "
             "hot-queue 09-04 NOT gen (date-lock broken 2nd day); rev Rs1,999 Jiya sole; GAP Rs4,98,001. "
             "GHANTI all 8 07:00 gates - 06:15 too 0 proof/0 ACK (fleet unresponsive ~52h).",
    "engineering": "ENG-004 P0 (FRESH GHANTI): WA flip LIVE=1 par auto_send 0/2298 NO msg-id - link-only→sendText. #1 gate. 07:00.",
    "platform": "PLT-005 P0 (FRESH GHANTI): dialer day5+ - SIP 5 vars len=0 re-confirm, CLI revoked, leads 0. DID vendor proof+ETA. 07:00.",
    "operations": "OPS-007 P1 (FRESH GHANTI): 09-04 queue NOT gen 2nd day (date-lock broken); WA auto_send 0 digest. 07:00.",
    "sales": "SAL-005 P0 (FRESH GHANTI): dirty HARD STOP; GENUINE wa_conversations intent close msg-id. 07:00.",
    "hunter": "HNT-005 P1 (FRESH GHANTI): leads/ 0 (ammo 0 day5+); 50 qualified DND mobile CSV. 07:00.",
    "guardian": "GRD-004 P1 (FRESH GHANTI): verdicts file 07:00 - auto_send/rev-truth/dialer/DID/43-blast/09-04-date-lock.",
    "success": "SUC-004 P0 (FRESH GHANTI): Jiya sole payer retention SMTP+WA proof. 07:00.",
    "board": "BRD-003 P2 (FRESH GHANTI): VPS mirror + page verify Sep4 06:30. 07:00.",
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
    "ENG-004": "PILOT 06:30 IST Sep4 CRON (LIVE FRESH): /health 308 up; containers Up; WA flip container=1 LIVE; auto_sent TRUE=0/2298 NO msg-id - WAHA sendText 0 day5+. #1 EXECUTABLE gate 07:00: >=1 auto_sent=true msg-id.",
    "SAL-005": "PILOT 06:30 IST Sep4 CRON: dirty HARD STOP. GENUINE wa_conversations intent close -> MANUAL WAHA sendText close-kit msg-id. ACC 07:00 >=3 genuine sends msg-id + DID vendor status.",
    "PLT-005": "PILOT 06:30 IST Sep4 CRON: SIP 5 vars ALL len=0 re-confirm (SIP_HOST=/SIP_DID= blank); VOBIZ_CALLER_ID revoked; call_loop mtime Aug31 batch211 proc0; leads/ EMPTY. DIALER DEAD day5+. ACC 07:00 DID vendor proof+ETA.",
    "SUC-004": "PILOT 06:30 IST Sep4 CRON: Jiya sole payer 1999 churn P0; 0 SMTP/WA proof since Sep2 day4. ACC 07:00 SMTP msg-id + WA follow-up + retention offer. DID-independent.",
    "HNT-005": "PILOT 06:30 IST Sep4 CRON: leads/ EMPTY re-confirm (ammo 0 day5+). 50 qualified DND mobile CSV 07:00.",
    "GRD-004": "PILOT 06:30 IST Sep4 CRON: verdicts file 07:00 (auto_send link-only / rev-truth / dialer-dead / DID / 43-blast-0-buyer / 09-04-date-lock 2nd-day FAIL).",
    "OPS-007": "PILOT 06:30 IST Sep4 CRON: hot-queue 09-04 NOT gen 2nd day (last 09-03, date-lock broken). Digest 07:00: WA auto_send 0 day5+ + dialer dead cadence + 09-04 date-lock root-cause.",
    "BRD-003": "PILOT 06:30 IST Sep4 CRON: mirror + page verify Sep4 06:30. 07:00.",
}
for t in tasks:
    if t["id"] in tails:
        t["evidence_tail"] = tails[t["id"]]
        t["updated_at"] = TS
save(tp, tasks)
print("tasks.json tails updated")

# ---------- 4) pinned.json ----------
pp = os.path.join(BASE, "pinned.json")
try:
    pin = load(pp)
except Exception:
    pin = {}
pin["last_updated"] = "2026-09-04T06:30+05:30"
pin["vps_status"] = ("HEALTHY (/health 308 auth-gated, containers Up); VERIFIED rev Rs1,999 (Jiya INV/2026-27/0001 SOLE); "
                     "WA flip container=1 LIVE par auto_sent 0/2298 NO msg-id (link-only day5+) -> 0 UPI; "
                     "hot-queue 09-04 NOT gen 2nd day (date-lock broken); dialer DEAD day5+ (SIP 5 vars len=0, CLI "
                     "revoked, leads 0); GAP Rs4,98,001. GHANTI all 8 07:00 gates - fleet unresponsive ~52h "
                     "(00 proof, 0 ACK across Sep3/Sep4 runs).")
save(pp, pin)
print("pinned.json updated")
print("DONE")
