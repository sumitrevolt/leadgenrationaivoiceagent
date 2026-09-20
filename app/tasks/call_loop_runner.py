"""
Call Loop Runner ??? runs inside Docker container.
Entry point for platform_dial scheduler.
Uses TelephonyService (unified facade) + ComplianceGate.
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def run_call_loop():
    """Main call loop ??? runs inside container."""
    logger.info("[call_loop] STARTING call loop service...")

    # Import here to avoid circular imports
    try:
        from app.telephony.compliance import get_compliance_gate
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
        logger.info("[call_loop] Will run in simulation mode or exit...")
        if provider.provider != "simulation":
            return

    batch_count = 0
    while True:
        try:
            # Check calling window (canonical compliance source of truth)
            from datetime import time as dt_time

            from app.telephony.compliance import effective_promo_window

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

            # Get pending leads from platform dial queue
            try:
                leads = await _get_pending_leads()
            except Exception as e:
                logger.error(f"[call_loop] Failed to get leads: {e}")
                await asyncio.sleep(60)
                continue

            if not leads:
                logger.info("[call_loop] No leads pending, sleeping 1min...")
                await asyncio.sleep(60)
                continue

            logger.info(f"[call_loop] Batch {batch_count + 1}: {len(leads)} leads")

            batch_success = False
            for lead in leads:
                phone = lead.get("phone", "")
                lead_id = lead.get("id", "unknown")

                if not phone:
                    logger.warning(f"[call_loop] Lead {lead_id} has no phone, skipping")
                    continue

                # Place call (compliance gate is inside place_call)
                try:
                    result = await provider.place_call(phone, call_type="promotional")
                    call_id = result.call_id
                    status = result.status
                    logger.info(f"[call_loop] Called {phone}: {status} ({call_id})")
                    if status in ("success", "queued", "initiated", "in-progress"):
                        batch_success = True
                except Exception as e:
                    logger.error(f"[call_loop] Call failed {phone}: {e}")

            batch_count += 1
            if not batch_success and leads:
                logger.warning(
                    "[call_loop] Batch unsuccessful (rejected or failed). "
                    "Backing off for 120s to protect carrier rate limits."
                )
                await asyncio.sleep(120)
            else:
                await asyncio.sleep(30)

        except KeyboardInterrupt:
            logger.info("[call_loop] Stopping on KeyboardInterrupt")
            break
        except Exception as e:
            logger.error(f"[call_loop] Error: {e}", exc_info=True)
            await asyncio.sleep(60)


async def _get_pending_leads(limit: int = 3) -> list:
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


if __name__ == "__main__":
    asyncio.run(run_call_loop())
