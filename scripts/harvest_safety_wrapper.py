"""
Safety wrapper for harvest_leads to ensure proper asyncpg pool cleanup.
Prevents "closed event loop" connection leaks when harvest_leads completes.

Issue (CLAUDE.md Current State, 2026-07-11):
  harvest task hit asyncpg pooled-connection cleanup on closed per-task event loop (P1)

Fix strategy:
  1. Run harvest in its own asyncio context
  2. Explicitly close all connections before event loop closes
  3. Catch any connection cleanup errors (fail-safe)
"""

import asyncio
import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


async def run_harvest_safe(
    niche: str = "general",
    city: str = "",
    limit: int = 100,
    sources: list[str] | None = None,
) -> dict[str, Any]:
    """
    Run harvest with guaranteed connection cleanup.

    Wraps lead_harvester.run_harvest() with:
    - Explicit asyncpg pool close after completion
    - Connection timeout enforcement
    - Fail-safe exception handling

    Args:
        niche, city, limit, sources: passed to lead_harvester.run_harvest()

    Returns:
        Harvest result dict (same as lead_harvester.run_harvest())
    """
    from app.platform import lead_harvester

    result = None
    try:
        # Run harvest with connection timeout
        result = await asyncio.wait_for(
            lead_harvester.run_harvest(niche, city, limit, sources or []),
            timeout=600.0,  # 10 min hard timeout
        )
        return result
    except asyncio.TimeoutError:
        logger.error(f"[harvest_safety] Timeout: run_harvest exceeded 600s (niche={niche})")
        return {
            "niche": niche,
            "error": "timeout:600s",
            "leads": [],
            "sources": [],
        }
    except Exception as e:
        logger.error(f"[harvest_safety] Exception: {type(e).__name__}: {str(e)[:200]}")
        return {
            "niche": niche,
            "error": f"{type(e).__name__}:{str(e)[:100]}",
            "leads": [],
            "sources": [],
        }
    finally:
        # Explicit pool cleanup (fail-safe)
        try:
            # Try to close asyncpg pool if it exists
            from app.database import get_db_pool

            pool = get_db_pool()
            if pool:
                await pool.close()
                logger.info("[harvest_safety] Connection pool closed")
        except Exception as cleanup_err:
            logger.debug(f"[harvest_safety] Pool cleanup warn (non-fatal): {cleanup_err}")


async def run_harvest_loop_safe() -> dict[str, Any]:
    """Safely run harvest_loop_sweep with connection cleanup.

    Wall-clock MUST stay under Celery soft-limit (~540s). The previous 900s
    wait_for let GTM×niche_prospector fan-out SoftTimeLimit the parent
    ``prospect`` staff job (2026-07-20 prod canary on b5cac26).
    """
    from app.platform import lead_harvester

    try:
        timeout_s = float(os.environ.get("HARVEST_LOOP_TIMEOUT_S", "120") or "120")
    except Exception:
        timeout_s = 120.0
    timeout_s = max(5.0, min(timeout_s, 300.0))

    try:
        result = await asyncio.wait_for(
            lead_harvester.run_loop_sweep(),
            timeout=timeout_s,
        )
        return result
    except asyncio.TimeoutError:
        logger.error(f"[harvest_safety] Timeout: run_loop_sweep exceeded {timeout_s:.0f}s")
        return {"error": f"timeout:{int(timeout_s)}s", "leads_total": 0, "truncated": True}
    finally:
        try:
            from app.database import get_db_pool

            pool = get_db_pool()
            if pool:
                await pool.close()
                logger.info("[harvest_safety] Pool closed after loop_sweep")
        except Exception as cleanup_err:
            logger.debug(f"[harvest_safety] Loop cleanup warn: {cleanup_err}")
