#!/usr/bin/env python3
"""Append OWNER-ESC for 08:00 Sep4 run on record."""
import json

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
TS = "2026-09-04T08:00:00+05:30"

esc = {
    "ts": TS,
    "level": "OWNER_ESCALATION",
    "reason": "Revenue rails STALLED day5+; fleet 0-ACK ~5d (all specialist GHANTIs unanswered); goal deadline 08-30 PASSED; verified Rs1,999 Jiya sole; GAP Rs4,98,001",
    "verified_revenue": "Rs1,999 (Jiya INV/2026-27/0001 SOLE)",
    "gap": "Rs4,98,001",
    "live_evidence_this_run": {
        "health": "37a1daf8 healthy uptime11h50m environment=production",
        "wa_msg_id": 0,
        "wa_auto_sent_true": 0,
        "wa_auto_sent_false": 469,
        "wa_auto_sent_none": 1829,
        "wa_channel_whatsapp": 1129,
        "sip_host_len": 0,
        "sip_user_len": 0,
        "sip_pass_len": 0,
        "sip_did_len": 0,
        "sip_provider_len": 0,
        "vobiz_caller_id_len": 13,
        "dialer_proc": 0,
        "leads": 0,
        "hot_queue_0904": "ABSENT (2nd day, last 09-03)"
    },
    "blocked_since": {
        "dialer": "2026-08-31 08:39:55Z (batch 211, CLI revoked)",
        "wa_sendtext": "never shipped (ENG-004 msg_id=0 ~5d)",
        "qualified_leads": "leads/ empty ~5d",
        "vendor_did": "SIP 5 vars empty, no Jio/RMS creds",
        "fleet_ack": "~5 days"
    },
    "critical_paths_zero": {
        "ENG-004": "WA sendText NEVER fires (msg_id=0, auto_sent None=1829) despite env flip + restart",
        "HNT-005": "qualified leads 0 (leads/=0), hot-queue 09-04 absent",
        "PLT-005": "DID not landed (SIP empty), dialer dead day5",
        "SUC-004": "Jiya SMTP/WA retention proof 0 (only payer churn-risk)",
        "SAL-005": "no genuine-buyer UPI close (WA rail gated)"
    },
    "action_this_run": "08:00 IST full-dispatch pushed to VPS mirror (specialists reach): REV-COMMAND + ENG-004 DECISIVE GHANTI (gate 09:00, hard acceptance) + PLT-005/HNT-005/SUC-004/SAL-005/GRD-004/OPS-007/BRD-003 standing re-notes. VPS mirror md5 now current.",
    "recommendation": "OWNER 3 decisions needed: (a) force-deploy ENG-004 real WAHA sendText commit (needs msg-id proof) — THE single unlock to pehla UPI close; (b) Jio/RMS DID creds for PLT-005 to revive dialer; (c) Jiya retention P0 (only verified payer). Jab tak ye gates locked, naya verified collection Rs0. Goal 08-30 passed — seek re-baseline.",
    "deadline_owned": "next gate ENG-004 09:00 IST 2026-09-04"
}
p = f"{BASE}/esc_0904_0800.jsonl"
with open(p, "a", encoding="utf-8") as f:
    f.write(json.dumps(esc, ensure_ascii=False) + "\n")
print("OWNER-ESC appended:", p)
