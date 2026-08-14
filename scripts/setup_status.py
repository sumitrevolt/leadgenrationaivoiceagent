"""CLI: print the stack's Setup & Readiness report.

Run on the VPS:  cd /opt/leadgen && .venv/bin/python scripts/setup_status.py

Loads /opt/leadgen/.env so feature flags + keys are visible, then prints what's live,
what to enable, and what needs a user action. Read-only — changes nothing.
"""

import os
import sys

# load .env into the environment so os.getenv sees the real flags/keys
for _p in ("/opt/leadgen/.env", ".env"):
    if os.path.exists(_p):
        try:
            for _line in open(_p, encoding="utf-8"):
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
        except Exception:
            pass
        break

sys.path.insert(0, os.getcwd())

try:
    from app.platform.setup_status import format_report

    print(format_report())
except Exception as exc:
    print(f"setup_status error: {exc}")
    sys.exit(1)
