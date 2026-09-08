"""Verify LLM cooldown + content scheduler. Run on VPS:
cd /opt/leadgen && .venv/bin/python scripts/check_advanced.py
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
    from app.voice_agent import free_ai

    r, prov = await free_ai.chat(
        "You are terse.", [{"role": "user", "content": "say OK"}], max_tokens=5
    )
    print("free_ai.chat ->", repr((r or "")[:30]), "| provider:", prov or "(none)")
    print(
        "cooldown state:",
        {
            k: round(v - __import__("time").time(), 1)
            for k, v in free_ai._LLM_COOLDOWN_UNTIL.items()
        },
    )

    from app.marketing import content_schedule

    item = content_schedule.schedule(
        "Test Cafe", "restaurant_cafe", date_iso="2020-01-01", offer="20% off"
    )
    print("scheduled id:", item["id"], "date:", item["date"], "status:", item["status"])
    res = await content_schedule.run_due()
    print("run_due ->", res)
    lst = content_schedule.list_scheduled()
    ready = [x for x in lst if x.get("status") == "ready"]
    print(
        "list total:",
        len(lst),
        "| ready:",
        len(ready),
        "| sample_caption:",
        (ready[0]["content"]["caption"][:50] if ready and ready[0].get("content") else "—"),
    )


asyncio.run(main())
