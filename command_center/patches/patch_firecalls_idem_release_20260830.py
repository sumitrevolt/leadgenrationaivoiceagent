#!/usr/bin/env python3
"""PILOT hotfix 2026-08-30 14:35 IST — fire_calls.py FAIL branch idem-release.

Root cause (evidence): call_loop.log batches 7-12 all SKIP(already_dispatched_this_session)
after 14:07 batches 1-6 FAIL 'not owned'. FAIL branch records FAILED disposition but never
releases session slot / idem claim => same 3 leads re-fetched forever, 0 attempts per batch.
Fix: on FAIL, release slot + idem so next batch actually attempts again (when DID lands,
retry hits PLACED OK). Compliance gates untouched.
"""
import re, sys, shutil

path = "/opt/leadgen/scripts/fire_calls.py"
src = open(path, encoding="utf-8").read()

old = """        else:
            body = result.get("vobiz_response", {}).get("body", {})
            print(f"FAIL  {result.get('error') or body}")
            if spine_on:
                await vl.record_session_disposition(session_id, vl.VoiceDisposition.FAILED)
            fail += 1"""

new = """        else:
            body = result.get("vobiz_response", {}).get("body", {})
            print(f"FAIL  {result.get('error') or body}")
            if spine_on:
                await vl.record_session_disposition(session_id, vl.VoiceDisposition.FAILED)
                await vl.release_session_slot(session_id)
                await vl.session_idem_release(session_id, f"lead:{p['phone']}")
                print("RELEASED(retry_next_batch)")
            fail += 1"""

if old not in src:
    print("PATCH_ANCHOR_NOT_FOUND", file=sys.stderr)
    sys.exit(2)

shutil.copy2(path, path + ".bak-pilot-20260830-1435")
open(path, "w", encoding="utf-8").write(src.replace(old, new, 1))
print("PATCHED_OK")