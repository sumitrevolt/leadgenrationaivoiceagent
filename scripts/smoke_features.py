"""Smoke-test the newly enabled features (safe ones). Run on VPS after restart.

Runs ops watchdog (read-only), onboarding sweep (limit 2), and a structured-content
post. Skips reply-triage on purpose (it marks inbox mail seen — let the scheduler do it).
"""

import asyncio
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


async def main():
    try:
        from app.platform.ops_watchdog import run_watchdog

        r = await run_watchdog()
        if r.get("ok"):
            print("WATCHDOG: ok (system healthy)")
        else:
            print(
                "WATCHDOG: issues =",
                [i.get("key") for i in r.get("issues", [])],
                "| diag:",
                r.get("diagnosis", "")[:120],
            )
    except Exception as e:
        print("watchdog err:", e)

    try:
        from app.marketing.onboarding import run_onboarding_sweep

        print("ONBOARD sweep:", await run_onboarding_sweep(limit=2))
    except Exception as e:
        print("onboard err:", e)

    try:
        from app.marketing.post_generator import generate_post

        p = await generate_post("Test Cafe", "restaurant_cafe", offer="20% off")
        print(
            "STRUCTURED post -> provider:",
            p.get("provider"),
            "| caption chars:",
            len(p.get("caption", "")),
        )
    except Exception as e:
        print("structured err:", e)


asyncio.run(main())
