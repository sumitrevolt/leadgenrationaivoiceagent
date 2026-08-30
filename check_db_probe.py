from app.models.base import _SessionLocal
import sqlalchemy as sa
db = _SessionLocal()
for q in [
    "SELECT count(*) FROM leads",
    "SELECT count(*) FROM leads WHERE call_attempts=0",
    "SELECT count(*) FROM leads WHERE phone_type LIKE '%MOBILE%'",
    "SELECT count(*) FROM leads WHERE call_attempts=0 AND (phone_type LIKE '%MOBILE%' OR phone_type LIKE '%FLOM%')",
]:
    try:
        print(q, "=>", db.execute(sa.text(q)).scalar())
    except Exception as e:
        print(q, "ERR", repr(e)[:120])
