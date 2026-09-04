import sys
from sqlalchemy import text
from app.models.base import _get_sync_engine

engine = _get_sync_engine()
with engine.connect() as conn:
    res = conn.execute(text("SELECT created_at, call_sid, to_number, duration_seconds, status, outcome, summary FROM call_logs ORDER BY created_at DESC LIMIT 35;"))
    rows = res.fetchall()
    print(f"Total call_logs: {len(rows)}")
    for r in rows:
        print(f"{r[0]} | SID: {r[1]} | To: {r[2]} | Dur: {r[3]}s | Status: {r[4]} | Outcome: {r[5]}")
