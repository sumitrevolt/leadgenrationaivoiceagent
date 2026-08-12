#!/usr/bin/env python3
"""Continuous outbound cold-call loop (Vobiz stream).

Har batch me N fresh leads dial karta hai, batch ke baad wait, phir repeat —
TRAI window band hone tak ya max-batches.

Run (VPS container):
  docker exec -d leadgen_app python3 scripts/fire_calls_loop.py --batch-size 3 --platform
  docker exec leadgen_app python3 scripts/fire_calls_loop.py --batch-size 2 --platform --max-batches 5

Logs: stdout (docker logs leadgen_app ya nohup file).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import os
import sys

_BASE = (
    "/app" if os.path.isdir("/app") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _BASE)
os.chdir(_BASE)

from dotenv import load_dotenv

load_dotenv(os.path.join(_BASE, ".env"), override=True)

_scripts = os.path.join(_BASE, "scripts")
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

import fire_calls as fc  # noqa: E402


def _ist_now() -> datetime.datetime:
    return datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)


def _in_trai_window(call_type: str) -> tuple[bool, str]:
    ist = _ist_now()
    trai_start = int(os.environ.get("COMPLIANCE_PROMO_START", "10").split(":")[0])
    trai_end = int(os.environ.get("COMPLIANCE_PROMO_END", "19").split(":")[0])
    txn_end = int(os.environ.get("COMPLIANCE_TXN_END", "21").split(":")[0])
    start_hour = (
        int(os.environ.get("COMPLIANCE_TXN_START", "9").split(":")[0])
        if call_type == "transactional"
        else trai_start
    )
    end_hour = txn_end if call_type == "transactional" else trai_end
    ok = start_hour <= ist.hour < end_hour
    msg = f"IST {ist.strftime('%H:%M')} window {start_hour:02d}:00–{end_hour:02d}:00 ({call_type})"
    return ok, msg


async def _maybe_learn(learn: bool) -> None:
    if not learn:
        return
    try:
        import voice_learn_from_calls as vlc  # noqa: E402

        result = await vlc.learn_from_recent(limit=2)
        print(
            f"[loop] learn: {result.get('lessons_saved', 0)} lessons, score={result.get('avg_score')}"
        )
    except Exception as e:
        print(f"[loop] learn skip: {e}")


async def run_loop(
    batch_size: int,
    pause_batch_s: int,
    pause_empty_s: int,
    max_batches: int,
    platform: bool,
    transactional: bool,
    learn: bool,
    niche: str,
) -> None:
    call_type = "transactional" if transactional else "promotional"
    batch_n = 0
    total_ok = total_skip = total_fail = 0

    print(
        f"[loop] START batch_size={batch_size} platform={platform} "
        f"call_type={call_type} max_batches={max_batches or '∞'}"
    )

    while True:
        ok_win, win_msg = _in_trai_window(call_type)
        if not ok_win:
            print(f"[loop] TRAI window CLOSED — {win_msg}. Sleeping 10min.")
            await asyncio.sleep(600)
            continue

        if max_batches and batch_n >= max_batches:
            print(f"[loop] max_batches={max_batches} reached — stop.")
            break

        batch_n += 1
        niche_filter = "ai_marketing" if platform else niche
        prospects = fc.get_prospects(batch_size, niche_filter)
        print(f"\n[loop] === BATCH {batch_n} | {win_msg} | leads={len(prospects)} ===")

        if not prospects:
            print(f"[loop] no uncontacted leads — sleep {pause_empty_s}s")
            await asyncio.sleep(pause_empty_s)
            continue

        if batch_n == 1:
            try:
                tr = __import__(
                    "app.telephony.telephony_readiness", fromlist=["run_checks"]
                ).run_checks()
                score = int(tr.get("score") or 0)
                print(f"[loop] telephony readiness {score}/100 provider={tr.get('provider')}")
                if score < 70:
                    print("[loop] readiness too low — abort")
                    return
            except Exception as e:
                print(f"[loop] readiness warn: {e}")

        ok, skip, fail = await fc.fire_vobiz(
            prospects, dry_run=False, call_type=call_type, client_id="", platform=platform
        )
        total_ok += ok
        total_skip += skip
        total_fail += fail
        print(
            f"[loop] batch {batch_n} done: ok={ok} skip={skip} fail={fail} | totals ok={total_ok}"
        )

        await _maybe_learn(learn)

        # Calls complete hone do — batch ke baad buffer
        wait = max(pause_batch_s, batch_size * 35)
        print(f"[loop] sleeping {wait}s before next batch…")
        await asyncio.sleep(wait)


def main() -> None:
    p = argparse.ArgumentParser(description="Continuous outbound call loop")
    p.add_argument("--batch-size", type=int, default=3, help="Leads per batch")
    p.add_argument("--pause-batch", type=int, default=90, help="Seconds between batches")
    p.add_argument("--pause-empty", type=int, default=300, help="Seconds when no leads")
    p.add_argument("--max-batches", type=int, default=0, help="0 = until TRAI window closes")
    p.add_argument("--platform", action="store_true", help="LeadGen AI platform pitch")
    p.add_argument("--transactional", action="store_true")
    p.add_argument("--learn", action="store_true", help="Run voice_learn after each batch")
    p.add_argument("--niche", type=str, default="")
    args = p.parse_args()

    if fc._provider() != "vobiz":
        print(f"ERROR: provider={fc._provider()} — loop only supports vobiz stream path.")
        sys.exit(1)

    asyncio.run(
        run_loop(
            batch_size=max(1, args.batch_size),
            pause_batch_s=max(30, args.pause_batch),
            pause_empty_s=max(60, args.pause_empty),
            max_batches=max(0, args.max_batches),
            platform=args.platform,
            transactional=args.transactional,
            learn=args.learn,
            niche=args.niche,
        )
    )


if __name__ == "__main__":
    main()
