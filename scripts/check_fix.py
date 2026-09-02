"""Verify duplicate-route fix: no dup routes, existing modules intact, my dups gone."""

import importlib
import os
import sys
from collections import Counter

for _p in ("/opt/leadgen/.env", ".env"):
    if os.path.exists(_p):
        for _ln in open(_p, encoding="utf-8"):
            _ln = _ln.strip()
            if _ln and not _ln.startswith("#") and "=" in _ln:
                _k, _v = _ln.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
        break
sys.path.insert(0, os.getcwd())

from app.api import marketing as M  # noqa: E402

paths = [(r.path, tuple(sorted(getattr(r, "methods", []) or []))) for r in M.router.routes]
dups = {k: v for k, v in Counter(paths).items() if v > 1}
print("DUPLICATE_ROUTES:", dups or "NONE")

import app.marketing.festivals as F  # noqa: E402

ups = F.upcoming(60)
print("festivals.upcoming(60):", len(ups), "| sample:", ups[0] if ups else None)

import app.marketing.review_replies as RR  # noqa: E402

print("review_replies.generate_replies present:", hasattr(RR, "generate_replies"))

fa = sorted({r.path for r in M.router.routes if r.path.endswith("/festival-autoschedule")})
fv = sorted({r.path for r in M.router.routes if r.path.endswith("/festivals")})
print("festival-autoschedule routes:", fa, "| /festivals routes:", fv)

for m in ["festival_calendar", "review_reply", "ad_copy", "gbp_post", "reel_script"]:
    try:
        importlib.import_module(f"app.marketing.{m}")
        print("STILL_EXISTS (bad):", m)
    except ModuleNotFoundError:
        print("deleted_ok:", m)
