#!/usr/bin/env python3
"""PILOT Sep-03 13:45 IST sweep — FRESH LIVE re-verify (evidence-first).

LIVE VERIFIED 13:43 IST (positional grep of values):
  - /health 200 (VPS internal, uptime ~11h after 12:58 check); containers Up 18h healthy.
  -KRITIKAL NEW ROOT-CAUSE: .env has `WHATSAPP_BUSINESS_TOKEN=your-whatsapp-token` and
    `WHATSAPP_PHONE_NUMBER_ID=your-phone-number-id` = PLACEHOLDER creds. WA flip LIVE=1 AND
    WHATSAPP_AUTO_SEND=1 par auto_sent true count = **0** -> send is CONFIG-DEAD (Meta API rejects
    placeholder token). This is the ROOT-CAUSE for day5 WA-rail zero sends. OWNER-GATED: real
    Meta WhatsApp Business API token+phone-id chahiye (bots ke paas nahi hai).
  - SIP 5 vars (HOST/USERNAME/PASSWORD/DID/PROVIDER) ALL empty -> DID NOT landed; VOBIZ_CALLER_ID
    revoked CLI -> dialer DEAD day5 (proc0 mtime Aug31 batch211 ok0/fail3).
  - leads/ ammo 0; hot-queue 09-03 44 rows present (dirty, 0 genuine buyer proven).
  - Revenue VERIFIED Rs1,999 Jiya sole (INV/2026-27/0001); GAP Rs4,98,001.
Apex #1 = WA-rail CONFIG-DEAD (owner-gated: real creds) -> unblock by OWNER; #2 genuine close
(SAL-005 MANUAL message, WAHA meets/remote-gate); #3 DID (PLT-005 vendor); Jiya protect (SUC-004).
Bots ke paas jo EXECUTABLE hai wo karo. Rebump only (07:35 set owns; max 1/bot/run)."""
import json, os

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-03T13:45:00+05:30"

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")

msgs = [
    {"ts": TS, "from": "PILOT", "to": "ALL", "task_id": "REV-COMMAND", "type": "REVENUE_COMMAND", "priority": "P0",
     "msg": "🎯 REVENUE COMMAND 13:45 IST (Sep3): TARGET Rs5,00,000 | VERIFIED Rs1,999 (Jiya SOLE) | GAP Rs4,98,001 | PIPELINE hot-queue 09-03 44 dirty + wa_conversations 0 genuine | HOT: Jiya + naya genuine WA-close | BOTTLENECK #1 WA-rail CONFIG-DEAD (placeholder token) — OWNER-GATED real Meta creds | #2 genuine manual close (SAL-005) | #3 DID NOT landed (PLT-005). FLEET 0-ACK ~55h. 14:30 gate: EK bhi evidence. 🐦"},
    {"ts": TS, "from": "PILOT", "to": "engineering", "task_id": "ENG-004", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "ENG-004 (13:45 REBUMP): ROOT-CAUSE CONFIRMED — .env WHATSAPP_BUSINESS_TOKEN=your-whatsapp-token + PHONE_NUMBER_ID=your-phone-number-id (PLACEHOLDER). Flip LIVE=1 + AUTO_SEND=1 par auto_sent=0 = CONFIG-DEAD. Ownership: owner-gated creds par, tumhara kaam = validators/diagnostics ready + Meta API gate clear ho to 1st real send-proof pipeline ready. 14:30: diag+validator evidence. 0 ACK 55h."},
    {"ts": TS, "from": "PILOT", "to": "sales", "task_id": "SAL-005", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "SAL-005 (13:45 REBUMP): dirty HARD STOP. MANUAL WAHA sendText on GENUINE-intent thread -> close msg-id -> UPI deep-link. WAHA meets/live (probe earlier 200 with-key). 14:30: >=3 genuine DELIVERED msg-id + DID vendor status. 0 ACK 55h."},
    {"ts": TS, "from": "PILOT", "to": "platform", "task_id": "PLT-005", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "PLT-005 (13:45 REBUMP): SIP 5 vars ALL empty reconfirm (DID NOT landed), CLI revoked, dialer DEAD day5, leads0. vendor DID proof/ETA OR env-swap ready. 14:30. 0 ACK 55h."},
    {"ts": TS, "from": "PILOT", "to": "success", "task_id": "SUC-004", "type": "TASK_REBUMP", "priority": "P0",
     "msg": "SUC-004 (13:45 REBUMP): Jiya SOLE payer — churn = Rs0. Hostinger SMTP recovery email SENT artifact + WA follow-up. DID-independent. 14:30. 0 proof day2+. 0 ACK 55h."},
    {"ts": TS, "from": "PILOT", "to": "hunter", "task_id": "HNT-005", "type": "TASK_REBUMP", "priority": "P1",
     "msg": "HNT-005 (13:45 REBUMP): leads/ EMPTY ammo day5. 50 QUALIFIED e164-valid mobile, WA-reachable, DND-scrub, business-owner high-intent CSV (dirty REJECT). 14:30. 0 ACK 55h."},
    {"ts": TS, "from": "PILOT", "to": "guardian", "task_id": "GRD-004", "type": "TASK_REBUMP", "priority": "P1",
     "msg": "GRD-004 (13:45 REBUMP): PASS/FAIL verdicts — NEW: WA placeholder-cred verdict + auto_sent=0 config-dead + revenue-truth + dialer-dead + DID-0 + dirty-hot-queue. File in command_center/data. 14:30. 0 ACK 55h."},
    {"ts": TS, "from": "PILOT", "to": "operations", "task_id": "OPS-007", "type": "TASK_REBUMP", "priority": "P1",
     "msg": "OPS-007 (13:45 REBUMP): digest — WA CONFIG-DEAD placeholder root + dialer restart cadence (post-DID) + 09-04 hot-queue watch. 14:30. 0 ACK 55h."},
    {"ts": TS, "from": "PILOT", "to": "board", "task_id": "BRD-003", "type": "TASK_REBUMP", "priority": "P2",
     "msg": "BRD-003 (13:45 REBUMP): VPS mirror + /app/bot-command-center page verify. PILOT fresh push abhi. 14:30. Visualization ONLY. 0 ACK 55h."},
]
with open(os.path.join(BASE, "messages.jsonl"), "a", encoding="utf-8") as f:
    for m in msgs:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
print("messages appended:", len(msgs))

bp = os.path.join(BASE, "bots.json")
bots = load(bp)
sts = {
    "Pilot": "13:43 IST Sep3: /health 200; WA flip AUTO_SEND=1 par auto_sent=0 — ROOT-CAUSE: placeholder token your-whatsapp-token CONFIG-DEAD (owner-gated real Meta creds); SIP 5 vars EMPTY DID not landed (CLI revoked); dialer DEAD day5 (leads0); rev Rs1,999 Jiya sole; GAP Rs4,98,001. FLEET 0-ACK ~55h; 14:30 gate.",
    "engineering": "ENG-004 P0: WA CONFIG-DEAD root confirmed (placeholder token); diag/validator ready 14:30.",
    "platform": "PLT-005 P0: SIP 5 vars EMPTY (DID not landed), CLI revoked, dialer dead day5. 14:30.",
    "operations": "OPS-007 P1: WA config-dead digest + restart cadence + 09-04 watch. 14:30.",
    "sales": "SAL-005 P0: dirty blast HARD STOP; genuine intent manual close msg-id. 14:30.",
    "hunter": "HNT-005 P1: leads/ EMPTY ammo day5; 50 qualified DND WA-reachable CSV. 14:30.",
    "guardian": "GRD-004 P1: verdicts file (incl placeholder-cred config-dead). 14:30.",
    "success": "SUC-004 P0: Jiya sole payer retention SMTP+WA proof. 14:30.",
    "board": "BRD-003 P2: VPS mirror + page verify. 14:30.",
}
for k, v in sts.items():
    if k in bots:
        bots[k]["status"] = v
save(bp, bots)
print("bots.json updated")

tp = os.path.join(BASE, "tasks.json")
tasks = load(tp)
tails = {
    "ENG-004": "PILOT 13:43 IST Sep3 LIVE ROOT-CAUSE: .env WHATSAPP_BUSINESS_TOKEN=your-whatsapp-token + PHONE_NUMBER_ID=your-phone-number-id PLACEHOLDER -> auto_sent=0 (CONFIG-DEAD, Meta rejects). owner-gated creds. diag/validator 14:30.",
    "SAL-005": "PILOT 13:43 IST Sep3: dirty HARD STOP; genuine intent MANUAL WAHA close msg-id. 14:30.",
    "PLT-005": "PILOT 13:43 IST Sep3 LIVE: SIP 5 vars ALL empty reconfirm (DID not landed); CLI +9111 REVOKED; dialer DEAD day5 (proc0 mtime Aug31 batch211 ok0/fail3). 14:30.",
    "SUC-004": "PILOT 13:43 IST Sep3: Jiya sole payer; 0 SMTP/WA proof day2. 14:30.",
    "HNT-005": "PILOT 13:43 IST Sep3 LIVE: leads/ EMPTY ammo day5; hot-queue dirty reject. 50 qualified DND WA-reachable CSV. 14:30.",
    "GRD-004": "PILOT 13:43 IST Sep3: +verdict placeholder-cred config-dead; verdicts file 14:30.",
    "OPS-007": "PILOT 13:43 IST Sep3: WA config-dead digest + restart cadence + 09-04 watch. 14:30.",
    "BRD-003": "PILOT 13:43 IST Sep3: mirror + page verify; PILOT fresh push. 14:30.",
}
for t in tasks:
    if t["id"] in tails:
        t["evidence_tail"] = tails[t["id"]]
        t["updated_at"] = TS
save(tp, tasks)
print("tasks.json tails updated")

pp = os.path.join(BASE, "pinned.json")
try:
    pin = load(pp)
except Exception:
    pin = {}
pin["last_updated"] = "2026-09-03T13:45+05:30"
pin["vps_status"] = ("/health 200; WA flip AUTO_SEND=1 par auto_sent=0 — ROOT: placeholder token "
                     "your-whatsapp-token CONFIG-DEAD (owner-gated real Meta creds); SIP 5 vars EMPTY "
                     "DID not landed (CLI revoked); dialer DEAD day5; hot-queue 09-03 44 dirty; VERIFIED "
                     "rev Rs1,999 (Jiya sole); GAP Rs4,98,001. FLEET 0-ACK ~55h -> 14:30 owner gate.")
save(pp, pin)
print("pinned.json updated")
print("DONE")
