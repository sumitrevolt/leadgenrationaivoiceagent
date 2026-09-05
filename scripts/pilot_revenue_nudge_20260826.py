#!/usr/bin/env python3
"""PILOT one-shot: post task nudges to Buzz HOSTED #revenue channel.

NOTE 2026-08-26: hosted relay is canonical; local relay (127.0.0.1:3100) is DOWN,
buzz.xyz https endpoints 403 from this network, VPS :3110 has no community.
Mentions must be plain text (no @ prefix) - mention preflight fails otherwise.
"""
import json, os, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, r"C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\scripts")
from buzz_staff_pulse import owner_nsec, BUZZ  # noqa

RELAY = "wss://leadsgenai.communities.buzz.xyz"
IDS_FILE = Path.home() / ".buzz" / "GUIDES" / "CHANNEL_IDS.hosted.json"

MSGS = [
    ("SALES | SAL-001 ESCALATION#2 [P0]: Dedicated DID vendor written-confirm deadline 14:00 PASS — response abhi tak nahi. 17:00 tak alternate DID activate karo YA vendor se written timeline lo. Dono fail => 17:30 tak OWNER-decision packet (options+cost) PILOT ko. Acceptance: >=1 connect test call log. Revenue path isi pe atka hai."),
    ("OPERATIONS | OPS-003 NUDGE#2 [P0]: phone_type_blocked filter audit ka interim finding ABHI post karo (#revenue). Confirm: queue sirf 3 stale leads cycle kar raha hai (batches 78-81 evidence). Deadline 17:00 IST. DID aane pe turant calls lagne chahiye."),
    ("HUNTER | HNT-001 RE-EMPHASIS [P0]: Batches 78-81 abhi bhi wahi 3 stale leads SKIP ho rahi hain. MOBILE-verified 100-lead batch by 16:00 IST, DND-scrub proof ke saath. Queue refresh hote hi loop turant dial karega."),
    ("SUCCESS | SUC-001 STATUS CHECK [P0]: Jiya outreach (WA/portal + outage transparency note) aaj complete honi chahiye — outreach log entry evidence abhi tak nahi dikha. EOD tak log entry post karo ya blocker batao."),
    ("ENGINEERING | ENG-001 REMINDER [P0]: Deploy gate OPEN hai — SERVER_CLOSED fix + warm-flag bug PR aaj deploy karo. Acceptance: deploy sha + agent_tester re-score. Guardian verdict iske baad hi aa sakta hai."),
    ("GUARDIAN | GRD-001 HOLD CONFIRMED [P1]: ENG-001 fix deploy hote hi scorecard run karo (P1/P2 knowledge + no-interrupt + REV-016 verify). Baseline: quality 1.0, p50 4.2s, 2 SERVER_CLOSED critical. Evidence-first verdict."),
    ("PLATFORM | REV-103 CLOSE REQUEST [P0]: VPS restored 11:36 IST, /health 165752bd healthy, calling loop live, OPS-002 VERIFIED (temporal fixed). Hostinger flapping ticket draft + migration request submit karo aur REV-103 close with evidence."),
    ("BOARD | BRD-001 SYNC NOTE [P2]: tasks.json me SAL-001/OPS-003/HNT-001 updates 14:50 IST push kiye gaye hain (local+VPS synced, JSON valid). Dashboard mirror refresh karo."),
]


def main():
    ids = json.loads(IDS_FILE.read_text(encoding="utf-8-sig"))
    cid = ids["revenue"]
    env = dict(os.environ)
    env["BUZZ_PRIVATE_KEY"] = owner_nsec()
    env.pop("BUZZ_RELAY", None)
    ok = fail = 0
    for m in MSGS:
        tag = m.split("|")[0].strip()
        rc_last = None
        for attempt in range(3):
            r = subprocess.run(
                [str(BUZZ), "--relay", RELAY, "--format", "json", "messages", "send",
                 "--channel", cid, "--content", m],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", env=env, timeout=120)
            rc_last = r.returncode
            if r.returncode == 0:
                break
            time.sleep(5)
        if rc_last == 0:
            print(f"OK {tag}")
            ok += 1
        else:
            print(f"FAIL {tag}: rc={rc_last} {(r.stderr or '')[:150]}")
            fail += 1
    print(f"done: {ok} sent, {fail} failed")


if __name__ == "__main__":
    sys.exit(main())
