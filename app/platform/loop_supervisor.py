"""loop_supervisor.py — single-loop SPOF hardening (SP3).

PROBLEM: do single-points-of-failure jinhe koi watch nahi karta —
  1. **Call-processor task** (`CallManager.start_call_processor`) ek hi
     long-lived asyncio task hai jo main.py lifespan me spawn hota hai. Agar
     wo task kisi un-caught error se die ho jaye (ya kabhi spawn hi na ho), to
     queue silently bharti rehti hai — koi alert nahi, koi re-spawn nahi.
  2. **Boot-grace skip** (team_scheduler / boot_grace) — restart pe heavy daily
     job apne window me ho to wo SKIP ho jaata hai (restart-storm prevent). Yeh
     by-design sahi hai, par operator ko KABHI pata nahi chalta ki aaj qa/blog/
     content run hi nahi hua. Agar din me 2-3 restart isi window me hue to job
     us din kabhi nahi chala — chupchaap.

Yeh module dono ke liye thin, NEVER-RAISE helpers deta hai:
  * `ensure_call_processor_alive(app)` — lifespan periodically call kare. Task
    dead-non-cancel mile to re-spawn + ntfy alert (cooldown). Heartbeat record.
  * `alert_boot_grace_skip(job)` — boot-grace skip ke time call ho; ops_alerts
    ntfy fire kare taaki operator ko pata chale ki aaj job skip hua.

Design rules (project-proven):
- **Flag-gated, default OFF**: `LOOP_SUPERVISOR=1` unset = INERT. Bina flag ke
  dono helpers ek `{"ok": True, "reason": "disabled"}` no-op return karte hain —
  shipping karne se kuch nahi badalta.
- **NEVER raises**: har cheez try/except; failure = graceful skip. Lifespan ya
  scheduler ko kabhi crash nahi karega.
- **Reuses** `app.platform.ops_alerts._ntfy` (same ntfy channel + cooldown
  pattern) aur `automation_health.record_run` (heartbeat).
- Lazy imports (heavy / circular se bachne ke liye) — sab function ke andar.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FLAG = "LOOP_SUPERVISOR"

# In-process cooldowns (seconds) so a re-spawn loop or repeated boot-grace skip
# doesn't storm the operator's phone. ops_alerts has its own file ledger; these
# are a cheap in-memory guard local to this supervisor.
_RESPAWN_COOLDOWN_S = 600  # at most one re-spawn alert per 10 min
_BOOT_GRACE_COOLDOWN_S = 3600  # at most one boot-grace alert per job per hour
_last_alert: dict[str, float] = {}


def enabled() -> bool:
    """Master gate. OFF default = INERT (unset == off)."""
    return os.environ.get(_FLAG, "0").strip().lower() in ("1", "true", "yes")


def _cooldown_ok(key: str, window_s: float) -> bool:
    """True if we may alert for `key` now (and records the fire). Never raises."""
    try:
        now = time.time()
        last = _last_alert.get(key, 0.0)
        if (now - last) < window_s:
            return False
        _last_alert[key] = now
        return True
    except Exception:
        return False


def _alert(title: str, body: str, *, priority: str = "high", tags: list[str] | None = None) -> None:
    """Best-effort ntfy push reusing ops_alerts' channel. Never raises."""
    try:
        from app.platform import ops_alerts as _oa

        _oa._ntfy(title, body[:1000], priority=priority, tags=tags or [])
    except Exception as exc:
        logger.debug("loop_supervisor alert swallowed: %s", exc)


def _heartbeat(job: str, ok: bool = True, note: str = "") -> None:
    """Record an automation_health heartbeat. Never raises."""
    try:
        from app.platform import automation_health as _ah

        _ah.record_run(job, ok=ok, note=note[:120])
    except Exception as exc:
        logger.debug("loop_supervisor heartbeat swallowed: %s", exc)


# --------------------------------------------------------------------------- #
# 1. Call-processor liveness
# --------------------------------------------------------------------------- #
def _task_is_dead_non_cancel(task: Any) -> bool:
    """True if `task` finished for a reason OTHER than cancellation.

    A cancelled task = intentional shutdown, NOT a failure — don't re-spawn.
    A task that raised (or returned) = the processor loop exited = dead, re-spawn.
    None / not-a-task = treat as dead (nothing alive to process the queue).
    """
    try:
        if task is None:
            return True
        if not task.done():
            return False
        # done() — distinguish cancel from error/return.
        try:
            if task.cancelled():
                return False
        except Exception:
            return False
        # Retrieve exception WITHOUT re-raising (avoids "exception never retrieved").
        try:
            task.exception()
        except asyncio.CancelledError:
            return False
        except Exception:
            pass
        return True
    except Exception:
        # If we can't even introspect, be conservative: don't claim dead.
        return False


def ensure_call_processor_alive(app: Any) -> dict[str, Any]:
    """Check the call-processor asyncio task and re-spawn it if dead-non-cancel.

    Intended to be called PERIODICALLY from the FastAPI lifespan (e.g. via a
    small watchdog loop). It mirrors how main.py spawns the processor:
        _cm = app.state.call_manager  (set at startup)
        task = asyncio.create_task(_cm.start_call_processor())
    and stores the new task back on `app.state.call_processor_task` so the
    next check (and lifespan shutdown) can find it.

    Returns a small status dict for logging. NEVER raises.
    """
    if not enabled():
        return {"ok": True, "reason": "disabled"}
    try:
        state = getattr(app, "state", None)
        cm = getattr(state, "call_manager", None)
        if cm is None:
            # Processor was never started (telephony unconfigured / flag off in
            # main). Nothing to supervise — not an error.
            return {"ok": True, "reason": "no_call_manager"}

        task = getattr(state, "call_processor_task", None)
        if not _task_is_dead_non_cancel(task):
            _heartbeat("call_processor", ok=True, note="alive")
            return {"ok": True, "reason": "alive"}

        # Dead (or never tracked) — re-spawn.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — can't spawn here; report so caller can decide.
            return {"ok": False, "reason": "no_running_loop"}

        new_task = loop.create_task(cm.start_call_processor())
        try:
            state.call_processor_task = new_task
        except Exception:
            pass
        _heartbeat("call_processor", ok=False, note="respawned")
        logger.warning("[loop_supervisor] call-processor was dead — re-spawned")
        if _cooldown_ok("respawn:call_processor", _RESPAWN_COOLDOWN_S):
            _alert(
                "🔁 Call-processor re-spawned",
                "Outbound call queue processor task was dead (non-cancel) — "
                "loop_supervisor re-spawned it. Queued calls were stalled till now.",
                priority="urgent",
                tags=["rotating_light", "telephony"],
            )
        return {"ok": True, "reason": "respawned"}
    except Exception as exc:
        logger.debug("ensure_call_processor_alive swallowed: %s", exc)
        return {"ok": False, "reason": "error", "error": str(exc)[:200]}


async def supervisor_loop(app: Any, interval_s: int = 120) -> None:
    """Optional long-lived watchdog the lifespan can spawn as one task.

    Periodically (every `interval_s`) calls ensure_call_processor_alive. Inert
    when the flag is OFF — it still loops cheaply but does nothing. NEVER raises
    out of the loop (so it can't take down the process). Stops on cancellation.
    """
    logger.info("[loop_supervisor] watchdog loop started (interval=%ss)", interval_s)
    while True:
        try:
            ensure_call_processor_alive(app)
        except asyncio.CancelledError:
            logger.info("[loop_supervisor] watchdog loop stopped")
            break
        except Exception as exc:
            logger.debug("[loop_supervisor] loop tick swallowed: %s", exc)
        try:
            await asyncio.sleep(max(15, int(interval_s)))
        except asyncio.CancelledError:
            logger.info("[loop_supervisor] watchdog loop stopped")
            break


# --------------------------------------------------------------------------- #
# 2. Boot-grace skip visibility
# --------------------------------------------------------------------------- #
def alert_boot_grace_skip(job: str) -> dict[str, Any]:
    """Fire an ops alert when a heavy daily job is skipped by boot-grace.

    Boot-grace silently skips heavy jobs (qa/blog/content/...) if the worker
    restarted inside that job's window. That's correct for restart-storm
    prevention, but the operator never learns the job didn't run today. This
    helper makes the skip VISIBLE (ntfy + heartbeat), without changing the
    skip behaviour itself.

    Call it right where the skip is decided (team_scheduler boot-grace seed /
    staff_jobs boot_grace branch). Returns a status dict. NEVER raises.
    """
    if not enabled():
        return {"alerted": False, "reason": "disabled"}
    try:
        j = (job or "?")[:40]
        # Heartbeat so automation_health knows the job was intentionally skipped
        # (not silently overdue/dead).
        _heartbeat(f"boot_grace_skip:{j}", ok=True, note="boot-grace skip")
        if not _cooldown_ok(f"boot_grace:{j}", _BOOT_GRACE_COOLDOWN_S):
            return {"alerted": False, "reason": "cooldown", "job": j}
        _alert(
            f"⏭️ Boot-grace skip: {j}",
            f"Heavy daily job '{j}' was SKIPPED this boot (worker/scheduler "
            f"restarted inside its window). It will run next cycle — but if "
            f"restarts repeat in-window, '{j}' may not run today.",
            priority="default",
            tags=["warning", "scheduler"],
        )
        return {"alerted": True, "job": j}
    except Exception as exc:
        logger.debug("alert_boot_grace_skip swallowed: %s", exc)
        return {"alerted": False, "reason": "error", "error": str(exc)[:200]}


__all__ = [
    "enabled",
    "ensure_call_processor_alive",
    "supervisor_loop",
    "alert_boot_grace_skip",
]
