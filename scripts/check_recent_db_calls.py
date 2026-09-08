import sys
from sqlalchemy import text
from app.models.base import _get_sync_engine

engine = _get_sync_engine()
with engine.connect() as conn:
    res = conn.execute(text("SELECT * FROM call_logs WHERE created_at >= '2026-08-20' ORDER BY created_at DESC;"))
    keys = res.keys()
    print("Columns:", list(keys))
    rows = res.fetchall()
    print(f"Total call_logs since 2026-08-20: {len(rows)}")
    for r in rows:
        d = dict(zip(keys, r))
        print({k: v for k, v in d.items() if v not in (None, "", False)})
