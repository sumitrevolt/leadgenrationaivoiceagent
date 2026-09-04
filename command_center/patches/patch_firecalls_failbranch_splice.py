#!/usr/bin/env python3
"""FAIL-branch splice (branch-specific, file-level guard hata ke)."""
path = "scripts/fire_calls.py"
src = open(path, encoding="utf-8").read()
old = """            if spine_on:
                await vl.record_session_disposition(session_id, vl.VoiceDisposition.FAILED)
            fail += 1"""
new = """            if spine_on:
                await vl.record_session_disposition(session_id, vl.VoiceDisposition.FAILED)
                await vl.release_session_slot(session_id)
                await vl.session_idem_release(session_id, f"lead:{p['phone']}")
                print("RELEASED(retry_next_batch)")
            fail += 1"""
print("old_count:", src.count(old))
if src.count(old) == 1:
    open(path, "w", encoding="utf-8").write(src.replace(old, new, 1))
    print("PATCHED_OK")
else:
    print("AMBIG_OR_MISSING", src.count(old))