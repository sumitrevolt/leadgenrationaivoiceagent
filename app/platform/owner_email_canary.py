"""Owner-inbox one-shot email canary — live send WITHOUT enabling bulk outreach.

Does NOT turn on ``AUTO_EMAIL_OUTREACH`` or Sales Autopilot schedulers. Reuses
canonical ``EmailSender`` + ``email_unsub`` only. Super-admin API is the sole
entry; this module never accepts a prospect list.

Safety:
  - one recipient only (bulk-shaped addresses refused)
  - suppression fail-closed
  - attempt persisted BEFORE provider
  - idempotency key ⇒ duplicate request does not re-send
  - missing SMTP/API ⇒ FAILED, provider_called=false
  - timeout ⇒ UNKNOWN_REQUIRES_REVIEW, no blind retry
  - recipient never logged in cleartext (masked only)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

SENT = "SENT"
FAILED = "FAILED"
SKIPPED = "SKIPPED"
DUPLICATE = "DUPLICATE"
BLOCKED = "BLOCKED"
UNKNOWN_REQUIRES_REVIEW = "UNKNOWN_REQUIRES_REVIEW"

_CANARY_SUBJECT = "LeadGen AI — owner inbox canary (one-shot)"
_TIMEOUT_S = float(os.getenv("OWNER_EMAIL_CANARY_TIMEOUT_S", "30") or "30")


def _store_dir() -> Path:
    from app.platform import runtime_data_authority as _auth

    try:
        p = _auth.resolve_store_path(
            store_id="ops.owner_email_canary",
            legacy_path=Path("data") / "owner_email_canary" / "attempts.jsonl",
            target_segments=("ops", "owner_email_canary", "attempts.jsonl"),
        )
        return Path(p).parent
    except Exception:
        return Path("data") / "owner_email_canary"


def _attempts_path() -> Path:
    d = _store_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "attempts.jsonl"


def mask_email(email: str) -> str:
    s = str(email or "").strip()
    if "@" not in s:
        return "***"
    name, _, dom = s.partition("@")
    return (name[:2] + "***@" + dom) if name else "***@" + dom


def is_one_to_one(email: str) -> bool:
    s = str(email or "").strip()
    if not s or "@" not in s:
        return False
    if any(sep in s for sep in (",", ";", "\n", "\r", " ")):
        return False
    local, _, domain = s.partition("@")
    if not local or not domain or "." not in domain:
        return False
    return True


def _append_attempt(row: dict[str, Any]) -> None:
    path = _attempts_path()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _iter_attempts() -> list[dict[str, Any]]:
    path = _attempts_path()
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        return []
    return out


def find_by_idempotency(key: str) -> dict[str, Any] | None:
    """Return the original attempt row for ``key`` (ignores later status markers)."""
    k = str(key or "").strip()
    if not k:
        return None
    for row in _iter_attempts():
        if str(row.get("idempotency_key") or "") == k and row.get("event") == "attempt":
            return row
    return None


def latest_status(key: str) -> dict[str, Any] | None:
    k = str(key or "").strip()
    if not k:
        return None
    last: dict[str, Any] | None = None
    for row in _iter_attempts():
        if str(row.get("idempotency_key") or "") != k:
            continue
        last = row
    return last


def _update_attempt(key: str, **fields: Any) -> None:
    """Rewrite last matching attempt status (append-only ledger + status marker)."""
    row = {
        "idempotency_key": str(key),
        "event": "status",
        "ts": time.time(),
        **fields,
    }
    _append_attempt(row)


def _smtp_or_api_configured() -> dict[str, Any]:
    api_ok = False
    try:
        from app.integrations.email_api import api_available

        api_ok = bool(api_available())
    except Exception:
        api_ok = False
    smtp_user = False
    smtp_pass = False
    try:
        from app.config import settings

        smtp_user = bool(str(getattr(settings, "smtp_user", "") or "").strip())
        smtp_pass = bool(str(getattr(settings, "smtp_password", "") or "").strip())
    except Exception:
        pass
    return {
        "api_available": api_ok,
        "smtp_user_present": smtp_user,
        "smtp_password_present": smtp_pass,
        "send_path_ready": bool(api_ok or (smtp_user and smtp_pass)),
    }


def _dns_truth() -> dict[str, Any]:
    try:
        from app.platform import deliverability_monitor as _dm

        rec = _dm.check_records() or {}
        return {
            "spf_ok": bool(rec.get("spf_ok")),
            "dkim_ok": bool(rec.get("dkim_ok")),
            "dmarc_ok": bool(rec.get("dmarc_ok")),
            "domain": str(rec.get("domain") or "")[:64] or None,
        }
    except Exception as e:
        return {"spf_ok": None, "dkim_ok": None, "dmarc_ok": None, "error": type(e).__name__}


def _flag_bool(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in ("1", "true", "yes", "on")


def preflight() -> dict[str, Any]:
    """Read-only readiness. Never includes a recipient address."""
    cfg = _smtp_or_api_configured()
    dns = _dns_truth()
    attempts = [a for a in _iter_attempts() if a.get("event") == "attempt"]
    last = attempts[-1] if attempts else None
    return {
        "ok": True,
        "canary": "owner_inbox_one_shot",
        "auto_email_outreach_enabled": _flag_bool("AUTO_EMAIL_OUTREACH"),
        "sales_autopilot_email_enabled": _flag_bool("SALES_AUTOPILOT_EMAIL_ENABLED"),
        "smtp": cfg,
        "dns": dns,
        "suppression_module": "email_unsub",
        "attempt_count": len(attempts),
        "last_attempt": (
            {
                "outcome": last.get("outcome"),
                "to_masked": last.get("to_masked"),
                "idempotency_key": last.get("idempotency_key"),
                "provider_called": last.get("provider_called"),
            }
            if last
            else None
        ),
        "bulk_outreach_required": False,
        "notes": [
            "Does not enable AUTO_EMAIL_OUTREACH",
            "Exactly one owner-controlled inbox per confirmed send",
            "Refresh with same idempotency_key will not resend",
        ],
    }


def _suppressed(email: str) -> bool:
    try:
        from app.platform import email_unsub

        return bool(email_unsub.is_contact_suppressed(email=email, channel="email"))
    except Exception as e:
        logger.warning("[owner_email_canary] suppression check failed: %s", type(e).__name__)
        return True  # fail-closed


def _body_text() -> tuple[str, str]:
    text = (
        "Namaste,\n\n"
        "Yeh LeadGen AI ka ONE-SHOT owner-inbox canary hai.\n"
        "Agar yeh mail mil gaya, delivery path live hai.\n\n"
        "Unsubscribe / stop ke liye List-Unsubscribe header use karein "
        "(ya reply STOP).\n\n"
        "— LeadGen AI Ops\n"
    )
    html = (
        "<p>Namaste,</p>"
        "<p>Yeh LeadGen AI ka <b>ONE-SHOT</b> owner-inbox canary hai.</p>"
        "<p>Agar yeh mail mil gaya, delivery path live hai.</p>"
        "<p>Unsubscribe / stop ke liye List-Unsubscribe header use karein.</p>"
        "<p>— LeadGen AI Ops</p>"
    )
    return text, html


async def _provider_send(to: str, timeout_s: float) -> dict[str, Any]:
    from app.integrations.email_sender import EmailSender

    cfg = _smtp_or_api_configured()
    if not cfg["send_path_ready"]:
        return {"sent": False, "mode": "smtp_not_configured", "provider_called": False}

    headers: dict[str, str] = {}
    try:
        from app.platform import email_unsub as _eu

        headers = _eu.headers_for(to) or {}
    except Exception:
        headers = {}

    text, html = _body_text()
    sender = EmailSender()
    ok = await asyncio.wait_for(
        sender.send_email(
            [to],
            _CANARY_SUBJECT,
            text,
            html_body=html,
            extra_headers=headers,
        ),
        timeout=timeout_s,
    )
    return {
        "sent": bool(ok),
        "mode": "email_sender" if ok else "provider_refused",
        "provider_called": True,
        "list_unsubscribe_attached": bool(headers),
    }


async def send_canary(
    *,
    to_email: str,
    idempotency_key: str,
    confirm: bool,
    actor_id: str = "",
) -> dict[str, Any]:
    """Send exactly one owner-inbox canary. Never raises."""
    result: dict[str, Any] = {
        "ok": False,
        "outcome": BLOCKED,
        "provider_called": False,
        "to_masked": mask_email(to_email),
    }
    try:
        if not confirm:
            result["outcome"] = BLOCKED
            result["reason"] = "confirm_required"
            return result

        idem = str(idempotency_key or "").strip()
        if not idem or len(idem) < 8:
            result["outcome"] = BLOCKED
            result["reason"] = "idempotency_key_required"
            return result
        result["idempotency_key"] = idem

        existing = find_by_idempotency(idem)
        if existing:
            prior = latest_status(idem) or existing
            result["ok"] = True
            result["outcome"] = DUPLICATE
            result["reason"] = "idempotent_replay"
            result["prior_outcome"] = prior.get("outcome") or existing.get("outcome")
            result["provider_called"] = False
            return result

        to = str(to_email or "").strip()
        if not is_one_to_one(to):
            result["outcome"] = SKIPPED
            result["reason"] = "bulk_or_invalid_email_refused"
            return result

        if _suppressed(to):
            result["outcome"] = SKIPPED
            result["reason"] = "suppressed"
            return result

        # Persist BEFORE provider.
        _append_attempt(
            {
                "event": "attempt",
                "ts": time.time(),
                "idempotency_key": idem,
                "to_masked": mask_email(to),
                "to_hash": hashlib.sha256(to.lower().encode()).hexdigest()[:16],
                "actor_id": str(actor_id or "")[:64],
                "outcome": "pending",
                "provider_called": False,
            }
        )

        try:
            res = await _provider_send(to, _TIMEOUT_S)
        except asyncio.TimeoutError:
            _update_attempt(
                idem,
                outcome=UNKNOWN_REQUIRES_REVIEW,
                reason="provider_timeout_no_retry",
                provider_called=True,
            )
            result["outcome"] = UNKNOWN_REQUIRES_REVIEW
            result["reason"] = "provider_timeout_no_retry"
            result["provider_called"] = True
            return result
        except Exception as e:
            _update_attempt(
                idem,
                outcome=FAILED,
                reason=type(e).__name__,
                provider_called=True,
            )
            result["outcome"] = FAILED
            result["reason"] = type(e).__name__
            result["provider_called"] = True
            return result

        mode = str(res.get("mode") or "")
        called = bool(res.get("provider_called"))
        result["provider_called"] = called
        result["provider"] = {
            "mode": mode,
            "provider_called": called,
            "list_unsubscribe_attached": bool(res.get("list_unsubscribe_attached")),
        }

        if mode == "smtp_not_configured":
            _update_attempt(
                idem, outcome=FAILED, reason="smtp_not_configured", provider_called=False
            )
            result["outcome"] = FAILED
            result["reason"] = "smtp_not_configured"
            return result

        if res.get("sent"):
            _update_attempt(idem, outcome=SENT, reason="ok", provider_called=True, mode=mode)
            result["ok"] = True
            result["outcome"] = SENT
            return result

        _update_attempt(
            idem, outcome=SKIPPED, reason=mode or "provider_refused", provider_called=called
        )
        result["outcome"] = SKIPPED
        result["reason"] = mode or "provider_refused"
        return result
    except Exception as e:  # pragma: no cover
        result["outcome"] = FAILED
        result["reason"] = type(e).__name__
        return result


__all__ = [
    "SENT",
    "FAILED",
    "SKIPPED",
    "DUPLICATE",
    "BLOCKED",
    "UNKNOWN_REQUIRES_REVIEW",
    "mask_email",
    "is_one_to_one",
    "preflight",
    "send_canary",
    "find_by_idempotency",
]
