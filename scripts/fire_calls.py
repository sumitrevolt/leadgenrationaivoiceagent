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

_BASE = (
    "/app" if os.path.isdir("/app") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _BASE)
os.chdir(_BASE)

from dotenv import load_dotenv

load_dotenv(os.path.join(_BASE, ".env"), override=True)

parser = argparse.ArgumentParser()
parser.add_argument("--limit", type=int, default=10)
parser.add_argument("--dry-run", action="store_true")
parser.add_argument("--niche", type=str, default="")
parser.add_argument(
    "--client-id",
    type=str,
    default="",
    help="Campaign client (clients_store id) -> bot greets as that business + niche",
)
parser.add_argument(
    "--transactional",
    action="store_true",
    help="Consented/inbound style — looser compliance window (no DLT promo gate)",
)
parser.add_argument(
    "--platform",
    action="store_true",
    help="LeadGen AI platform pitch — force niche=ai_marketing (Swara structured opener)",
)


def phone10(ph: str) -> str:
    return re.sub(r"\D", "", (ph or "").strip())[-10:]


def _provider() -> str:
    try:
        from app.config import settings

        return (
            (os.environ.get("TELEPHONY_PROVIDER") or settings.default_telephony or "exotel")
            .strip()
            .lower()
        )
    except Exception:
        return (os.environ.get("TELEPHONY_PROVIDER") or "exotel").strip().lower()


def get_db_conn():
    import urllib.parse as up

    import psycopg2

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
    # MOBILE-only pre-filter (2026-08-30 PILOT): dial_gate ka phone_type_gate
    # FIXED_LINE/TOLL_FREE ko promotional pe block karta hai -> top-score leads
    # (mostly CA/landline niches) hamesha SKIP(phone_type_blocked) hote the aur
    # loop leads=0 / skip-loop me phas jata tha. SQL me hi sirf valid IN MOBILE
    # numbers select karo — gate INTACT (PHONE_TYPE_GATE=1), promotiona dial
    # policy bhi compliant (mobile = person reachable). Compliance safe hai.
    mobile_where = "phone ~ '^\\+?91[6-9][0-9]{9}$'"
    if niche:
        cur.execute(
            f"""SELECT phone, company_name, niche, city FROM leads
            WHERE phone IS NOT NULL AND phone != ''
            AND (call_attempts IS NULL OR call_attempts = 0)
            AND {mobile_where}
            AND LOWER(COALESCE(niche,'')) = LOWER(%s)
            ORDER BY lead_score DESC NULLS LAST, created_at DESC
            LIMIT %s""",
            (niche, limit),
        )
    else:
        cur.execute(
            f"""SELECT phone, company_name, niche, city FROM leads
            WHERE phone IS NOT NULL AND phone != ''
            AND (call_attempts IS NULL OR call_attempts = 0)
            AND {mobile_where}
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


async def fire_vobiz(
    prospects: list[dict],
    dry_run: bool,
    call_type: str,
    client_id: str = "",
    platform: bool = False,
) -> tuple[int, int, int]:
    from app.api.telephony_vobiz import start_stream_call
    from app.telephony import voice_launch as vl
    from app.telephony.vobiz_handler import VobizClient

    client = VobizClient()
    if not dry_run and not client.available():
        print("ERROR: Vobiz not configured — VOBIZ_AUTH_ID + VOBIZ_AUTH_TOKEN set karo.")
        return 0, 0, len(prospects)

    # Controlled-launch spine parity (2026-08-02): Celery path ke same session
    # limiter — exactly VOICE_CALLS_PER_SESSION per session, fail-CLOSED. Subprocess
    # fallback me bhi 31st attempt provider boundary se PEHLE block.
    spine_on = vl.campaign_enabled()
    session_id = None
    if spine_on and not dry_run:
        session_id = await vl.current_session_id()
        if not session_id:
            session_id = await vl.create_voice_session(owner="cli", niche="", label="fire_calls")
        if not session_id:
            print("BLOCKED(no_session) — voice launch session unavailable (Redis?)")
            return 0, len(prospects), 0
        if await vl.session_is_stopped(session_id):
            print("BLOCKED(session_stopped)")
            return 0, len(prospects), 0

    ok = fail = skip = 0
    for p in prospects:
        p10 = phone10(p["phone"])
        niche = "ai_marketing" if platform else (p.get("niche") or "general")
        cid = "" if platform else client_id
        print(
            f"  -> +91{p10} | {p['name']} | {p['city']} | niche={niche}",
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

        if spine_on:
            # eligibility (compose ke samay ke chokepoints) — fail-closed
            elig = await vl.is_lead_eligible_for_voice_call("+91" + p10, call_type)
            if not elig.eligible:
                print(f"SKIP({elig.reason})")
                await vl.record_session_disposition(session_id, vl.VoiceDisposition.SKIPPED)
                skip += 1
                continue
            sslot = await vl.reserve_session_slot(session_id)
            if not sslot.ok:
                await vl.record_session_disposition(session_id, vl.VoiceDisposition.SKIPPED)
                print(f"BLOCKED({sslot.reason})")
                skip += 1
                break
            if not await vl.session_idem_claim(session_id, f"lead:{p['phone']}"):
                await vl.release_session_slot(session_id)
                await vl.record_session_retry_blocked(session_id)
                print("SKIP(already_dispatched_this_session)")
                skip += 1
                continue

        result = await start_stream_call(
            to="+91" + p10, niche=niche, call_type=call_type, client_id=cid or None
        )
        if result.get("placed"):
            print("PLACED OK")
            mark_called(p["phone"])
            ok += 1
        elif result.get("error") == "compliance_blocked":
            print("BLOCKED(compliance)")
            if spine_on:
                await vl.release_session_slot(session_id)
                await vl.session_idem_release(session_id, f"lead:{p['phone']}")
                await vl.record_session_disposition(session_id, vl.VoiceDisposition.SKIPPED)
            skip += 1
        else:
            body = result.get("vobiz_response", {}).get("body", {})
            print(f"FAIL  {result.get('error') or body}")
            if spine_on:
                await vl.record_session_disposition(session_id, vl.VoiceDisposition.FAILED)
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
            print(
                f"  -> +91{p10} | {p['name']} | {p.get('city', '')} | niche={p.get('niche', 'general')} ... DRY"
            )
        return 0, 0, 0

    cm = CallManager(provider=provider)
    proc = asyncio.create_task(cm.start_call_processor())
    ok = fail = skip = 0
    try:
        for p in prospects:
            p10 = phone10(p["phone"])
            niche = p.get("niche") or "general"
            print(
                f"  -> +91{p10} | {p['name']} | {p.get('city', '')} | niche={niche}",
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


async def fire(
    prospects: list[dict],
    dry_run: bool,
    call_type: str,
    client_id: str = "",
    platform: bool = False,
) -> None:
    provider = _provider()
    print(f"Provider: {provider} | call_type={call_type} | platform_pitch={platform}")
    if provider == "vobiz":
        ok, skip, fail = await fire_vobiz(prospects, dry_run, call_type, client_id, platform)
    else:
        ok, skip, fail = await fire_exotel(prospects, dry_run, call_type)
    if not dry_run:
        print(f"\n=== placed/queued={ok}  blocked/skipped={skip}  failed={fail} ===")


async def main() -> None:
    args = parser.parse_args()
    from app.telephony.campaign_compliance import call_type_for, readiness_ok, trai_window_ok

    call_type = call_type_for(args.transactional)

    if not args.dry_run:
        ok, reason = trai_window_ok(args.transactional)
        if not ok:
            print(f"ERROR: {reason}")
            return

    if not args.dry_run:
        ready, score, actions = readiness_ok()
        if not ready:
            print(f"ERROR: Telephony readiness {score}/100 — fix before live calls:")
            for act in actions:
                print(f"  → {act}")
            return
        print(f"Telephony readiness OK ({score}/100)")

    niche_filter = "ai_marketing" if args.platform else args.niche
    prospects = get_prospects(args.limit, niche_filter)
    print(
        f"Found {len(prospects)} uncontacted leads "
        f"(limit={args.limit}, dry_run={args.dry_run}, niche={niche_filter or 'all'}, "
        f"platform={args.platform}, call_type={call_type})"
    )
    if not prospects:
        print("No leads found.")
        return
    await fire(prospects, args.dry_run, call_type, args.client_id, args.platform)


if __name__ == "__main__":
    asyncio.run(main())
