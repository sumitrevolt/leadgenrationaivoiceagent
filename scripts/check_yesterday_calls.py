import sys
from sqlalchemy import text
from app.models.base import _get_sync_engine

engine = _get_sync_engine()
with engine.connect() as conn:
    res = conn.execute(text("SELECT * FROM call_logs WHERE call_sid IN ('7bdc9afb-7d71-405e-afea-4566158c6def', 'cd27c771-ebf3-40aa-896a-a97c869537b9', '659537e1-8ba4-4a37-8a1d-0447e80d90d8');"))
    keys = list(res.keys())
    for row in res.fetchall():
        d = dict(zip(keys, row))
        print("=== Call record ===")
        for k, v in d.items():
            print(f"  {k}: {v}")
