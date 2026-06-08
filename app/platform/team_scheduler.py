from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))
_TICK_S = 60

# --------------------------------------------------------------------------- #
# Single-instance lock — uvicorn --workers 2 dono workers scheduler start karte
# the → har job 2 baar chalta tha (double emails/content!). Lock file se sirf
# EK worker scheduler chalata hai. Heartbeat (mtime) + dead-PID reclaim:
# - lock free/stale (>180s) ya PID dead → acquire karo
# - warna skip (dusra worker owner hai)
# Loop har tick lock ka mtime refresh karta hai (heartbeat).
# --------------------------------------------------------------------------- #
_LOCK_PATH = os.path.join("data", ".scheduler.lock")
_LOCK_STALE_S = 180
_have_lock = False


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _acquire_lock() -> bool:
    """True agar is process ne scheduler-lock le liya. Atomic + stale-reclaim."""
    global _have_lock
    try:
        os.makedirs(os.path.dirname(_LOCK_PATH) or ".", exist_ok=True)
        try:
            fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            _have_lock = True
            return True
        except FileExistsError:
            # exists — stale ya dead-pid ho to steal karo
            try:
                age = datetime.now().timestamp() - os.path.getmtime(_LOCK_PATH)
                pid = int((open(_LOCK_PATH).read().strip() or "0") or 0)
            except Exception:
                age, pid = 9999, 0
            if age > _LOCK_STALE_S or (pid and not _pid_alive(pid)) or pid == 0:
                try:
                    with open(_LOCK_PATH, "w") as f:
                        f.write(str(os.getpid()))
                    _have_lock = True
                    return True
                except Exception:
                    return False
            return False
    except Exception:
        # lock-fs issue — fail-open (chalne do; single-worker dev me theek)
        _have_lock = True
        return True


def _refresh_lock() -> None:
    """Heartbeat — lock file ka mtime update (owner zinda hai)."""
    if not _have_lock:
        return
    try:
        os.utime(_LOCK_PATH, None)
    except Exception:
        pass

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
    "reply_triage": None,
    "watchdog": None,
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
        elif job == "reply_triage":
            from app.platform import reply_agent

            await reply_agent.run_reply_triage()
        elif job == "watchdog":
            from app.platform import ops_watchdog

            await ops_watchdog.run_watchdog()
    except Exception as e:
        logger.warning(f"[team-scheduler] job {job} failed: {e}")


async def scheduler_loop() -> None:
    logger.info("[team-scheduler] loop started (growth 15min + dailies)")
    while True:
        try:
            _refresh_lock()  # heartbeat — owner zinda hai
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
            # AI reply triage — hourly (read inbox replies, classify, draft). Gated by REPLY_AGENT.
            if now.minute >= 20 and _last_ran["reply_triage"] != hour_key:
                _last_ran["reply_triage"] = hour_key
                await _run_job("reply_triage")
            # AI ops watchdog — hourly (monitor + diagnose + alert). Gated by OPS_WATCHDOG.
            if now.minute >= 35 and _last_ran["watchdog"] != hour_key:
                _last_ran["watchdog"] = hour_key
                await _run_job("watchdog")
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
        # Single-instance: sirf EK worker scheduler chalaye (warna double jobs).
        if not _acquire_lock():
            logger.info("[team-scheduler] another worker owns the scheduler — skip (single-instance)")
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
