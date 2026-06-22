"""Probe: pytest jaisa double TestClient lifecycle replicate karo.

test_agent_stack me test#1 (GET status) ke baad test#2 (POST run) pe
KeyboardInterrupt aata hai. Yeh script wahi sequence bina pytest ke chalati:
TestClient #1 (with-block, lifespan) -> GET -> close -> TestClient #2 -> POST
-> sleep. Kahan marta hai pata chalega.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("PROBE start", flush=True)
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

print("import done", flush=True)

with TestClient(app) as c:
    r = c.get("/api/agents/status")
    print("r1:", r.status_code, flush=True)
print("client1 closed", flush=True)

with TestClient(app) as c:
    r = c.post("/api/agents/run", json={"task": "qualify lead call campaign"})
    print("r2:", r.status_code, flush=True)
print("client2 closed", flush=True)

time.sleep(12)
print("ALIVE_END", flush=True)
sys.exit(0)
