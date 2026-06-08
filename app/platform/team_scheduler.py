from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))
_TICK_S = 60

_last_ran: dict[str, str | None] = {
    "growth": None,
    "ops": None,
    "qa": None,
    "trainer": None,
    "prospect": None,
    "digest": None,
    "content": None,
    "email_outreach": None,
    "blog": None,
}


async def _run_job(job: str) -> None:
    try:
        from app.agents import staff

        logger.info(f"[team-scheduler] running job: {job}")
        if job == "growth":
            from app.platform import growth_engine

            await growth_engine.pulse()
        elif job == "ops":
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

            await auto_outreach.run_email_outreach()
            await auto_outreach.run_email_followups()
    except Exception as e:
        logger.warning(f"[team-scheduler] job {job} failed: {e}")


async def scheduler_loop() -> None:
    logger.info("[team-scheduler] loop started (growth 15min + dailies)")
    while True:
        try:
            now = datetime.now(_IST)
            hour_key = now.strftime("%Y-%m-%d %H")
            day_key = now.strftime("%Y-%m-%d")
            hm = (now.hour, now.minute)

            slot_min = (now.minute // 15) * 15
            slot_key = now.strftime("%Y-%m-%d %H:") + f"{slot_min:02d}"
            if _last_ran.get("growth") != slot_key:
                _last_ran["growth"] = slot_key
                await _run_job("growth")

            if now.minute >= 5 and _last_ran["ops"] != hour_key:
                _last_ran["ops"] = hour_key
                await _run_job("ops")
            if (2, 30) <= hm < (4, 0) and _last_ran["qa"] != day_key:
                _last_ran["qa"] = day_key
                await _run_job("qa")
            if (3, 0) <= hm < (4, 30) and _last_ran["trainer"] != day_key:
                _last_ran["trainer"] = day_key
                await _run_job("trainer")
            if (8, 30) <= hm < (10, 30) and _last_ran["digest"] != day_key:
                _last_ran["digest"] = day_key
                await _run_job("digest")
            if (6, 30) <= hm < (8, 30) and _last_ran["blog"] != day_key:
                _last_ran["blog"] = day_key
                await _run_job("blog")
            if (7, 0) <= hm < (9, 0) and _last_ran["content"] != day_key:
                _last_ran["content"] = day_key
                await _run_job("content")
            if (9, 30) <= hm < (11, 30) and _last_ran["prospect"] != day_key:
                _last_ran["prospect"] = day_key
                await _run_job("prospect")
            if (10, 30) <= hm < (12, 30) and _last_ran["email_outreach"] != day_key:
                _last_ran["email_outreach"] = day_key
                await _run_job("email_outreach")
        except asyncio.CancelledError:
            logger.info("[team-scheduler] loop cancelled")
            raise
        except Exception as e:
            logger.warning(f"[team-scheduler] tick failed: {e}")
        await asyncio.sleep(_TICK_S)


def start_scheduler() -> asyncio.Task[Any] | None:
    try:
        flag = "1"
        try:
            from app.config import settings

            flag = str(getattr(settings, "team_automation", None) or os.environ.get("TEAM_AUTOMATION", "1"))
        except Exception:
            flag = os.environ.get("TEAM_AUTOMATION", "1")
        if flag.strip() == "0":
            logger.info("[team-scheduler] TEAM_AUTOMATION=0 — scheduler OFF")
            return None
        task = asyncio.create_task(scheduler_loop(), name="team-scheduler")
        try:
            from app.platform import team

            team.log_event("manager", "automation_started", "Team scheduler on (growth 15min + dailies)")
        except Exception:
            pass
        logger.info("[team-scheduler] started")
        return task
    except Exception as e:
        logger.warning(f"[team-scheduler] start failed: {e}")
        return None


__all__ = ["scheduler_loop", "start_scheduler"]
