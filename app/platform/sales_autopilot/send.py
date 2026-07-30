"""Sales Autopilot idempotent send service — the ONLY outbound entrypoint.

Accepts ``prospect_id + channel + step`` (NOT arbitrary phone+text from a browser). It
resolves the prospect, builds a versioned message, runs eligibility + safety, computes a
deterministic idempotency key, PERSISTS the attempt BEFORE any provider call, and only
then — when the engine + channel flag are on AND policy dry_run is false AND everything
passed — calls the existing ban-safe WhatsApp provider (``whatsapp_campaign.send_one``)
or the canonical email integration (``EmailSender`` + List-Unsubscribe headers).

Dry-run is the default and is MANDATORY whenever any gate is unmet: we simulate, label the
attempt ``SIMULATED``, and never touch a provider. A provider timeout yields
``UNKNOWN_REQUIRES_REVIEW`` with NO auto-retry. Never raises.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

from app.platform.sales_autopilot import eligibility as _elig
from app.platform.sales_autopilot import messages as _messages
from app.platform.sales_autopilot import policy as _policy_mod
from app.platform.sales_autopilot import safety as _safety
from app.platform.sales_autopilot import store as _store
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Outcomes
SENT = "SENT"
SIMULATED = "SIMULATED"
SKIPPED = "SKIPPED"
BLOCKED = "BLOCKED"
DUPLICATE = "DUPLICATE"
FAILED = "FAILED"
UNKNOWN_REQUIRES_REVIEW = "UNKNOWN_REQUIRES_REVIEW"


def build_idempotency_key(prospect_id: str, channel: str, step: str, version: str) -> str:
    raw = f"{prospect_id}|{channel}|{step}|{version}"
    return "sap_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


async def _provider_send_whatsapp(phone: str, message: str, timeout_s: float) -> dict[str, Any]:
    """Call the existing ban-safe WhatsApp sender under a hard timeout. No auto-retry."""
    from app.marketing import whatsapp_campaign

    return await asyncio.wait_for(whatsapp_campaign.send_one(phone, message), timeout=timeout_s)


def _email_contact_is_one_to_one(contact: Any) -> bool:
    """Refuse bulk-shaped addresses (comma/semicolon/newline lists). One recipient only."""
    s = str(contact or "").strip()
    if not s or "@" not in s:
        return False
    if any(sep in s for sep in (",", ";", "\n", "\r", " ")):
        return False
    return True


async def _provider_send_email(
    to_email: str,
    *,
    subject: str,
    body: str,
    timeout_s: float,
) -> dict[str, Any]:
    """Call canonical ``EmailSender`` under a hard timeout. One recipient. No auto-retry.

    Reuses the existing Hostinger/API integration — does NOT introduce a second engine.
    Missing SMTP/API credentials fail CLOSED (no provider call). Ambiguous timeout is
    raised to the caller as ``asyncio.TimeoutError`` so the attempt stays
    ``UNKNOWN_REQUIRES_REVIEW`` with no blind retry.
    """
    to = str(to_email or "").strip()
    if not _email_contact_is_one_to_one(to):
        return {"sent": False, "mode": "bulk_or_invalid_refused", "provider_called": False}

    from app.integrations.email_sender import EmailSender

    # Prefer API when available; otherwise require SMTP user+password.
    api_ok = False
    try:
        from app.integrations.email_api import api_available

        api_ok = bool(api_available())
    except Exception:
        api_ok = False

    sender = EmailSender()
    if not api_ok and not (sender.user and sender.password):
        return {"sent": False, "mode": "smtp_not_configured", "provider_called": False}

    extra_headers: dict[str, str] = {}
    try:
        from app.platform import email_unsub as _eu

        extra_headers = _eu.headers_for(to) or {}
    except Exception:
        extra_headers = {}

    ok = await asyncio.wait_for(
        sender.send_email(
            [to],
            str(subject or "").strip() or "LeadGen AI",
            str(body or ""),
            extra_headers=extra_headers,
        ),
        timeout=timeout_s,
    )
    return {
        "sent": bool(ok),
        "mode": "email_sender" if ok else "provider_refused",
        "provider_called": True,
    }


async def send(
    prospect_id: str,
    *,
    channel: str,
    step: str = _elig.STEP_INITIAL,
    pol: _policy_mod.Policy | None = None,
    prospect: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    force_dry_run: bool | None = None,
) -> dict[str, Any]:
    """Send (or simulate) one outbound message. Returns a rich result dict. Never raises.

    ``force_dry_run=True`` guarantees simulation regardless of flags (used by admin
    preview + the scheduler canary). It can NEVER be overridden to live from here.
    """
    result: dict[str, Any] = {
        "prospect_id": str(prospect_id),
        "channel": (channel or "").lower(),
        "step": step,
        "outcome": SKIPPED,
    }
    try:
        pol = pol or _policy_mod.get_policy()
        channel = (channel or "").lower()

        rec = prospect or _store.get_prospect(prospect_id) or {}
        if not rec:
            result["outcome"] = SKIPPED
            result["reason"] = "prospect_not_found"
            return result
        rec.setdefault("id", str(prospect_id))

        # 1. Eligibility (fail-closed).
        elig = _elig.evaluate(rec, channel=channel, step=step, pol=pol)
        result["eligibility"] = elig
        if elig.get("decision") != _elig.ELIGIBLE:
            result["outcome"] = BLOCKED
            result["reason"] = elig.get("decision")
            result["reason_codes"] = elig.get("reason_codes")
            return result

        # 2. Build + validate message.
        envelope = _messages.build(rec, channel=channel, step=step)
        val = _safety.validate(envelope)
        envelope["validation_status"] = val["status"]
        result["message"] = envelope
        result["validation"] = val
        if val["status"] != _safety.AUTO_APPROVED:
            result["outcome"] = BLOCKED
            result["reason"] = f"safety_{val['status']}"
            result["reason_codes"] = val.get("reasons")
            return result

        # 3. Idempotency key + duplicate guard.
        version = envelope["template_version"] + ":" + envelope["content_hash"]
        idem = idempotency_key or build_idempotency_key(str(prospect_id), channel, step, version)
        result["idempotency_key"] = idem
        if _store.attempt_exists(idem):
            result["outcome"] = DUPLICATE
            result["reason"] = "idempotent_replay"
            return result

        # 4. Decide dry-run. ANY of these ⇒ simulate.
        forced = _coerce_forced_dry_run(force_dry_run)
        dry = forced or pol.dry_run or not pol.channel_enabled(channel)
        result["dry_run"] = dry
        result["forced_dry_run"] = forced

        # 5. Persist attempt BEFORE provider (status=pending).
        contact = rec.get("phone") if channel == "whatsapp" else rec.get("email")
        _store.record_attempt(
            {
                "idempotency_key": idem,
                "prospect_id": str(prospect_id),
                "channel": channel,
                "step": step,
                "template_family": envelope["template_family"],
                "template_version": envelope["template_version"],
                "content_hash": envelope["content_hash"],
                "dry_run": dry,
                "status": "pending",
                "contact_masked": _mask(contact),
            }
        )

        # 6. Dry-run path — simulate, never call provider.
        if dry:
            _store.update_attempt_status(idem, SIMULATED, note="dry_run")
            _advance_prospect(prospect_id, channel, step, simulated=True)
            result["outcome"] = SIMULATED
            result["preview"] = envelope["body"]
            return result

        # 6b. PRE-PROVIDER SUPPRESSION RECHECK (defense in depth).
        #
        # Eligibility ran at SCHEDULING time. A prospect can reply STOP, or a
        # bounce can land, in the window between being queued and being sent —
        # a scheduler-time-only check would still deliver that message. This is
        # the last read before the provider, and it fails CLOSED.
        if _suppressed_now(rec, channel, contact):
            _store.update_attempt_status(idem, SKIPPED, note="suppressed_pre_provider")
            result["outcome"] = SKIPPED
            result["reason"] = "suppressed_pre_provider"
            return result

        # 7. LIVE path — WhatsApp (ban-safe) + Email (canonical EmailSender).
        #
        # FAIL-CLOSED PROVIDER BOUNDARY. Step 4 already forces `dry` when a caller
        # requested simulation, so this branch is unreachable under dry-run — that
        # is the point. It is the last statement before real money/reputation is
        # spent, so the guarantee is asserted here rather than inferred from a
        # boolean expression 30 lines up that a future edit could reorder or weaken.
        if forced:
            _store.update_attempt_status(idem, SIMULATED, note="forced_dry_run_guard")
            _advance_prospect(prospect_id, channel, step, simulated=True)
            logger.error(
                "[sales_autopilot.send] forced dry-run reached the provider boundary "
                "(prospect=%s channel=%s) — refusing to send. This is a bug in the "
                "dry-run decision, not a config problem.",
                prospect_id,
                channel,
            )
            result["outcome"] = SIMULATED
            result["reason"] = "forced_dry_run_guard"
            result["dry_run"] = True
            return result

        timeout_s = float(pol.get("provider_timeout_s") or 20)
        if channel == "whatsapp":
            try:
                res = await _provider_send_whatsapp(str(contact), envelope["body"], timeout_s)
            except asyncio.TimeoutError:
                _store.update_attempt_status(idem, UNKNOWN_REQUIRES_REVIEW, note="provider_timeout")
                result["outcome"] = UNKNOWN_REQUIRES_REVIEW
                result["reason"] = "provider_timeout_no_retry"
                return result
            except Exception as e:  # pragma: no cover - defensive
                _store.update_attempt_status(idem, FAILED, note=str(e)[:120])
                result["outcome"] = FAILED
                result["reason"] = str(e)[:120]
                return result
            ok = bool(res.get("sent"))
            if ok:
                _store.update_attempt_status(idem, SENT, provider_mode=res.get("mode"))
                _advance_prospect(prospect_id, channel, step, simulated=False)
                result["outcome"] = SENT
            else:
                # send_one returned a link/suppressed/no-creds mode — NOT a live send.
                _store.update_attempt_status(idem, SKIPPED, provider_mode=res.get("mode"))
                result["outcome"] = SKIPPED
                result["reason"] = res.get("mode")
            result["provider"] = res
            return result

        if channel == "email":
            # One-to-one only — bulk-shaped contact never reaches EmailSender.
            if not _email_contact_is_one_to_one(contact):
                _store.update_attempt_status(idem, SKIPPED, note="bulk_or_invalid_email_refused")
                result["outcome"] = SKIPPED
                result["reason"] = "bulk_or_invalid_email_refused"
                result["provider"] = {
                    "sent": False,
                    "mode": "bulk_or_invalid_refused",
                    "provider_called": False,
                }
                return result
            try:
                res = await _provider_send_email(
                    str(contact).strip(),
                    subject=str(envelope.get("subject") or ""),
                    body=str(envelope.get("body") or ""),
                    timeout_s=timeout_s,
                )
            except asyncio.TimeoutError:
                # Ambiguous: may have sent. Hold — never blind-retry.
                _store.update_attempt_status(idem, UNKNOWN_REQUIRES_REVIEW, note="provider_timeout")
                result["outcome"] = UNKNOWN_REQUIRES_REVIEW
                result["reason"] = "provider_timeout_no_retry"
                return result
            except Exception as e:  # pragma: no cover - defensive
                _store.update_attempt_status(idem, FAILED, note=str(e)[:120])
                result["outcome"] = FAILED
                result["reason"] = str(e)[:120]
                return result

            mode = str(res.get("mode") or "")
            if mode == "smtp_not_configured":
                # Fail CLOSED — no credentials ⇒ no send, attempt not advanced as SENT.
                _store.update_attempt_status(
                    idem, FAILED, note="smtp_not_configured", provider_mode=mode
                )
                result["outcome"] = FAILED
                result["reason"] = "smtp_not_configured"
                result["provider"] = res
                return result
            if bool(res.get("sent")):
                _store.update_attempt_status(idem, SENT, provider_mode=mode)
                _advance_prospect(prospect_id, channel, step, simulated=False)
                result["outcome"] = SENT
            else:
                _store.update_attempt_status(idem, SKIPPED, provider_mode=mode)
                result["outcome"] = SKIPPED
                result["reason"] = mode or "provider_refused"
            result["provider"] = res
            return result

        _store.update_attempt_status(idem, SKIPPED, note="unknown_channel")
        result["outcome"] = SKIPPED
        result["reason"] = "unknown_channel"
        return result
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[sales_autopilot.send] send failed: %s", e)
        result["outcome"] = FAILED
        result["reason"] = str(e)[:150]
        return result


def _suppressed_now(rec: dict[str, Any], channel: str, contact: Any) -> bool:
    """Re-read the canonical suppression ledger immediately before the provider.

    Fail-CLOSED: if the ledger cannot be read we skip the send. A missed message
    is recoverable; messaging someone who opted out is not.
    """
    try:
        from app.platform import email_unsub

        pid = str(rec.get("id") or "")
        if (channel or "").lower() == "whatsapp":
            return email_unsub.is_contact_suppressed(
                phone=str(contact or ""), prospect_id=pid, channel="whatsapp"
            )
        return email_unsub.is_contact_suppressed(
            email=str(contact or ""), prospect_id=pid, channel="email"
        )
    except Exception as e:  # pragma: no cover - defensive, fail-closed
        logger.warning("[sales_autopilot.send] pre-provider suppression check failed: %s", e)
        return True


def _coerce_forced_dry_run(value: Any) -> bool:
    """Normalise the forced-dry-run request, failing CLOSED on anything unknown.

    Only an explicit ``False`` or ``None`` means "not forced". Every other value —
    including a malformed ``"false"`` string, an int, or an arbitrary object — is
    treated as a request to SIMULATE. Getting this backwards would send real
    messages, so ambiguity resolves toward the harmless outcome.
    """
    if value is None or value is False:
        return False
    if value is True:
        return True
    return True  # unknown/malformed mode -> simulate


def _mask(contact: Any) -> str:
    s = str(contact or "")
    if "@" in s:
        name, _, dom = s.partition("@")
        return (name[:2] + "***@" + dom) if name else "***@" + dom
    d = _store.digits(s)
    return ("***" + d[-4:]) if len(d) >= 4 else "***"


def _advance_prospect(prospect_id: str, channel: str, step: str, *, simulated: bool) -> None:
    """Advance lifecycle state after a (real or simulated) attempt. Never raises."""
    try:
        rec = _store.get_prospect(prospect_id) or {"id": str(prospect_id)}
        _store.add_step_done(prospect_id, f"{step}_{channel}")
        if step == _elig.STEP_INITIAL:
            _store.mark_status(prospect_id, _store.STATUS_CONTACTED, last_contact_at=None)
        elif step in (_elig.STEP_FOLLOWUP_1, _elig.STEP_FOLLOWUP_2):
            fc = int((rec or {}).get("followup_count", 0)) + 1
            _store.mark_status(prospect_id, _store.STATUS_FOLLOWUP, followup_count=fc)
    except Exception:
        pass


__all__ = [
    "SENT",
    "SIMULATED",
    "SKIPPED",
    "BLOCKED",
    "DUPLICATE",
    "FAILED",
    "UNKNOWN_REQUIRES_REVIEW",
    "build_idempotency_key",
    "send",
]
