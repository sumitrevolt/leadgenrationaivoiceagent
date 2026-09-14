"""Full WhatsApp Automation — ENABLED (user decision, high risk acknowledged).

This module provides fully automated WhatsApp messaging via the GUARDED sender
boundary (``app/integrations/whatsapp.py::get_whatsapp_sender``). It must never POST
to a provider itself: every send here passes ``send_permitted`` (canary allowlist +
opt-out ledger + ``WHATSAPP_AUTO_SEND`` / Owner-OS kill), the same gate as the rest
of the codebase. See ``send_template_message`` for the 2026-09-14 bypass fix.

⚠️ WARNING: Cold/bulk auto-send = NUMBER BAN RISK (3 business days).
User has explicitly accepted this risk.

GATES (can be enabled/disabled via env):
- WHATSAPP_AUTO_SEND=1           # Enable full automation
- WHATSAPP_AUTO_SEND_HARD_OFF=0  # Emergency kill switch (env)
- WHATSAPP_AUTO_SEND_DAILY_CAP=50  # Daily message cap (conservative)
- WHATSAPP_AUTO_SEND_BATCH=10     # Per-run batch limit
- Owner-OS ``owner_whatsapp_outbound`` kill switch (runtime, engaged by emergency_stop)
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone

from app.utils.logger import setup_logger
from app.worker import celery_app

logger = setup_logger(__name__)


# ── Config ──────────────────────────────────────────────────────────
def _owner_kill_engaged() -> bool:
    """Owner-OS ``owner_whatsapp_outbound`` kill switch (runtime state, no .env edit).

    This is what :func:`emergency_stop` engages. Unreadable -> not engaged HERE; the
    sender boundary (``send_permitted`` -> ``auto_send_enabled``) is still the
    authority and re-checks the same switch on every send.
    """
    try:
        from app.platform import owner_os

        return bool(owner_os.kill_engaged("owner_whatsapp_outbound"))
    except Exception as e:  # noqa: BLE001 - probe, must never raise on a gate read
        logger.warning(f"WA automation: owner kill switch unreadable ({e})")
        return False


def whatsapp_enabled() -> bool:
    """Master gate for this module: env flags AND the Owner-OS runtime kill switch.

    Kill first, so an engaged emergency stop cannot be undone by an env value (same
    order as ``whatsapp_campaign.auto_send_enabled``). ``WHATSAPP_AUTO_SEND_HARD_OFF``
    is kept as the env-level switch — the RUNTIME stop is the kill switch, never a
    ``.env`` edit (see :func:`emergency_stop`).
    """
    if os.getenv("WHATSAPP_AUTO_SEND", "0").strip().lower() not in ("1", "true", "yes"):
        return False
    if os.getenv("WHATSAPP_AUTO_SEND_HARD_OFF", "0").strip().lower() in ("1", "true", "yes"):
        return False
    return not _owner_kill_engaged()


def daily_cap() -> int:
    return int(os.getenv("WHATSAPP_AUTO_SEND_DAILY_CAP", "50"))


def batch_limit() -> int:
    return int(os.getenv("WHATSAPP_AUTO_SEND_BATCH", "10"))


# ── Template Management ─────────────────────────────────────────────
def _get_template_name(purpose: str) -> str:
    """Map purpose to approved template name."""
    templates = {
        "lead_followup": "lead_followup_v1",  # Must be pre-approved in Meta
        "post_call": "post_call_interested_v1",  # For interested leads
        "daily_tip": "daily_business_tip_v1",  # Value-add content
        "appointment": "appointment_reminder_v1",  # Appointment reminders
        "offer": "special_offer_v1",  # Promotional offers
    }
    return templates.get(purpose, "lead_followup_v1")


# ── Core Send Function ──────────────────────────────────────────────
async def send_template_message(
    to_phone: str,
    template_name: str,
    template_params: list = None,
    language: str = "en",
) -> dict:
    """Send a template message THROUGH the guarded sender boundary (§5).

    BYPASS CLOSED (2026-09-14). This function used to assemble the Meta Cloud Graph
    ``/messages`` URL itself (host + phone-id) and POST the payload with ``httpx``. That
    made this module the one automated WhatsApp sender in the repo that never called
    :func:`app.integrations.whatsapp.send_permitted` — so it bypassed the canary
    allowlist, the opt-out ledger and the Owner-OS kill switch, and the egress ratchet in
    ``tests/test_whatsapp_auto_send_gate.py`` could not see it either (that ratchet only
    scanned for the WAHA text-send endpoint). The send now goes through
    ``get_whatsapp_sender()``, which picks Cloud or WAHA and enforces the gate at two
    levels (public method + egress backstop).

    Returns this module's historical shape — ``{"sent": bool, ...}`` — because
    ``run_whatsapp_batch`` counts with ``result.get("sent")``; a refusal therefore comes
    back as ``{"sent": False, "reason": <gate reason>}`` and never as success.
    """
    if not whatsapp_enabled():
        return {"sent": False, "reason": "WHATSAPP_AUTO_SEND not enabled"}

    # Lazy import (send-path idiom): keeps task import cheap and lets tests patch the
    # selector. The selector decides Cloud vs self-host WAHA — this module no longer
    # needs to know, and no longer needs WhatsApp credentials of its own.
    from app.integrations.whatsapp import get_whatsapp_sender

    sender = get_whatsapp_sender()
    try:
        res = await sender.send_template_message(
            to_phone, template_name, list(template_params or []), language
        )
    except Exception as e:  # noqa: BLE001 - a send must never crash the batch runner
        logger.error(f"WhatsApp send exception: {e}")
        return {"sent": False, "reason": str(e)[:150]}

    if res.get("error"):
        logger.warning(f"WhatsApp send blocked/failed: {res.get('error')}")
        return {"sent": False, "reason": str(res["error"])[:150]}
    return {"sent": True, "response": res}


# ── Automated Flows ────────────────────────────────────────────────
async def auto_send_lead_followup(lead_phone: str, lead_name: str = "") -> dict:
    """Auto-send follow-up to new lead."""
    if not whatsapp_enabled():
        return {"sent": False, "reason": "WhatsApp auto disabled"}

    template = _get_template_name("lead_followup")
    return await send_template_message(
        lead_phone, template, template_params=[lead_name or "Customer"]
    )


async def auto_send_post_call_interested(lead_phone: str, niche: str = "") -> dict:
    """Auto-send to leads who showed interest post-call."""
    if not whatsapp_enabled():
        return {"sent": False, "reason": "WhatsApp auto disabled"}

    template = _get_template_name("post_call")
    return await send_template_message(
        lead_phone, template, template_params=[niche or "your business"]
    )


async def auto_send_daily_tip(phone: str, tip: str) -> dict:
    """Auto-send daily business tip."""
    if not whatsapp_enabled():
        return {"sent": False, "reason": "WhatsApp auto disabled"}

    template = _get_template_name("daily_tip")
    return await send_template_message(phone, template, template_params=[tip[:1024]])


# ── Batch Runner (for scheduler) ───────────────────────────────────
async def run_whatsapp_batch(leads: list) -> dict:
    """Process a batch of leads for WhatsApp automation."""
    if not whatsapp_enabled():
        return {"processed": 0, "sent": 0, "reason": "disabled"}

    cap = daily_cap()
    batch = min(batch_limit(), len(leads))

    sent = 0
    failed = 0

    for i, lead in enumerate(leads[:batch]):
        if sent >= cap:
            break

        # Determine message type based on lead status
        if lead.get("status") == "interested":
            result = await auto_send_post_call_interested(lead["phone"], lead.get("niche", ""))
        else:
            result = await auto_send_lead_followup(lead["phone"], lead.get("name", ""))

        if result.get("sent"):
            sent += 1
        else:
            failed += 1

        # Small delay to avoid rate limiting
        import asyncio

        await asyncio.sleep(0.5)

    return {
        "processed": min(batch, len(leads)),
        "sent": sent,
        "failed": failed,
        "daily_cap": cap,
    }

# ── Daily budget + idempotency (Redis-backed) ───────────────────────
# The daily cap must be genuinely DAILY. The beat fires hourly (9-19 IST = 11
# runs/day) and run_whatsapp_batch only clamps PER RUN, so without a shared
# counter 11 x batch_limit could blow past WHATSAPP_AUTO_SEND_DAILY_CAP.
# If Redis is unreachable the cap cannot be enforced -> FAIL CLOSED (§5).
_WA_DAILY_TTL_S = 48 * 3600
_IST = timezone(timedelta(hours=5, minutes=30))


def _ist_today() -> str:
    return datetime.now(_IST).strftime("%Y-%m-%d")


def _redis_client():
    try:
        import redis as _redis

        from app.config import settings

        return _redis.Redis.from_url(str(settings.redis_url), socket_timeout=3)
    except Exception as e:  # noqa: BLE001 - infra probe, must not raise
        logger.warning(f"WA automation: Redis unavailable ({e}) — daily cap cannot be enforced")
        return None


def _budget_state(day: str) -> tuple:
    """Return (sent_today, phones_done_today); (None, None) if Redis is down."""
    r = _redis_client()
    if r is None:
        return None, None
    try:
        raw = r.get(f"wa:auto:sent:{day}")
        sent = int(raw or 0)
        done = set()
        for member in r.smembers(f"wa:auto:done:{day}") or ():
            done.add(member.decode() if isinstance(member, bytes) else str(member))
        return sent, done
    except Exception as e:  # noqa: BLE001
        logger.warning(f"WA automation: budget read failed ({e}) — fail-closed")
        return None, None


def _record_sends(day: str, phones: list, sent: int) -> None:
    r = _redis_client()
    if r is None or sent <= 0:
        return
    try:
        pipe = r.pipeline()
        pipe.incrby(f"wa:auto:sent:{day}", sent)
        if phones:
            pipe.sadd(f"wa:auto:done:{day}", *phones)
        pipe.expire(f"wa:auto:sent:{day}", _WA_DAILY_TTL_S)
        pipe.expire(f"wa:auto:done:{day}", _WA_DAILY_TTL_S)
        pipe.execute()
    except Exception as e:  # noqa: BLE001
        logger.error(f"WA automation: failed to record sends: {e}")


# ── Candidate selection ─────────────────────────────────────────────
def _fetch_candidates(limit: int) -> list:
    """Fetch leads eligible for an automated WhatsApp touch.

    Only engaged, non-terminal states are eligible. DND / NOT_INTERESTED /
    WRONG_NUMBER / CONVERTED / LOST are excluded by construction.
    """
    if limit <= 0:
        return []
    try:
        from app.models.base import get_db_session
        from app.models.lead import Lead, LeadStatus

        with get_db_session() as db:
            rows = (
                db.query(Lead)
                .filter(Lead.status.in_([LeadStatus.NEW, LeadStatus.CONTACTED, LeadStatus.QUALIFIED]))
                .filter(Lead.phone.isnot(None))
                .order_by(Lead.created_at.asc())
                .limit(limit * 3)  # over-fetch: the DND scrub will trim
                .all()
            )
            out = []
            for lead in rows:
                phone = (getattr(lead, "phone", "") or "").strip()
                if not phone:
                    continue
                status = getattr(lead, "status", None)
                sval = getattr(status, "value", None) or (str(status) if status else "new")
                out.append(
                    {
                        "phone": phone,
                        "name": getattr(lead, "name", "") or "",
                        "niche": getattr(lead, "niche", "") or "",
                        # run_whatsapp_batch discriminates on the literal string
                        # "interested" for the niche-aware post-call template, but
                        # LeadStatus has no "interested" member — so map the
                        # engaged states onto it. (Latent mismatch, not fixed here
                        # to keep blast radius small.)
                        "status": "interested" if sval in ("contacted", "qualified") else "new",
                        "lead_status": sval,
                    }
                )
            return out
    except Exception as e:  # noqa: BLE001
        logger.error(f"WA automation: lead fetch failed: {e}")
        return []


async def _scrub_dnd(candidates: list) -> tuple:
    """Fail-closed DND/TRAI scrub (§5). UNVERIFIED == DND == BLOCK.

    Mirrors app/automation/orchestrator_pipeline.py::_is_dnd. DNDChecker has no
    external lookup provider (Exotel removed 2026-06-18), so any number not
    already in the local cache / consent ledger returns UNVERIFIED and is
    therefore BLOCKED. That is intentional: cold promotional WhatsApp without
    provable non-DND status is not permitted.
    """
    try:
        from app.utils.dnd_checker import DNDChecker

        checker = DNDChecker()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"WA automation: DND checker unavailable ({e}) — FAIL CLOSED")
        return [], len(candidates)

    kept: list = []
    blocked = 0
    for c in candidates:
        phone = c.get("phone")
        if not phone:
            continue
        try:
            # channel="messaging" (OPS-017): promotional WhatsApp needs a real
            # NCPR scrub. The blanket DND_CARRIER_SCRUB voice allowance must
            # NOT be able to mark every number "verified non-DND" here.
            res = await checker.check_single(phone, channel="messaging")
            verified = bool(getattr(res, "verified", True))
            is_dnd = bool(getattr(res, "is_dnd", False))
            if not verified or is_dnd:
                blocked += 1
                continue
        except Exception as e:  # noqa: BLE001
            logger.debug(f"WA automation: DND check error for ***{str(phone)[-4:]}: {e}")
            blocked += 1  # FAIL-CLOSED (§5)
            continue
        kept.append(c)
    return kept, blocked


def _run_async(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


# ── Scheduler Entry Point ──────────────────────────────────────────
# 2026-09-06 (wiring): registered as a Celery task — beat entry
# "staff-whatsapp-automation-hourly" pointed at this name but the function was
# plain, so the worker rejected it as unregistered and the hourly queue-drain
# silently never ran (same dormant-wiring class as the daily-social incident
# #468). Direct in-process callers (team_scheduler, staff_jobs) are unaffected:
# calling a task object runs it synchronously; only .delay()/beat enqueues.
#
@celery_app.task(name="app.tasks.whatsapp_automation.run_whatsapp_automation")
def run_whatsapp_automation():
    """Celery beat entry: run WhatsApp automation batch.

    Compliance spine — EVERY gate below fails CLOSED (§5):
      1. WHATSAPP_AUTO_SEND gate + HARD_OFF emergency kill switch.
      2. Genuine DAILY cap (Redis counter), not a per-run clamp.
      3. Per-day idempotency set — a phone is messaged at most once a day.
      4. Fail-closed DND/TRAI scrub — unverified lookup == blocked.
    Any infra failure (Redis / DB / DND checker) aborts the run instead of
    sending blind. Always returns a dict containing "status".
    """
    if not whatsapp_enabled():
        logger.info("WhatsApp automation disabled (WHATSAPP_AUTO_SEND=0)")
        return {"status": "skipped", "reason": "disabled"}

    day = _ist_today()
    sent_today, done_today = _budget_state(day)
    if sent_today is None or done_today is None:
        return {
            "status": "aborted",
            "reason": "daily-cap counter unavailable — cannot enforce cap (fail-closed)",
        }

    cap = daily_cap()
    remaining = max(0, cap - sent_today)
    if remaining <= 0:
        return {
            "status": "skipped",
            "reason": "daily cap reached",
            "sent_today": sent_today,
            "daily_cap": cap,
        }

    candidates = _fetch_candidates(min(batch_limit(), remaining))
    if not candidates:
        return {
            "status": "idle",
            "reason": "no eligible candidates",
            "candidates": 0,
            "sent_today": sent_today,
            "daily_cap": cap,
        }

    fresh = [c for c in candidates if c.get("phone") not in done_today]
    skipped_dupe = len(candidates) - len(fresh)
    if not fresh:
        return {
            "status": "idle",
            "reason": "all candidates already messaged today",
            "skipped_duplicate": skipped_dupe,
            "sent_today": sent_today,
            "daily_cap": cap,
        }

    allowed, blocked_dnd = _run_async(_scrub_dnd(fresh))
    if not allowed:
        return {
            "status": "blocked",
            "reason": "DND scrub removed all candidates (fail-closed: unverified == blocked)",
            "candidates": len(fresh),
            "skipped_dnd": blocked_dnd,
            "sent_today": sent_today,
            "daily_cap": cap,
        }

    result = _run_async(run_whatsapp_batch(allowed))
    sent = int(result.get("sent") or 0)
    if sent:
        _record_sends(day, [c["phone"] for c in allowed][:sent], sent)

    return {
        "status": "ok",
        "candidates": len(fresh),
        "skipped_duplicate": skipped_dupe,
        "skipped_dnd": blocked_dnd,
        "sent": sent,
        "failed": int(result.get("failed") or 0),
        "sent_today": sent_today + sent,
        "daily_cap": cap,
    }


# ── Emergency Stop ─────────────────────────────────────────────────
def emergency_stop(
    by: str = "whatsapp_automation.emergency_stop",
    reason: str = "application emergency_stop()",
) -> dict:
    """Stop all automated WhatsApp sends NOW — via runtime state, never by editing `.env`.

    WHAT THIS REPLACED (2026-09-14). The old body ran
    ``subprocess.run(["bash", "-c", "sed -i 's/WHATSAPP_AUTO_SEND_HARD_OFF=0/...=1/' .env"],
    cwd="/opt/leadgen", capture_output=True)``. Three reasons application code must not
    do that — all of them why the "emergency stop" was not one:

    1. **It could not take effect.** ``.env`` is read when the container is CREATED.
       A process keeps the environment it started with, so ``os.getenv`` inside the
       running worker never sees the edited value — the flag only changed after a
       recreate, i.e. exactly when the emergency was already over.
    2. **It usually failed silently.** The app does not run from the host checkout, so
       the relative ``.env`` path generally did not exist there; ``capture_output=True``
       with no return-code check turned that into a no-op with no signal.
    3. **It wrote the file that holds the API keys/secrets** (§5 secrets rule). One bad
       substitution or a partial write corrupts every credential in it — an app bug must
       not be able to damage the credential store.

    The replacement is the Owner-OS kill switch ``owner_whatsapp_outbound``, which is a
    runtime state file (``data/owner_kill_switches.jsonl``) consulted at SEND time by
    ``whatsapp_campaign.auto_send_enabled()`` (and by :func:`whatsapp_enabled` here), so
    engaging it stops the very next send — no restart, no file edit. The env-level
    ``WHATSAPP_AUTO_SEND_HARD_OFF`` remains available to operators; this function simply
    no longer pretends to change it.

    Returns the store's result: ``{"ok": True, ...}`` on success; ``{"ok": False, ...}``
    when the switch could not be set (never a silent success).
    """
    try:
        from app.platform import owner_os

        res = owner_os.set_kill_switch("owner_whatsapp_outbound", True, by=by, reason=reason)
        if not res.get("ok"):
            logger.error(f"WHATSAPP EMERGENCY STOP did not engage the kill switch: {res}")
            return res
    except Exception as e:  # noqa: BLE001 - report, never raise into an emergency path
        logger.error(f"WHATSAPP EMERGENCY STOP failed to engage owner_whatsapp_outbound: {e}")
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    logger.warning("WHATSAPP EMERGENCY STOP ACTIVATED (owner_whatsapp_outbound engaged)")
    return res


__all__ = [
    "whatsapp_enabled",
    "send_template_message",
    "auto_send_lead_followup",
    "auto_send_post_call_interested",
    "auto_send_daily_tip",
    "run_whatsapp_batch",
    "run_whatsapp_automation",
    "emergency_stop",
]
