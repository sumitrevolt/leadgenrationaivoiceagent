"""
LeadGen AI - Outbound call campaign
leads DB se numbers → AI call via Tata SmartFlo (Vobiz + Jio removed 2026-09-15).

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

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BASE)

from dotenv import load_dotenv

# .env resolution: container me /app/.env nahi hota — actual file /opt/leadgen/.env
# pe hai (VPS install path). Multiple locations try karo, first existing wins.
for _env_dir in (_BASE, "/opt/leadgen", "/app"):
    _env_path = os.path.join(_env_dir, ".env")
    if os.path.exists(_env_path):
        load_dotenv(_env_path, override=True)
        break
os.chdir(_BASE)

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
            (os.environ.get("TELEPHONY_PROVIDER") or settings.default_telephony or "tata_smartflo")
            .strip()
            .lower()
        )
    except Exception:
        # Vobiz + Exotel removed 2026-09-15 — the stale default now picks the
        # sole live provider (Tata SmartFlo) whenever settings failed to import.
        return (os.environ.get("TELEPHONY_PROVIDER") or "tata_smartflo").strip().lower()


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


def get_prospects(limit: int, niche: str = "", exclude: set | None = None) -> list[dict]:
    conn = get_db_conn()
    cur = conn.cursor()
    # MOBILE-only pre-filter (2026-08-30 PILOT): dial_gate ka phone_type_gate
    # FIXED_LINE/TOLL_FREE ko promotional pe block karta hai -> top-score leads
    # (mostly CA/business links) hamesha SKIP(phone_type_blocked) hote the aur
    # loop leads=0 / skip-loop me phas jata tha. SQL me hi valid IN mobile-fmt
    # numbers select karo (regex reuses OPS-004 verified pattern; phonenumbers
    # lib authority bhi isi se MILTI hai kyunki 91 prefix valid IN mobiles hi
    # dial_gate me pass karte hain). Gate INTACT (PHONE_TYPE_GATE=1), policy
    # compliant (promo dial sirf person-reachable mobile). Compliance safe hai.
    mobile_where = "phone ~ '(^|\\+)(91)9[0-9]{9}$'"
    # 2026-09-15 PLT-156 ROTATION: caller passes `exclude` (set of phone10s
    # already attempted this run). We fetch a WIDER window and filter
    # out excluded + same-number duplicates in Python. This breaks the
    # infinite "same top-N → all already-claimed → skip" loop.
    exclude10 = set(exclude or ())
    fetch = limit + len(exclude10) + 20
    if niche:
        cur.execute(
            f"""SELECT phone, company_name, niche, city FROM leads
            WHERE phone IS NOT NULL AND phone != ''
            AND (call_attempts IS NULL OR call_attempts = 0)
            AND {mobile_where}
            AND LOWER(COALESCE(niche,'')) = LOWER(%s)
            ORDER BY lead_score DESC NULLS LAST, created_at DESC
            LIMIT %s""",
            (niche, fetch),
        )
    else:
        cur.execute(
            f"""SELECT phone, company_name, niche, city FROM leads
            WHERE phone IS NOT NULL AND phone != ''
            AND (call_attempts IS NULL OR call_attempts = 0)
            AND {mobile_where}
            ORDER BY lead_score DESC NULLS LAST, created_at DESC
            LIMIT %s""",
            (fetch,),
        )
    rows = cur.fetchall()
    conn.close()
    out: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        p10 = phone10(r[0])
        if not p10 or p10 in seen or p10 in exclude10:
            continue
        seen.add(p10)
        out.append(
            {
                "phone": r[0],
                "name": r[1] or "Business",
                "niche": r[2] or "general",
                "city": r[3] or "",
            }
        )
        if len(out) >= limit:
            break
    return out
    
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


async def fire_queue(
    prospects: list[dict],
    dry_run: bool,
    call_type: str,
    provider: str | None = None,
) -> tuple[int, int, int]:
    """Queue-based dialer — provider-agnostic (CallManager picks the client).

    Used for every non-Vobiz provider (tata_smartflo today). Compliance is
    NOT bypassed here: CallManager.queue_call() runs dial_gate ->
    ComplianceGate -> admin kill switch before anything is enqueued, and
    the provider client re-checks the same gates inside place_call().
    """
    from app.telephony.call_manager import CallManager, CallRequest

    provider = (provider or _provider()).strip().lower()
    if provider != "tata_smartflo":
        print(f"ERROR: provider '{provider}' not supported — Vobiz was REMOVED 2026-09-15. Set TELEPHONY_PROVIDER=tata_smartflo.")
        return 0, len(prospects), 0

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
    # Vobiz removed 2026-09-15 — every provider now routes through the queue dialer
    # (CallManager → Tata SmartFlo provider client).
    ok, skip, fail = await fire_queue(prospects, dry_run, call_type, provider)
    if not dry_run:
        print(f"\n=== placed/queued={ok}  blocked/skipped={skip}  failed={fail} ===")


# Back-compat alias: the exotel path was deleted with the provider, but the
# name is still referenced from ops scripts/notes. Signature is identical.
fire_exotel = fire_queue


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
