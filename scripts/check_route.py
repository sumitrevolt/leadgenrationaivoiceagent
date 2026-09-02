import asyncio
import os
import sys

sys.path.insert(0, os.getcwd())
from app.main import FRONTEND_DIR, app

print("FRONTEND_DIR =", str(FRONTEND_DIR))
print("login.html exists:", os.path.isfile(os.path.join(str(FRONTEND_DIR), "login.html")))
appp = [
    str(getattr(r, "path", ""))
    for r in app.routes
    if str(getattr(r, "path", "")).startswith("/app/")
]
print("/app/* routes (in order):", appp)

# Show ALL routes whose pattern could match '/app/login' (catch-alls / params).
import re

matchers = []
for r in app.routes:
    p = str(getattr(r, "path", ""))
    rx = getattr(r, "path_regex", None)
    try:
        if rx is not None and rx.match("/app/login"):
            matchers.append((p, type(r).__name__))
    except Exception:
        pass
print("routes whose regex matches /app/login:", matchers)

import httpx


async def t():
    tr = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=tr, base_url="http://t") as ac:
        for p in ["/app/login", "/app/analytics", "/app/customer"]:
            try:
                r = await ac.get(p)
                print("ASGI", p, "->", r.status_code)
            except Exception as e:
                print("ASGI", p, "ERR", repr(e)[:90])


asyncio.run(t())
