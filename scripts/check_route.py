import os
import sys

sys.path.insert(0, os.getcwd())
from app.main import FRONTEND_DIR, app

print("FRONTEND_DIR =", str(FRONTEND_DIR))
print("login.html exists:", os.path.isfile(os.path.join(str(FRONTEND_DIR), "login.html")))
print("analytics.html exists:", os.path.isfile(os.path.join(str(FRONTEND_DIR), "analytics.html")))
allp = [str(getattr(r, "path", "")) for r in app.routes]
print("/app/* routes:", sorted([p for p in allp if p.startswith("/app/")]))
print("has /app/login:", "/app/login" in allp, "| has /app/analytics:", "/app/analytics" in allp)
try:
    from starlette.testclient import TestClient

    c = TestClient(app)
    print("TC /app/login   ->", c.get("/app/login").status_code)
    print("TC /app/analytics ->", c.get("/app/analytics").status_code)
    print("TC /app/customer ->", c.get("/app/customer").status_code)
except Exception as e:
    print("testclient skipped:", repr(e)[:90])
