"""
LeadGen AI - Outbound call campaign (Vobiz)
leads DB se numbers → Swara AI stream call via Vobiz.
Run: docker exec leadgen_app python3 scripts/fire_calls.py [--limit N] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys

_BASE = "/app" if os.path.isdir("/app") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BASE)
os.chdir(_BASE)

from dotenv import load_dotenv

load_dotenv(os.path.join(_BASE, ".env"), override=True)

parser = argparse.ArgumentParser()
parser.add_argument("--limit", type=int, default=10)
parser.add_argument("--dry-run", action="store_true")
parser.add_argument("--niche", type=str, default="")
args = parser.parse_args()


def phone10(ph: str) -> str:
    return re.sub(r"\D", "", (ph or "").strip())[-10:]


def get_db_conn():
    import psycopg2
    import urllib.parse as up

    p = up.urlparse(os.environ["DATABASE_URL"])
    return psycopg2.connect(
        host=p.hostname,
        port=p.port or 5432,
        dbname=p.path.lstrip("/"),
        user=p.username,
        password=p.password,
    )


def get_prospects(limit: int, niche: str = "") -> list[dict]:
    conn = get_db_conn()
    cur = conn.cursor()
    if niche:
        cur.execute(
            """SELECT phone, company_name, niche, city FROM leads
            WHERE phone IS NOT NULL AND phone != ''
            AND (call_attempts IS NULL OR call_attempts = 0)
            AND LOWER(COALESCE(niche,'')) = LOWER(%s)
            ORDER BY lead_score DESC NULLS LAST, created_at DESC
            LIMIT %s""",
            (niche, limit),
        )
    else:
        cur.execute(
            """SELECT phone, company_name, niche, city FROM leads
            WHERE phone IS NOT NULL AND phone != ''
            AND (call_attempts IS NULL OR call_attempts = 0)
            ORDER BY lead_score DESC NULLS LAST, created_at DESC
            LIMIT %s""",
            (limit,),
        )
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "phone": r[0],
            "name": r[1] or "Business",
            "niche": r[2] or "general",
            "city": r[3] or "",
        }
        for r in rows
    ]


def mark_called(phone_raw: str) -> None:
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            """UPDATE leads SET call_attempts = COALESCE(call_attempts,0)+1,
            last_called_at = NOW() WHERE phone = %s""",
            (phone_raw,),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"  [warn] DB mark_called failed: {e}")


async def fire(prospects: list[dict], dry_run: bool) -> None:
    from app.api.telephony_vobiz import start_stream_call
    from app.telephony.vobiz_handler import VobizClient

    client = VobizClient()
    if not dry_run and not client.available():
        print("ERROR: Vobiz not configured — VOBIZ_AUTH_ID + VOBIZ_AUTH_TOKEN set karo.")
        return

    ok = fail = skip = 0
    for p in prospects:
        p10 = phone10(p["phone"])
        niche = p.get("niche") or "general"
        print(
            f'  -> +91{p10} | {p["name"]} | {p["city"]} | niche={niche}',
            end=" ... ",
            flush=True,
        )
        if dry_run:
            print("DRY")
            continue
        if not p10 or len(p10) != 10:
            print("SKIP(invalid phone)")
            skip += 1
            continue

        result = await start_stream_call(
            to="+91" + p10, niche=niche, call_type="promotional"
        )
        if result.get("placed"):
            print("PLACED OK")
            mark_called(p["phone"])
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


async def main() -> None:
    import datetime

    ist = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
    trai_start = int(os.environ.get("COMPLIANCE_PROMO_START", "10").split(":")[0])
    trai_end = int(os.environ.get("COMPLIANCE_PROMO_END", "19").split(":")[0])
    if not args.dry_run and not (trai_start <= ist.hour < trai_end):
        print(
            f"ERROR: TRAI window CLOSED (IST {ist.hour}:xx). "
            f"Allowed {trai_start:02d}:00–{trai_end:02d}:00 IST only."
        )
        return

    if not args.dry_run:
        try:
            from app.telephony.telephony_readiness import run_checks

            tr = run_checks()
            score = int(tr.get("score") or 0)
            if score < 70:
                print(f"ERROR: Telephony readiness {score}/100 — fix before live calls:")
                for act in tr.get("actions") or []:
                    print(f"  → {act}")
                return
            print(f"Telephony readiness OK ({score}/100, provider={tr.get('provider', 'vobiz')})")
        except Exception as e:
            print(f"WARN: readiness check skip: {e}")

    prospects = get_prospects(args.limit, args.niche)
    print(
        f"Found {len(prospects)} uncontacted leads "
        f"(limit={args.limit}, dry_run={args.dry_run}, niche={args.niche or 'all'})"
    )
    if not prospects:
        print("No leads found.")
        return
    await fire(prospects, args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
