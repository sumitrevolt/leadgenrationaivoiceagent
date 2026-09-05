#!/usr/bin/env python3
"""Container-side splice patch: add session release on FAIL branch."""
path = "scripts/fire_calls.py"
src = open(path, encoding="utf-8").read()
anchor = "await vl.record_session_disposition(session_id, vl.VoiceDisposition.FAILED)"
add = (
    "\n                await vl.release_session_slot(session_id)\n"
    "                await vl.session_idem_release(session_id, f\"lead:{p['phone']}\")\n"
    "                print(\"RELEASED(retry_next_batch)\")"
)
print("anchor_count:", src.count(anchor))
if src.count(anchor) == 1 and "session_idem_release(session_id, f\"lead:{p['phone']}\")" not in src:
    open(path, "w", encoding="utf-8").write(src.replace(anchor, anchor + add, 1))
    print("PATCHED_OK")
else:
    print("ALREADY_OR_AMBIG")