"""
LeadGen AI - Outbound call campaign
leads DB se numbers uthata hai, Swara se LeadGen AI pitch karwata hai.
Run: docker exec leadgen_app python3 scripts/fire_calls.py [--limit N] [--dry-run]
"""
import asyncio, argparse, sys, os
sys.path.insert(0, "/opt/leadgen")
os.chdir("/opt/leadgen")

from dotenv import load_dotenv
load_dotenv("/opt/leadgen/.env", override=True)

parser = argparse.ArgumentParser()
parser.add_argument("--limit", type=int, default=10)
parser.add_argument("--dry-run", action="store_true")
args = parser.parse_args()

def normalise(ph):
    ph = ph.strip().lstrip("+")
    if ph.startswith("91") and len(ph) == 12:
        return "+" + ph
    if len(ph) == 10:
        return "+91" + ph
    return "+" + ph

def get_prospects(limit):
    import psycopg2, urllib.parse as up
    p = up.urlparse(os.environ["DATABASE_URL"])
    conn = psycopg2.connect(host=p.hostname, port=p.port or 5432,
        dbname=p.path.lstrip("/"), user=p.username, password=p.password)
    cur = conn.cursor()
    cur.execute("""SELECT phone, company_name, niche, city FROM leads
        WHERE phone IS NOT NULL AND phone != ''
        AND (call_attempts IS NULL OR call_attempts = 0)
        ORDER BY lead_score DESC NULLS LAST, created_at DESC
        LIMIT %s""", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [{"phone": r[0], "name": r[1] or "Business",
             "niche": r[2] or "general", "city": r[3] or ""} for r in rows]

async def fire(prospects, dry_run):
    from app.api.telephony_vobiz import start_stream_call
    ok = fail = skip = 0
    for p in prospects:
        phone = normalise(p["phone"])
        niche = p["niche"]
        print(f'  -> {phone} | {p["name"]} | {p["city"]} | niche={niche}', end=" ... ", flush=True)
        if dry_run:
            print("DRY")
            continue
        result = await start_stream_call(to=phone, niche=niche, call_type="promotional")
        if result.get("placed"):
            print("PLACED OK")
            ok += 1
        elif result.get("error") == "compliance_blocked":
            print("BLOCKED(DND/hours)")
            skip += 1
        else:
            body = result.get("vobiz_response", {}).get("body", {})
            print(f"FAIL  {result.get('error') or body}")
            fail += 1
        await asyncio.sleep(4)
    if not dry_run:
        print(f"\n=== placed={ok}  dnd_blocked={skip}  failed={fail} ===")

async def main():
    prospects = get_prospects(args.limit)
    print(f"Found {len(prospects)} uncontacted leads (limit={args.limit}, dry_run={args.dry_run})")
    if not prospects:
        print("No leads found.")
        return
    await fire(prospects, args.dry_run)

asyncio.run(main())
