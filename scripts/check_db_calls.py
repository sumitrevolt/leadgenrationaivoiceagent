import sys
from sqlalchemy import text
from app.models.base import _get_sync_engine

engine = _get_sync_engine()
print("Connecting to DB via app engine...")
try:
    with engine.connect() as conn:
        res = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public';"))
        tables = [r[0] for r in res]
        print("Tables:", tables)
        
        for t in ["call_logs", "call_attempts", "calls", "voice_calls", "call_sessions", "campaign_leads", "leads"]:
            if t in tables:
                print(f"\n--- Table {t} (last 10) ---")
                res = conn.execute(text(f"SELECT * FROM {t} ORDER BY 1 DESC LIMIT 10;"))
                rows = res.fetchall()
                print(f"Count: {len(rows)}")
                for row in rows:
                    print(row)
except Exception as e:
    print("DB Error:", e)
