import asyncio, os, sys
sys.path.insert(0, "/app")
import asyncpg
from app.telephony.dial_gate import phone_quality

async def main():
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    c = await asyncpg.connect(url)
    rows = await c.fetch("SELECT phone FROM leads WHERE COALESCE(call_attempts,0)=0")
    print("uncontacted_total:", len(rows))
    from collections import Counter
    qc = Counter()
    samples = {}
    for r in rows:
        ph = r["phone"] or ""
        q = phone_quality(ph)
        qc[q] += 1
        if q not in samples and len(samples) < 8:
            samples[q] = ph
    print("quality_dist:", dict(qc))
    print("samples:", samples)
    # niche breakdown of mobile-quality
    try:
        mobrows = await c.fetch("""
            SELECT phone, niche FROM leads
            WHERE COALESCE(call_attempts,0)=0
        """)
        mc = Counter()
        for r in mobrows:
            if phone_quality(r["phone"]) == "mobile":
                mc[r["niche"] or "(null)"] += 1
        print("mobile_by_niche_top:", mc.most_common(8))
    except Exception as e:
        print("niche_breakdown_err:", repr(e))
    await c.close()

asyncio.run(main())