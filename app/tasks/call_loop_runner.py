"""
Call Loop Runner — runs inside Docker container.
Autonomous 5-Channel Continuous Telephony Dialer (Tata Smartflo).
Operates inside 09:00–20:00 IST promotional calling window.
Uses TelephonyService (unified facade) + ComplianceGate.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, time as dt_time, timedelta, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _sync_mark_called(lead_id: str):
    """Mark lead as called in DB to increment attempts and advance queue."""
    try:
        from app.models.base import get_db_session
        from app.models.lead import Lead

        with get_db_session() as db:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if lead:
                lead.mark_called()
                db.commit()
    except Exception as e:
        logger.warning(f"[call_loop] Could not mark lead {lead_id} called: {e}")


async def _mark_lead_called_in_db(lead_id: str):
    await asyncio.to_thread(_sync_mark_called, lead_id)


async def _get_pending_leads(limit: int = 5) -> list:
    """Get pending uncontacted leads with phone numbers from DB."""
    try:
        from app.models.base import get_db_session
        from app.tasks.calling import _get_campaign_prospects

        with get_db_session() as db:
            prospects = _get_campaign_prospects(db, limit, "all")
            return [
                {
                    "id": str(getattr(p, "id", "")),
                    "phone": str(getattr(p, "phone", "")),
                    "business_name": str(getattr(p, "business_name", "") or getattr(p, "name", "")),
                }
                for p in prospects
                if getattr(p, "phone", None)
            ]
    except Exception as e:
        logger.error(f"[call_loop] Failed to get leads from db: {e}")
        return []


async def run_call_loop():
    """Main call loop — runs inside container across 5 concurrent channels."""
    concurrency = int(os.getenv("CALL_LOOP_CONCURRENCY", os.getenv("TATA_SMARTFLO_MAX_CONCURRENT", "5")))
    cps_limit = float(os.getenv("TATA_SMARTFLO_CPS_LIMIT", "2.0"))
    stagger_delay = max(0.2, 1.0 / cps_limit if cps_limit > 0 else 0.5)
    interval_seconds = int(os.getenv("CALL_LOOP_INTERVAL_SECONDS", "5"))

    logger.info(
        f"[call_loop] STARTING autonomous call loop: {concurrency} concurrent channels, "
        f"CPS limit={cps_limit}, stagger={stagger_delay:.2f}s, loop_interval={interval_seconds}s"
    )

    # Import here to avoid circular imports
    try:
        from app.telephony.compliance import effective_promo_window, get_compliance_gate
        from app.telephony.telephony_service import get_telephony_service
    except ImportError as e:
        logger.error(f"[call_loop] Import error: {e}")
        sys.exit(1)

    compliance = get_compliance_gate()
    provider = get_telephony_service()

    # Log active provider
    logger.info(f"[call_loop] Active provider: {provider.provider}")

    # Check config via validation
    config = provider.validate_config()
    configured = config.get("configured", False)
    missing = config.get("missing", [])
    simulation_mode = config.get("simulation_mode", False)

    if not configured and not simulation_mode:
        logger.error(f"[call_loop] Provider not configured. Missing: {missing}")
        if provider.provider != "simulation":
            logger.info("[call_loop] Exiting due to missing provider credentials.")
            return

    batch_count = 0
    while True:
        try:
            # Check calling window (canonical compliance source of truth, 09:00 - 20:00 IST)
            now_utc = datetime.now(timezone.utc)
            now_ist = now_utc + timedelta(hours=5, minutes=30)
            start_str, end_str = effective_promo_window()
            start_h, start_m = map(int, start_str.split(":"))
            end_h, end_m = map(int, end_str.split(":"))
            in_window = dt_time(start_h, start_m) <= now_ist.time() < dt_time(end_h, end_m)

            if not in_window:
                logger.info(
                    f"[call_loop] Outside promotional calling window [{start_str}-{end_str} IST] "
                    f"(current IST {now_ist.strftime('%H:%M')}), sleeping 5min..."
                )
                await asyncio.sleep(300)
                continue

            # Fetch up to `concurrency` pending leads
            try:
                leads = await _get_pending_leads(limit=concurrency)
            except Exception as e:
                logger.error(f"[call_loop] Failed to get leads: {e}")
                await asyncio.sleep(60)
                continue

            if not leads:
                logger.info("[call_loop] No leads pending in dial queue, sleeping 30s...")
                await asyncio.sleep(30)
                continue

            batch_count += 1
            logger.info(f"[call_loop] Batch {batch_count}: Dialing {len(leads)} leads across {concurrency} channels concurrently")

            async def _dial_channel(ch_idx: int, lead: dict, delay: float) -> bool:
                if delay > 0:
                    await asyncio.sleep(delay)
                phone = lead.get("phone", "")
                lead_id = lead.get("id", "unknown")
                if not phone:
                    logger.warning(f"[call_loop][ch{ch_idx+1}] Lead {lead_id} has no phone, skipping")
                    return False
                try:
                    logger.info(f"[call_loop][ch{ch_idx+1}] Placing call to {phone} (lead {lead_id})...")
                    result = await provider.place_call(phone, call_type="promotional")
                    call_id = result.call_id
                    status = result.status
                    logger.info(f"[call_loop][ch{ch_idx+1}] Call response for {phone}: {status} (call_id: {call_id})")
                    if status in ("success", "queued", "initiated", "in-progress"):
                        await _mark_lead_called_in_db(lead_id)
                        return True
                    else:
                        logger.warning(f"[call_loop][ch{ch_idx+1}] Call rejected/failed for {phone}: {result.error or status}")
                        return False
                except Exception as e:
                    logger.error(f"[call_loop][ch{ch_idx+1}] Call exception for {phone}: {e}")
                    return False

            tasks = [
                _dial_channel(i, lead, i * stagger_delay)
                for i, lead in enumerate(leads)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            successful_calls = sum(1 for r in results if r is True)
            logger.info(f"[call_loop] Batch {batch_count} summary: {successful_calls}/{len(leads)} calls initiated")

            if successful_calls == 0 and leads:
                # All calls rejected or failed in this batch (e.g. carrier gateway inactive or 401/429)
                logger.warning(
                    "[call_loop] All calls in batch failed or rejected. "
                    "Backing off for 120s to protect carrier rate limits."
                )
                await asyncio.sleep(120)
            else:
                # Calls are actively going through! Continuous loop
                logger.info(f"[call_loop] Continuing to next batch in {interval_seconds}s...")
                await asyncio.sleep(interval_seconds)

        except KeyboardInterrupt:
            logger.info("[call_loop] Stopping on KeyboardInterrupt")
            break
        except Exception as e:
            logger.error(f"[call_loop] Unexpected error in call loop: {e}", exc_info=True)
            await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(run_call_loop())
