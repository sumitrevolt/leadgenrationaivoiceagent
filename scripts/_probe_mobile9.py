import asyncio, os, sys
sys.path.insert(0, "/app")
import asyncpg

async def main():
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    c = await asyncpg.connect(url)
    qs = {
        "uncontacted_total": "SELECT count(*) FROM leads WHERE COALESCE(call_attempts,0)=0",
        "mobile9_series": "SELECT count(*) FROM leads WHERE COALESCE(call_attempts,0)=0 AND phone ~ '(^|\\+)(91)9[0-9]{9}$'",
        "mobile_shown_series": "SELECT left(phone,11) AS p, count(*) FROM leads WHERE COALESCE(call_attempts,0)=0 AND phone ~ '(^|\\+)(91)9[0-9]{9}$' GROUP BY 1 ORDER BY 2 DESC LIMIT 5",
        "any_9_plan": "SELECT count(*) FROM leads WHERE COALESCE(call_attempts,0)=0 AND (phone LIKE '919%' OR phone LIKE '+919%')",
        "niche_9series": "SELECT COALESCE(niche,'(null)') AS n, count(*) FROM leads WHERE COALESCE(call_attempts,0)=0 AND (phone LIKE '919%' OR phone LIKE '+919%') GROUP BY 1 ORDER BY 2 DESC LIMIT 10",
    }
    for name, q in qs.items():
        try:
            rows = await c.fetch(q)
            print(name, "->", [dict(r) for r in rows][:6])
        except Exception as e:
            print(name, "ERR", repr(e))
    await c.close()

asyncio.run(main())