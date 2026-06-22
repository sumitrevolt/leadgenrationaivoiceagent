"""Process autostart — process-engine runs ko AUTO-START karo (sub-project D V1.1).

PROBLEM: `app.agents.process_engine` me deterministic process-as-code workflows
(lead_campaign / client_content / growth_audit) defined hain, par koi unhe
KHUD se start nahi karta — `start_run` sirf admin API se manually chalta. Aur
`start_run` ka ZERO dedup hai (har call ek fresh run banata = flood risk).

YEH MODULE: ek scheduled tick (`run_due`) jo flag `PROCESS_AUTOSTART` (default
OFF) pe gated hai. Per tick:
  - process_library.list_keys() se auto-start workflows uthata,
  - lead_campaign / client_content ke liye app.niches se rotating {niche, city}
    pull karta (per tick ek hi run — NO fan-out flood, cap),
  - growth_audit (no inputs) slow/weekly cadence pe,
  - IDEMPOTENCY GUARD: process_engine.list_runs() check — agar same
    process+inputs ka running ya AAJ ka run already hai to skip (start_run ka
    dedup gap yahin fill hota),
  - start_run ke baad process_tick.delay(run_id) enqueue (Celery worker advance);
    worker down ho to inline advance fallback (growth.py:2244-2260 pattern).

HARD RULES: additive · NEVER-RAISE (failure = graceful skip, scheduler/request
kabhi crash nahi) · flag-gated default OFF · lazy heavy imports. Koi naya dep
nahi. Import-safe.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Auto-start workflows + unki cadence. lead_campaign/client_content rozana
# (rotating niche+city), growth_audit slow (weekly) — read/draft-only.
_DAILY_KEYS = ("lead_campaign", "client_content")
_WEEKLY_KEYS = ("growth_audit",)
# growth_audit kis weekday pe (0=Mon) — slow cadence, ek baar/hafta.
_WEEKLY_DAY = 0

# Per tick cap: ek hi naya run (flood guard — fan-out NAHI).
_MAX_STARTS_PER_TICK = 1


def _flag_on() -> bool:
    return os.environ.get("PROCESS_AUTOSTART", "0").strip().lower() in ("1", "true", "yes")


def _today_str() -> str:
    return date.today().isoformat()


def _rotating_inputs(process_key: str) -> dict[str, Any]:
    """app.niches se deterministic-by-date rotating {niche, city} (testable).

    Date ordinal se index — har din alag niche+city window cover hota, billing/
    over-scrape surprise ke bina. Kabhi raise nahi (fail = generic fallback)."""
    try:
        from app.niches import NICHES

        keys = [k for k, c in NICHES.items() if isinstance(c, dict)]
        if not keys:
            keys = ["general"]
        # process-key se offset taaki lead_campaign aur client_content same din
        # alag niche pakde (overlap kam).
        salt = sum(ord(ch) for ch in process_key) if process_key else 0
        idx = (date.today().toordinal() + salt) % len(keys)
        niche = keys[idx]
    except Exception:
        niche = "general"
    city = "Pune"
    try:
        from app.platform.niche_prospector import city_rotation

        rot = city_rotation()
        if rot:
            salt = sum(ord(ch) for ch in process_key) if process_key else 0
            city = rot[salt % len(rot)]
    except Exception:
        pass
    return {"niche": niche, "city": city}


def _inputs_for(process_key: str) -> dict[str, Any]:
    """Process ke liye start-inputs. growth_audit ko kuch nahi chahiye."""
    if process_key in _WEEKLY_KEYS:
        return {}
    return _rotating_inputs(process_key)


def _already_active(process_key: str, inputs: dict[str, Any], runs: list[dict[str, Any]]) -> bool:
    """IDEMPOTENCY GUARD (start_run ka missing dedup): skip agar same process ka
    koi RUNNING/WAITING run hai, YA aaj ka koi run (same process) already start
    hua. inputs ke niche pe bhi match (alag niche = naya allowed). Never-raise."""
    try:
        want_niche = str((inputs or {}).get("niche", "")).strip().lower()
        for r in runs or []:
            if str(r.get("process") or "").strip().lower() != process_key:
                continue
            status = str(r.get("status") or "").strip().lower()
            # active run (running/waiting_approval) = hamesha block.
            if status in ("running", "waiting_approval"):
                return True
            # aaj already start hua (kisi bhi status) = same niche ho to skip
            # (rozana cadence — ek niche/din). started_at ISO se date.
            started = str(r.get("started_at") or "")
            if started[:10] == _today_str():
                if not want_niche:
                    return True
                # niche-aware: started run ke inputs hum list_runs se nahi
                # dekhte, isliye conservative — same process + aaj = skip.
                return True
        return False
    except Exception:
        # guard fail = SAFE side (skip) taaki accidental flood na ho.
        return True


async def _enqueue_or_inline(run_id: str) -> dict[str, Any]:
    """process_tick.delay enqueue; worker down ho to inline advance fallback
    (growth.py process_start pattern mirror). run_due async context me chalta
    isliye inline advance `await` se (asyncio.run nahi — nested-loop crash).
    Never-raise."""
    out: dict[str, Any] = {"run_id": run_id}
    try:
        from app.tasks.staff_jobs import process_tick

        process_tick.delay(run_id)
        out["queued"] = True
    except Exception:
        out["queued"] = False
        try:
            from app.agents import process_engine

            adv = await process_engine.advance(run_id)
            out["fallback"] = "in_process"
            out["advance_status"] = (adv or {}).get("status")
        except Exception as e2:
            out["hint"] = f"worker+inline fail: {str(e2)[:100]}"
    return out


async def run_due() -> dict[str, Any]:
    """Scheduled tick: due auto-start workflows ko (idempotent) start karo.

    Flag OFF = no-op. Per tick max 1 naya run (flood-cap). Never-raise."""
    if not _flag_on():
        return {"ok": True, "skipped": "PROCESS_AUTOSTART off", "started": []}

    started: list[dict[str, Any]] = []
    skipped: list[str] = []
    try:
        from app.agents import process_engine, process_library

        valid = set(process_library.list_keys())

        # Aaj kaunse keys due hain: daily hamesha, weekly sirf _WEEKLY_DAY pe.
        try:
            weekday = datetime.now(timezone.utc).weekday()
        except Exception:
            weekday = -1
        due_keys: list[str] = [k for k in _DAILY_KEYS if k in valid]
        if weekday == _WEEKLY_DAY:
            due_keys += [k for k in _WEEKLY_KEYS if k in valid]

        if not due_keys:
            return {"ok": True, "started": [], "skipped": [], "note": "no due keys"}

        # ek baar recent runs uthao (idempotency guard ke liye).
        try:
            recent = process_engine.list_runs(limit=50)
        except Exception:
            recent = []

        for key in due_keys:
            if len(started) >= _MAX_STARTS_PER_TICK:
                skipped.append(f"{key}:cap")
                continue
            inputs = _inputs_for(key)
            if _already_active(key, inputs, recent):
                skipped.append(f"{key}:active")
                continue
            try:
                r = process_engine.start_run(key, inputs)
            except Exception as e:
                skipped.append(f"{key}:start_err")
                logger.debug(f"[process_autostart] start_run fail {key}: {e}")
                continue
            if not r.get("ok"):
                skipped.append(f"{key}:{str(r.get('error', 'no_ok'))[:40]}")
                continue
            run_id = str(r.get("run_id") or "")
            disp = await _enqueue_or_inline(run_id)
            started.append({"process": key, "run_id": run_id, "inputs": inputs, **disp})
            # naya run recent list me add — same tick double-start guard.
            recent.append(
                {
                    "process": key,
                    "status": "running",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                }
            )

        return {"ok": True, "started": started, "skipped": skipped}
    except Exception as e:
        logger.warning(f"[process_autostart] run_due failed: {e}")
        return {"ok": False, "error": str(e)[:150], "started": started, "skipped": skipped}


__all__ = ["run_due"]
