"""
Team Scheduler — AI staff ke scheduled kaam (Asia/Kolkata time).
================================================================

Schedule (IST):
  - kavya  (ops health check) : har ghante, minute :05 pe
  - arjun  (QA run)           : roz 02:30
  - meera  (trainer analysis) : roz 03:00
  - isha   (SEO blog)         : roz 06:30 (3 naye niche articles → /blog, sitemap)
  - isha   (auto content)     : roz 07:00 (per-client social posts/posters → queue)
  - manager (daily digest)    : roz 08:30 (inquiries/prospects/QA/health → txt+email)
  - rohan  (client prospecting): roz 09:30 (Tier-1 prospects → outreach queue)
  - rohan  (email outreach)    : roz 10:30 (ready prospects ko auto cold email)

Loop har 60s tick karta hai; per-job "last ran" markers se har job apne
window me sirf EK baar fire hota hai (QA/trainer ke liye chhota catch-up
window bhi hai — restart raat ke window me ho to job miss na ho).

Wiring: main.py ke startup/lifespan me `start_scheduler()` call karo.
Off karna ho to env TEAM_AUTOMATION=0. Import-safe, kabhi raise nahi karta.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))
_TICK_S = 60

# Per-job "last ran" markers: ops -> "YYYY-MM-DD HH", baki -> "YYYY-MM-DD".
_last_ran: Dict[str, Optional[str]] = {
    "ops": None, "qa": None, "trainer": None, "prospect": None, "digest": None,
    "content": None, "email_outreach": None, "blog": None,
}


async def _run_job(job: str) -> None:
    """Ek staff job ko guarded chalao — scheduler kabhi nahi girta."""
    try:
        from app.agents import staff

        logger.info(f"[team-scheduler] running job: {job}")
        if job == "ops":
            await staff.run_ops()
        elif job == "qa":
            await staff.run_qa()
        elif job == "trainer":
            await staff.run_trainer()
        elif job == "digest":
            await staff.run_digest()
        elif job == "content":
            from app.marketing import auto_content

            await auto_content.run_daily_content()
        elif job == "blog":
            from app.marketing import seo_blog

            await seo_blog.run_daily_blog(3)
        elif job == "prospect":
            from app.platform import prospector

            await prospector.run_prospecting()
        elif job == "email_outreach":
            from app.platform import auto_outreach

            # Pehli baar wale prospects ko initial cold email, AUR purane
            # (emailed) prospects ko multi-touch follow-up — dono ek job me.
            await auto_outreach.run_email_outreach()
            await auto_outreach.run_email_followups()
    except Exception as e:
        logger.warning(f"[team-scheduler] job {job} failed: {e}")


async def scheduler_loop() -> None:
    """Infinite loop: 60s tick; IST schedule ke hisab se staff jobs fire karo."""
    logger.info(
        "[team-scheduler] loop started — ops hourly :05, QA daily 02:30, "
        "trainer daily 03:00, blog daily 06:30, content daily 07:00, "
        "digest daily 08:30, prospecting daily 09:30, email-outreach daily 10:30 (IST)"
    )
    while True:
        try:
            now = datetime.now(_IST)
            hour_key = now.strftime("%Y-%m-%d %H")
            day_key = now.strftime("%Y-%m-%d")
            hm = (now.hour, now.minute)

            # kavya — hourly at minute :05 (us ghante ke pehle tick >= :05 pe ek baar)
            if now.minute >= 5 and _last_ran["ops"] != hour_key:
                _last_ran["ops"] = hour_key
                await _run_job("ops")

            # arjun — daily 02:30 (catch-up window 02:30–04:00)
            if (2, 30) <= hm < (4, 0) and _last_ran["qa"] != day_key:
                _last_ran["qa"] = day_key
                await _run_job("qa")

            # meera — daily 03:00 (catch-up window 03:00–04:30)
            if (3, 0) <= hm < (4, 30) and _last_ran["trainer"] != day_key:
                _last_ran["trainer"] = day_key
                await _run_job("trainer")

            # manager — daily 08:30 digest (catch-up window 08:30–10:30)
            if (8, 30) <= hm < (10, 30) and _last_ran["digest"] != day_key:
                _last_ran["digest"] = day_key
                await _run_job("digest")

            # isha — daily 06:30 programmatic SEO blog (catch-up window 06:30–08:30)
            if (6, 30) <= hm < (8, 30) and _last_ran["blog"] != day_key:
                _last_ran["blog"] = day_key
                await _run_job("blog")

            # isha — daily 07:00 per-client social content (catch-up 07:00–09:00)
            if (7, 0) <= hm < (9, 0) and _last_ran["content"] != day_key:
                _last_ran["content"] = day_key
                await _run_job("content")

            # rohan — daily 09:30 client prospecting (catch-up window 09:30–11:30)
            if (9, 30) <= hm < (11, 30) and _last_ran["prospect"] != day_key:
                _last_ran["prospect"] = day_key
                await _run_job("prospect")

            # rohan — daily 10:30 auto email outreach (catch-up 10:30–12:30).
            # Flag/SMTP off ho to no-op (auto_outreach khud skip karta hai).
            if (10, 30) <= hm < (12, 30) and _last_ran["email_outreach"] != day_key:
                _last_ran["email_outreach"] = day_key
                await _run_job("email_outreach")
        except asyncio.CancelledError:  # graceful shutdown
            logger.info("[team-scheduler] loop cancelled")
            raise
        except Exception as e:
            logger.warning(f"[team-scheduler] tick failed: {e}")
        await asyncio.sleep(_TICK_S)


def start_scheduler() -> Optional["asyncio.Task[Any]"]:
    """Scheduler ko background task ki tarah start karo (running event loop
    chahiye — main.py startup/lifespan se call karo). TEAM_AUTOMATION=0 = off.
    Kabhi raise nahi karta; Task ya None return."""
    try:
        flag = "1"
        try:
            from app.config import settings  # settings me ho to wahi jeete
            flag = str(getattr(settings, "team_automation", None)
                       or os.environ.get("TEAM_AUTOMATION", "1"))
        except Exception:
            flag = os.environ.get("TEAM_AUTOMATION", "1")

        if flag.strip() == "0":
            logger.info("[team-scheduler] TEAM_AUTOMATION=0 — scheduler OFF")
            return None

        task = asyncio.create_task(scheduler_loop(), name="team-scheduler")
        try:
            from app.platform import team
            team.log_event(
                "manager",
                "automation_started",
                "Team scheduler on: ops hourly, QA 02:30, trainer 03:00, content 07:00, digest 08:30, prospecting 09:30, email-outreach 10:30",
            )
        except Exception:
            pass
        logger.info("[team-scheduler] started")
        return task
    except Exception as e:
        logger.warning(f"[team-scheduler] start failed: {e}")
        return None


__all__ = ["scheduler_loop", "start_scheduler"]
