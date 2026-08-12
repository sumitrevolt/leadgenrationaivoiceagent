"""Daily lead-pipeline automation — rescore, hot-lead surfacing, journey seed.

Rohan/Neha ke liye scheduled work: DB leads ko rescore karo, top hot leads
dashboard events me dikhao, journey rules empty hon to seed karo (disabled).
Kabhi raise nahi; scheduler/Celery safe.
"""

from __future__ import annotations

import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


async def run_daily() -> dict[str, Any]:
    """Mid-morning pipeline sweep (11:00 IST job)."""
    out: dict[str, Any] = {"ok": True}
    try:
        from app.platform import lead_scoring, team

        res = await lead_scoring.rescore_db(2000)
        out["rescore"] = res
        if res.get("ok"):
            team.log_event(
                "neha",
                "lead_rescore",
                f"♻️ {res.get('updated', 0)} leads rescored · {res.get('hot', 0)} hot (≥{res.get('threshold', 70)})",
                status="ok",
            )
        hot = await lead_scoring.top_hot_leads(10)
        out["hot"] = {"ok": hot.get("ok"), "hot_count": hot.get("hot_count", 0)}
        if hot.get("ok") and int(hot.get("hot_count") or 0) > 0:
            from app.platform import sales_qualify as _bant

            tops = []
            for ld in (hot.get("leads") or [])[:3]:
                label = (ld.get("name") or ld.get("business_name") or ld.get("phone") or "?")[:40]
                _g = _bant.bant_score(ld).get("grade", "?")
                tops.append(f"{label}({ld.get('lead_score', 0)}/{_g})")
            team.log_event(
                "rohan",
                "hot_leads",
                f"🔥 {hot['hot_count']} hot — top: {', '.join(tops)}",
                status="ok",
            )
    except Exception as e:
        logger.warning(f"[pipeline_ops] rescore/hot skip: {e}")
        out["rescore_error"] = str(e)[:200]

    try:
        if os.environ.get("JOURNEY_ENGINE", "0").strip().lower() in ("1", "true", "yes"):
            from app.marketing import journeys

            seeded = journeys.seed_defaults()
            activated = journeys.ensure_active_defaults()
            if seeded or activated:
                from app.platform import team

                team.log_event(
                    "neha",
                    "journey_seed",
                    f"📋 journeys seeded={seeded} activated={activated}",
                )
            out["journeys_seeded"] = seeded
            out["journeys_activated"] = activated
    except Exception as e:
        logger.debug(f"[pipeline_ops] journey seed skip: {e}")

    return out


async def run_afternoon_followups() -> dict[str, Any]:
    """Day-3/Day-7 email followups (hourly 9am-7pm IST) — naya cold batch nahi."""
    try:
        from app.platform import auto_outreach, team

        res = await auto_outreach.run_email_followups()
        sent = int((res or {}).get("sent") or 0)
        if sent:
            team.log_event("rohan", "email_followup", f"followups sent: {sent}", status="ok")
        return {"ok": True, **(res or {})}
    except Exception as e:
        logger.warning(f"[pipeline_ops] afternoon followups failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


__all__ = ["run_daily", "run_afternoon_followups"]
