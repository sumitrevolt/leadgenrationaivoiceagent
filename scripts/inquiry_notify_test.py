#!/usr/bin/env python3
"""Quick inquiry + notify test only — run in leadgen_app container."""

import asyncio
import uuid
from datetime import datetime, timezone

from app.api import public_site as ps

rec = {
    "id": str(uuid.uuid4()),
    "at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "name": "Sprint Test",
    "business_name": "LeadGen Sprint QA",
    "phone": "9876543210",
    "niche": "solar_residential",
    "city": "Pune",
    "message": "inquiry notify test",
    "package": "growth",
    "source": "website",
    "ip": "127.0.0.1",
}
f = ps._append_jsonl(rec)
d = ps._save_lead_db(rec)
print("store file=", f, "db=", bool(d))
asyncio.run(ps._notify_inquiry_email(dict(rec)))
print("notify_ok")
