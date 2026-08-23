"""run_wiring_gaps.py — Board-run wiring-gaps audit (PR #421 runner).

Prints automation_health().wiring_gaps so 'flag ON but backend/creds missing'
surfaces before it bites. Exits 1 on gaps found.
"""
import sys

try:
    from app.platform.automation_health import health

    h = health()
    gaps = h.get("wiring_gaps") or []
    if not gaps:
        print("WIRING_GAPS_OK 0 gaps — armed flags sab wired.")
        sys.exit(0)
    print(f"WIRING_GAPS {len(gaps)} gap(s):")
    for g in gaps:
        flag = g.get("flag", "?")
        missing = g.get("missing", "?")
        print(f"  - {flag}: {missing}")
    sys.exit(1)
except ImportError as e:
    print(f"Import failed: {e}")
    sys.exit(2)
except Exception as e:
    print(f"Unexpected error: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(3)
