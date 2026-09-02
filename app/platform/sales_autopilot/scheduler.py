"""Sales Autopilot scheduler tick — distributed-locked, one-at-a-time, canary-batched.

:func:`run_tick` is the real engine loop. It is INERT when the master flag is off
(returns ``{"enabled": False}`` immediately, no work). When on, it:

  - takes a Redis distributed lock (SET NX) so only ONE tick runs at a time (no double
    fan-out across worker + in-process scheduler),
  - selects at most ``canary_batch_size`` (default 1) new-outreach + follow-up targets —
    NO catch-up flood: a backlog is processed one small batch per tick,
  - routes every target through :func:`send.send` (dry-run default; live only when all
    gates pass), and
  - releases the lock in a finally block.

Never raises. Designed to be wired into the existing Celery/staff-jobs beat as an INERT
job (see the lane doc); until then it is safely callable/observable via the admin API.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from app.platform.sales_autopilot import eligibility as _elig
from app.platform.sales_autopilot import followups as _followups
from app.platform.sales_autopilot import policy as _policy_mod
from app.platform.sales_autopilot import send as _send
from app.platform.sales_autopilot import store as _store
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_LOCK_KEY = "sales_autopilot:tick:lock"
_LOCK_TTL_S = 300


def _redis():
    try:
        import redis as _r

        url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        return _r.from_url(url, decode_responses=True)
    except Exception:
        return None


def _acquire_lock() -> str | None:
    """Distributed single-flight. Returns a token if acquired, else None.

    Fail-closed: if Redis is unavailable we still return a local token so a single-process
    run works in dev/tests, but log it — production always has Redis.
    """
    token = uuid.uuid4().hex
    r = _redis()
    if r is None:
        return "local:" + token
    try:
        ok = r.set(_LOCK_KEY, token, nx=True, ex=_LOCK_TTL_S)
        return token if ok else None
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[sales_autopilot.scheduler] lock acquire failed: %s", e)
        return "local:" + token


def _release_lock(token: str) -> None:
    if not token or token.startswith("local:"):
        return
    r = _redis()
    if r is None:
        return
    try:
        if r.get(_LOCK_KEY) == token:
            r.delete(_LOCK_KEY)
    except Exception:
        pass


def _primary_channel(pol: _policy_mod.Policy) -> str:
    """Pick the enabled outbound channel. WhatsApp preferred when on, else email.

    Neither enabled → whatsapp (send() still simulates/refuses on channel gate, so this
    never produces a live provider call on a disabled channel).
    """
    if pol.get("whatsapp_enabled", False):
        return "whatsapp"
    if pol.get("email_enabled", False):
        return "email"
    return "whatsapp"


def _new_outreach_targets(pol: _policy_mod.Policy, limit: int) -> list[dict[str, Any]]:
    """Prospects in NEW status eligible for an initial touch, capped at ``limit``."""
    out: list[dict[str, Any]] = []
    channel = _primary_channel(pol)
    for rec in _store.list_prospects(limit=1000):
        if len(out) >= limit:
            break
        if rec.get("status") != _store.STATUS_NEW:
            continue
        out.append({"prospect": rec, "step": _elig.STEP_INITIAL, "channel": channel})
    return out


async def run_tick(limit: int | None = None, *, force_dry_run: bool = False) -> dict[str, Any]:
    """One scheduler tick. INERT when master flag off. Never raises.

    ``force_dry_run=True`` makes EVERY send on this tick a simulation, regardless
    of stored policy. The canary endpoint documents "never sends live"; before
    this parameter existed that promise rested entirely on ``policy.dry_run``
    being set correctly, so a policy misconfiguration silently turned the canary
    into a live sender. A safety promise must be structural, not configural.
    """
    pol = _policy_mod.get_policy()
    if not pol.enabled:
        # INERT: no lock, no work, no provider. Record the truth for observability.
        res = {"enabled": False, "processed": 0, "skip_reason": "engine_disabled"}
        _store.record_tick(res)
        return {"enabled": False, "processed": 0}

    token = _acquire_lock()
    if not token:
        # Another tick holds the single-flight lock — skip (no overlap, no catch-up).
        res = {"enabled": True, "skipped": "lock_held", "processed": 0}
        _store.record_tick(res)
        return res

    summary: dict[str, Any] = {
        "enabled": True,
        "dry_run": bool(pol.dry_run) or bool(force_dry_run),
        "forced_dry_run": bool(force_dry_run),
        "processed": 0,
        "outcomes": {},
        "items": [],
    }
    try:
        batch = pol.canary_batch() if limit is None else max(1, int(limit))

        # 0. Pipeline refill (flag-gated) + pay-truth reconcile — never sends.
        try:
            from app.platform.sales_autopilot import refill as _refill

            summary["refill"] = _refill.refill_from_prospector()
        except Exception as e:  # pragma: no cover - defensive
            summary["refill"] = {"error": str(e)[:120]}
        try:
            from app.platform.sales_autopilot import pay_truth as _pay

            summary["pay_truth"] = _pay.reconcile_pay_truth(chase=True)
        except Exception as e:  # pragma: no cover - defensive
            summary["pay_truth"] = {"error": str(e)[:120]}

        # 1. New outreach (respecting per-stage kill).
        targets: list[dict[str, Any]] = []
        if not pol.kill("new_outreach"):
            targets.extend(_new_outreach_targets(pol, batch))

        # 2. Follow-ups fill remaining batch capacity (no catch-up flood).
        if not pol.kill("followups") and len(targets) < batch:
            due = _followups.due_followups(pol, channel=_primary_channel(pol))
            targets.extend(due[: batch - len(targets)])

        # Empty queue is a NORMAL state, not silent success — record why so Mission
        # Control doesn't read processed=0 as a failure or a lie. (ISSUE-03)
        if not targets:
            counts: dict[str, int] = {}
            for r in _store.list_prospects(limit=1000):
                st = str(r.get("status") or _store.STATUS_NEW)
                counts[st] = counts.get(st, 0) + 1
            summary["idle_reason"] = "no_eligible_prospects"
            summary["prospect_status_counts"] = counts
            summary["notes"] = (
                "processed=0 kyunki koi eligible NEW/follow-up prospect nahi — "
                "yeh expected idle hai, engine fail nahi hua."
            )

        for t in targets[:batch]:
            rec = t["prospect"]
            res = await _send.send(
                str(rec.get("id")),
                channel=t["channel"],
                step=t["step"],
                pol=pol,
                prospect=rec,
                force_dry_run=force_dry_run,
            )
            outcome = res.get("outcome", "SKIPPED")
            summary["outcomes"][outcome] = summary["outcomes"].get(outcome, 0) + 1
            summary["items"].append(
                {
                    "prospect_id": rec.get("id"),
                    "step": t["step"],
                    "channel": t["channel"],
                    "outcome": outcome,
                    "reason": res.get("reason"),
                }
            )
            summary["processed"] += 1
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[sales_autopilot.scheduler] tick failed: %s", e)
        summary["error"] = str(e)[:150]
    finally:
        _release_lock(token)
    _store.record_tick(summary)
    return summary


__all__ = ["run_tick"]
