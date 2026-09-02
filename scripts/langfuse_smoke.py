#!/usr/bin/env python3
"""langfuse_smoke.py — Langfuse ingestion wiring verify (deploy ke baad).

Container me chalao:  docker exec leadgen_app python scripts/langfuse_smoke.py
Ek test trace POST karta + HTTP status print karta. Expect: 207 (multi-status =
accepted). 401/403 = auth galat; connection-error = network/endpoint. Trace
"deploy-smoke-test" naam se Langfuse dashboard me dikhega (harmless).
"""

from __future__ import annotations

import base64
import os
import sys
import uuid
from datetime import datetime, timezone


def main() -> int:
    pk = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
    sk = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
    base = (os.environ.get("LANGFUSE_BASE_URL", "") or "https://us.cloud.langfuse.com").strip()
    if not pk or not sk:
        print("SKIP: LANGFUSE_PUBLIC_KEY/SECRET_KEY not set in env")
        return 0
    try:
        import httpx
    except Exception as e:
        print(f"FAIL: httpx import error: {e}")
        return 0

    url = base.rstrip("/") + "/api/public/ingestion"
    token = base64.b64encode(f"{pk}:{sk}".encode()).decode()
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "batch": [
            {
                "id": str(uuid.uuid4()),
                "timestamp": now,
                "type": "trace-create",
                "body": {
                    "id": str(uuid.uuid4()),
                    "timestamp": now,
                    "name": "deploy-smoke-test",
                    "metadata": {"source": "langfuse_smoke.py"},
                    "tags": ["smoke-test"],
                    "environment": os.environ.get("ENVIRONMENT", "production"),
                },
            }
        ]
    }
    try:
        r = httpx.post(
            url,
            headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=10.0,
        )
        print(f"POST {url}")
        print(f"HTTP {r.status_code} -> {r.text[:300]}")
        print(
            "RESULT: OK (traces will flow)"
            if r.status_code in (200, 207)
            else "RESULT: CHECK auth/endpoint"
        )
    except Exception as e:
        print(f"FAIL: request error: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
