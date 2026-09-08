"""Check current revenue pipeline state."""
import sys, os
sys.path.insert(0, '/opt/leadgen')
os.environ.setdefault('DB_CREATE_ALL', '0')

# 1. Daily pipeline volume (last 30 days of outreach)
from app.platform.reply_agent import hot_queue
hq = hot_queue(scope='boss')
print(f"=== HOT QUEUE: {len(hq)} hot leads ===")
for r in hq[:5]:
    print(f"  {r['business_name'][:40]} | {r['niche']} | {r['city']} | {r['intent']}")

# 2. Check recent outreach attempts
try:
    from app.tasks.staff_jobs import STAFF_JOBS_VALID
    print(f"\n=== STAFF_JOBS_VALID count: {len(STAFF_JOBS_VALID)} ===")
    for sj in sorted(STAFF_JOBS_VALID):
        print(f"  {sj}")
except Exception as e:
    print(f"STAFF_JOBS_VALID error: {e}")

# 3. Check scheduler beat entries
try:
    from app.worker import HEAVY_STAFF_JOBS
    print(f"\n=== HEAVY_STAFF_JOBS count: {len(HEAVY_STAFF_JOBS)} ===")
except Exception as e:
    print(f"HEAVY_STAFF_JOBS error: {e}")

# 4. Check billing packages (revenue truth)
try:
    from app.billing.packages import get_public_packages
    pkgs = get_public_packages()
    print(f"\n=== PUBLIC PACKAGES ===")
    for p in pkgs:
        print(f"  {p.get('id')}: ₹{p.get('price')}/mo — {p.get('name')}")
except Exception as e:
    print(f"Packages error: {e}")

# 5. Check recent invoices
try:
    from sqlalchemy import create_engine, text
    from app.config import settings
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, customer_name, amount, status, created_at FROM invoices ORDER BY created_at DESC LIMIT 10"))
        print(f"\n=== RECENT INVOICES ===")
        for row in result:
            print(f"  {row[0]} | {row[1]} | ₹{row[2]} | {row[3]} | {row[4]}")
except Exception as e:
    print(f"Invoices query error: {e}")
