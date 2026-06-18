"""
LeadGen AI - Outbound call campaign
leads DB se numbers → AI call via active telephony provider (Exotel or Vobiz).

Run:
  docker exec leadgen_app python3 scripts/fire_calls.py --limit 10 --dry-run
  docker exec leadgen_app python3 scripts/fire_calls.py --limit 5 --transactional
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import uuid

_BASE = "/app" if os.path.isdir("/app") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BASE)
os.chdir(_BASE)

from dotenv import load_dotenv

load_dotenv(os.path.join(_BASE, ".env"), override=True)

parser = argparse.ArgumentParser()
parser.add_argument("--limit", type=int, default=10)
parser.add_argument("--dry-run", action="store_true")
parser.add_argument("--niche", type=str, default="")
parser.add_argument("--client-id", type=str, default="", help="Campaign client (clients_store id) -> bot greets as that business + niche")
parser.add_argument(
    "--transactional",
    action="store_true",
    help="Consented/inbound style — looser compliance window (no DLT promo gate)",
)
args = parser.parse_args()


def phone10(ph: str) -> str:
    return re.sub(r"\D", "", (ph or "").strip())[-10:]


def _provider() -> str:
    try:
        from app.config import settings

        return (
            os.environ.get("TELEPHONY_PROVIDER") or settings.default_telephony or "exotel"
        ).strip().lower()
    except Exception:
        return (os.environ.get("TELEPHONY_PROVIDER") or "exotel").strip().lower()


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


async def fire_vobiz(prospects: list[dict], dry_run: bool, call_type: str, client_id: str = "") -> tuple[int, int, int]:
    from app.api.telephony_vobiz import start_stream_call
    from app.telephony.vobiz_handler import VobizClient

    client = VobizClient()
    if not dry_run and not client.available():
        print("ERROR: Vobiz not configured — VOBIZ_AUTH_ID + VOBIZ_AUTH_TOKEN set karo.")
        return 0, 0, len(prospects)

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

        result = await start_stream_call(to="+91" + p10, niche=niche, call_type=call_type, client_id=client_id or None)
        if result.get("placed"):
            print("PLACED OK")
            mark_called(p["phone"])
            ok += 1
        elif result.get("error") == "compliance_blocked":
            print("BLOCKED(compliance)")
            skip += 1
        else:
            body = result.get("vobiz_response", {}).get("body", {})
            print(f"FAIL  {result.get('error') or body}")
            fail += 1
        await asyncio.sleep(4)
    return ok, skip, fail


async def fire_exotel(prospects: list[dict], dry_run: bool, call_type: str) -> tuple[int, int, int]:
    from app.telephony.call_manager import CallManager, CallRequest

    provider = _provider()
    if provider not in ("exotel", "twilio"):
        provider = "exotel"

    if dry_run:
        for p in prospects:
            p10 = phone10(p["phone"])
            print(f'  -> +91{p10} | {p["name"]} | {p.get("city","")} | niche={p.get("niche","general")} ... DRY')
        return 0, 0, 0

    cm = CallManager(provider=provider)
    proc = asyncio.create_task(cm.start_call_processor())
    ok = fail = skip = 0
    try:
        for p in prospects:
            p10 = phone10(p["phone"])
            niche = p.get("niche") or "general"
            print(
                f'  -> +91{p10} | {p["name"]} | {p.get("city","")} | niche={niche}',
                end=" ... ",
                flush=True,
            )
            if not p10 or len(p10) != 10:
                print("SKIP(invalid phone)")
                skip += 1
                continue
            phone = p["phone"] if str(p["phone"]).startswith("+") else "+91" + p10
            req = CallRequest(
                lead_id=str(uuid.uuid4())[:12],
                phone_number=phone,
                campaign_id=f"fire_{niche}",
                niche=niche,
                client_name=p.get("name") or "LeadGen AI",
                client_service=niche.replace("_", " ").title(),
                script_name=niche,
                lead_data={"company_name": p.get("name"), "city": p.get("city", "")},
                call_type=call_type,
                priority=3,
            )
            call_id = await cm.queue_call(req)
            if call_id.startswith("compliance") or call_id.startswith("out_of"):
                print(f"BLOCKED({call_id})")
                skip += 1
            elif call_id.startswith("compliance_error"):
                print(f"BLOCKED({call_id})")
                skip += 1
            else:
                print(f"QUEUED {call_id}")
                mark_called(p["phone"])
                ok += 1
            await asyncio.sleep(6)
        wait_s = min(max(len(prospects) * 25, 30), 300)
        print(f"Waiting {wait_s}s for calls to complete…")
        await asyncio.sleep(wait_s)
    finally:
        proc.cancel()
        try:
            await proc
        except asyncio.CancelledError:
            pass
    return ok, skip, fail


async def fire(prospects: list[dict], dry_run: bool, call_type: str, client_id: str = "") -> None:
    provider = _provider()
    print(f"Provider: {provider} | call_type={call_type}")
    if provider == "vobiz":
        ok, skip, fail = await fire_vobiz(prospects, dry_run, call_type, client_id)
    else:
        ok, skip, fail = await fire_exotel(prospects, dry_run, call_type)
    if not dry_run:
        print(f"\n=== placed/queued={ok}  blocked/skipped={skip}  failed={fail} ===")


async def main() -> None:
    import datetime

    ist = datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)
    trai_start = int(os.environ.get("COMPLIANCE_PROMO_START", "10").split(":")[0])
    trai_end = int(os.environ.get("COMPLIANCE_PROMO_END", "19").split(":")[0])
    txn_end = int(os.environ.get("COMPLIANCE_TXN_END", "21").split(":")[0])
    call_type = "transactional" if args.transactional else "promotional"
    end_hour = txn_end if args.transactional else trai_end
    start_hour = (
        int(os.environ.get("COMPLIANCE_TXN_START", "9").split(":")[0])
        if args.transactional
        else trai_start
    )
    if not args.dry_run and not (start_hour <= ist.hour < end_hour):
        print(
            f"ERROR: TRAI window CLOSED (IST {ist.hour}:xx). "
            f"Allowed {start_hour:02d}:00–{end_hour:02d}:00 IST for {call_type}."
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
            print(f"Telephony readiness OK ({score}/100, provider={tr.get('provider')})")
        except Exception as e:
            print(f"WARN: readiness check skip: {e}")

    prospects = get_prospects(args.limit, args.niche)
    print(
        f"Found {len(prospects)} uncontacted leads "
        f"(limit={args.limit}, dry_run={args.dry_run}, niche={args.niche or 'all'}, "
        f"call_type={call_type})"
    )
    if not prospects:
        print("No leads found.")
        return
    await fire(prospects, args.dry_run, call_type, args.client_id)


if __name__ == "__main__":
    asyncio.run(main())
