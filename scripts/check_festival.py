"""Verify festival calendar + autoschedule. VPS:
   cd /opt/leadgen && .venv/bin/python scripts/check_festival.py
"""
import os
import sys

for _p in ("/opt/leadgen/.env", ".env"):
    if os.path.exists(_p):
        for _ln in open(_p, encoding="utf-8"):
            _ln = _ln.strip()
            if _ln and not _ln.startswith("#") and "=" in _ln:
                _k, _v = _ln.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
        break
sys.path.insert(0, os.getcwd())

from app.marketing import festival_calendar  # noqa: E402

ups = festival_calendar.upcoming(months_ahead=12)
print("upcoming(12 months):", len(ups), "festivals")
for f in ups[:6]:
    print("   ", f["date"], "|", f["name"], f"({f['days_away']}d away)")

res = festival_calendar.autoschedule("Test Cafe", "restaurant_cafe", months_ahead=3)
print("autoschedule(3mo) ->", {"scheduled": res["scheduled"], "skipped": res["skipped"]})
print("    sample items:", res["items"][:3])

res2 = festival_calendar.autoschedule("Test Cafe", "restaurant_cafe", months_ahead=3)
print("re-run (dup-safe) ->", {"scheduled": res2["scheduled"], "skipped": res2["skipped"]})
print("DUP_SAFE_OK:", res2["scheduled"] == 0 and res2["skipped"] >= res["scheduled"])
