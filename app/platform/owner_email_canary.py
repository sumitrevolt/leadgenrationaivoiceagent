"""Owner-inbox one-shot email canary — live send WITHOUT enabling bulk outreach.

Does NOT turn on ``AUTO_EMAIL_OUTREACH`` or Sales Autopilot schedulers. Uses a
canary-specific ONE-SHOT transport (never ``EmailSender``'s Resend→Brevo→SMTP
cascade). Super-admin API is the sole entry; this module never accepts a
prospect list.

Safety:
  - one recipient only (bulk-shaped addresses refused)
  - suppression fail-closed via ONE strict validated snapshot (canary-local;
    never a second fail-open ``email_unsub`` reader; does not change globals)
  - attempt ledger read/parse/structural/authority failures block BEFORE provider I/O
  - attempt claimed under file-lock BEFORE provider (lock released before I/O)
  - idempotency key ⇒ duplicate request does not re-send
  - hard daily provider-attempt cap of 1 (pending claims count)
  - missing SMTP/API ⇒ FAILED, provider_called=false (does not consume cap)
  - exactly ONE transport/provider network attempt; timeout/error/ambiguous
    ⇒ UNKNOWN_REQUIRES_REVIEW (never fallback, never blind-retry)
  - recipient never logged in cleartext (masked only)
  - CANONICAL runtime-data: RuntimeDataError surfaces (no checkout fallback)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Literal

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
# Reputation safety: at most one provider attempt (or pending claim) per UTC day.
_DAILY_PROVIDER_CAP = 1

TransportName = Literal["resend", "brevo", "smtp"]


class AttemptLedgerError(Exception):
    """Attempt ledger unreadable or corrupt — fail closed before provider I/O."""

    def __init__(self, reason: str, *, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(reason)


class SuppressionLedgerError(Exception):
    """Suppression truth is unavailable, so the canary must not send."""


class ProviderNotCalledError(Exception):
    """A definite local failure occurred before any provider network call."""


def _attempts_path(*, create: bool = False) -> Path:
    """Resolve attempts.jsonl. ``create`` only on write paths — never on GET/preflight."""
    from app.platform import runtime_data_authority as _auth

    # RuntimeDataError must propagate in CANONICAL (and any misconfig) —
    # do NOT swallow into checkout fallback.
    path = Path(
        _auth.resolve_store_path(
            store_id="ops.owner_email_canary",
            legacy_path=Path("data") / "owner_email_canary" / "attempts.jsonl",
            target_segments=("ops", "owner_email_canary", "attempts.jsonl"),
        )
    )
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _lock_target() -> str:
    """Active attempts path string for ``file_lock`` (sidecar beside authority)."""
    return str(_attempts_path(create=False))


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


def _utc_day_start_ts() -> float:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc).timestamp()


def _append_attempt(row: dict[str, Any]) -> None:
    path = _attempts_path(create=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _validate_attempt_row(row: dict[str, Any]) -> None:
    """Strict shape for every historical row used by idempotency / daily-cap truth.

    Syntactically valid but empty/partial objects (``{}``, ``{event:attempt}``)
    must BLOCK — silently ignoring them would under-count the daily cap or miss
    an in-flight claim.
    """
    event = row.get("event")
    if event not in ("attempt", "status"):
        raise AttemptLedgerError("attempt_ledger_corrupt", detail="bad_event")
    key = row.get("idempotency_key")
    if not isinstance(key, str) or not key.strip():
        raise AttemptLedgerError("attempt_ledger_corrupt", detail="bad_idempotency_key")
    ts = row.get("ts")
    if isinstance(ts, bool) or not isinstance(ts, int | float):
        raise AttemptLedgerError("attempt_ledger_corrupt", detail="bad_ts")
    outcome = row.get("outcome")
    if not isinstance(outcome, str) or not outcome.strip():
        raise AttemptLedgerError("attempt_ledger_corrupt", detail="bad_outcome")
    pc = row.get("provider_called")
    if not isinstance(pc, bool):
        raise AttemptLedgerError("attempt_ledger_corrupt", detail="bad_provider_called")
    if event == "attempt":
        to_masked = row.get("to_masked")
        if not isinstance(to_masked, str) or not to_masked.strip():
            raise AttemptLedgerError("attempt_ledger_corrupt", detail="bad_to_masked")


def _iter_attempts() -> list[dict[str, Any]]:
    """Load attempt ledger. Missing file ⇒ []. Unreadable/corrupt ⇒ raise."""
    path = _attempts_path(create=False)
    try:
        exists = path.exists()
    except Exception as e:
        raise AttemptLedgerError(
            "attempt_ledger_unreadable",
            detail=type(e).__name__,
        ) from e
    if not exists:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        raise AttemptLedgerError(
            "attempt_ledger_unreadable",
            detail=type(e).__name__,
        ) from e
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception as e:
            raise AttemptLedgerError(
                "attempt_ledger_corrupt",
                detail=type(e).__name__,
            ) from e
        if not isinstance(row, dict):
            raise AttemptLedgerError("attempt_ledger_corrupt", detail="not_object")
        _validate_attempt_row(row)
        out.append(row)
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
    """Append-only status marker (does not rewrite history)."""
    row = {
        "idempotency_key": str(key),
        "event": "status",
        "ts": time.time(),
        **fields,
    }
    _append_attempt(row)


def _provider_slot_taken_today() -> bool:
    """True if a pending claim or any provider-called row already holds today's slot."""
    day0 = _utc_day_start_ts()
    pending: set[str] = set()
    finalized: dict[str, dict[str, Any]] = {}
    provider_keys: set[str] = set()
    for row in _iter_attempts():
        if float(row.get("ts") or 0) < day0:
            continue
        k = str(row.get("idempotency_key") or "")
        if not k:
            continue
        if row.get("provider_called"):
            provider_keys.add(k)
        if row.get("event") == "attempt" and str(row.get("outcome") or "") == "pending":
            pending.add(k)
        if row.get("event") == "status":
            finalized[k] = row
            if row.get("provider_called"):
                provider_keys.add(k)
    if provider_keys:
        return True
    for k in pending:
        fin = finalized.get(k)
        if fin is None:
            return True  # still in-flight — counts toward cap
        if fin.get("provider_called"):
            return True
        # Definite no-provider finalization released the slot.
    return False


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
    """Read-only readiness. Never creates dirs; never includes a recipient address."""
    from app.platform import runtime_data as rd

    try:
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
            "daily_provider_cap": _DAILY_PROVIDER_CAP,
            "bulk_outreach_required": False,
            "notes": [
                "Does not enable AUTO_EMAIL_OUTREACH",
                "Exactly one owner-controlled inbox per confirmed send",
                "Refresh with same idempotency_key will not resend",
            ],
        }
    except AttemptLedgerError as e:
        logger.error("[owner_email_canary] preflight ledger refused: %s", e.reason)
        return {
            "ok": False,
            "canary": "owner_inbox_one_shot",
            "outcome": BLOCKED,
            "reason": e.reason,
            "error_type": e.detail or type(e).__name__,
            "bulk_outreach_required": False,
        }
    except rd.RuntimeDataError as e:
        logger.error("[owner_email_canary] preflight authority refused: %s", type(e).__name__)
        return {
            "ok": False,
            "canary": "owner_inbox_one_shot",
            "outcome": BLOCKED,
            "reason": "runtime_data_authority_refused",
            "error_type": type(e).__name__,
            "bulk_outreach_required": False,
        }


def _validate_suppression_row(row: dict[str, Any], *, email_unsub: Any) -> dict[str, Any]:
    """Strict identity/shape for canary suppression truth. Unknown/partial ⇒ raise."""
    email = email_unsub.normalize_email(row.get("email"))
    phone = email_unsub.normalize_phone(row.get("phone"))
    prospect_id = str(row.get("prospect_id") or "").strip()
    # Empty / identity-less objects must not look like an empty ledger.
    if not email and not phone and not prospect_id:
        raise SuppressionLedgerError("suppression_ledger_untrusted")
    scope_raw = row.get("scope", email_unsub.SCOPE_EMAIL_ADDRESS)
    if scope_raw is None or not isinstance(scope_raw, str):
        raise SuppressionLedgerError("suppression_ledger_untrusted")
    scope = scope_raw.strip().lower() or email_unsub.SCOPE_EMAIL_ADDRESS
    if scope not in email_unsub._VALID_SCOPES:
        raise SuppressionLedgerError("suppression_ledger_untrusted")
    if "ts" in row:
        ts = row.get("ts")
        if isinstance(ts, bool) or not isinstance(ts, int | float):
            raise SuppressionLedgerError("suppression_ledger_untrusted")
    if "channel" in row and row.get("channel") is not None:
        if not isinstance(row.get("channel"), str):
            raise SuppressionLedgerError("suppression_ledger_untrusted")
    if "resolution" in row and row.get("resolution") is not None:
        if not isinstance(row.get("resolution"), str):
            raise SuppressionLedgerError("suppression_ledger_untrusted")
    return {
        "email": email,
        "phone": phone,
        "prospect_id": prospect_id,
        "scope": scope,
        "channel": str(row.get("channel") or "email"),
        "resolution": str(row.get("resolution") or ""),
        "ts": int(row.get("ts") or 0),
    }


def _quarantine_resolutions_from_snapshot(
    rows: list[dict[str, Any]],
) -> dict[str, str]:
    """Latest quarantine resolution per destination from ONE snapshot (no re-read)."""
    out: dict[str, tuple[int, str]] = {}
    for row in rows:
        res = str(row.get("resolution") or "")
        if not res:
            continue
        dest = str(row.get("email") or "")
        if not dest:
            continue
        ts = int(row.get("ts") or 0)
        if dest not in out or ts >= out[dest][0]:
            out[dest] = (ts, res)
    return {k: v[1] for k, v in out.items()}


def _email_blocked_by_snapshot(rows: list[dict[str, Any]], email: str) -> bool:
    """Match email against a pre-validated snapshot. Never opens the ledger."""
    if not email:
        return False
    resolutions = _quarantine_resolutions_from_snapshot(rows)
    for row in rows:
        if str(row.get("email") or "") != email:
            continue
        scope = str(row.get("scope") or "")
        if scope == "quarantine" and resolutions.get(email) == "released":
            continue
        if scope in ("email_address", "all_outreach", "quarantine"):
            return True
        if scope == "channel_contact" and str(row.get("channel") or "") == "email":
            return True
    return False


def _load_strict_suppression_snapshot() -> list[dict[str, Any]]:
    """Single atomic strict read of the suppression ledger for canary decisions.

    Missing file ⇒ []. Any I/O / decode / structural failure ⇒
    ``SuppressionLedgerError`` (uncertainty blocks). Does NOT call
    ``email_unsub.is_contact_suppressed`` / fail-open ``_iter_suppression_rows``.
    """
    from app.platform import email_unsub

    path = email_unsub._store_or_none()
    if path is None:
        raise SuppressionLedgerError("suppression_ledger_untrusted")
    try:
        is_file = path.is_file()
    except Exception as e:
        raise SuppressionLedgerError("suppression_ledger_untrusted") from e
    if not is_file:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        raise SuppressionLedgerError("suppression_ledger_untrusted") from e
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except Exception as e:
            raise SuppressionLedgerError("suppression_ledger_untrusted") from e
        if not isinstance(raw, dict):
            raise SuppressionLedgerError("suppression_ledger_untrusted")
        out.append(_validate_suppression_row(raw, email_unsub=email_unsub))
    return out


def _suppressed(email: str) -> bool:
    """Fail closed on any suppression-ledger uncertainty (canary-only).

    Send/no-send comes from the SAME strict validated snapshot — never a second
    fail-open reader (TOCTOU with ``is_contact_suppressed`` eliminated).
    """
    try:
        from app.platform import email_unsub

        rows = _load_strict_suppression_snapshot()
        return _email_blocked_by_snapshot(rows, email_unsub.normalize_email(email))
    except SuppressionLedgerError:
        raise
    except Exception as e:
        logger.warning("[owner_email_canary] suppression check failed: %s", type(e).__name__)
        raise SuppressionLedgerError("suppression_check_failed") from e


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


def _pick_one_transport() -> TransportName | None:
    """Select exactly one transport. Prefer Resend, else Brevo, else SMTP."""
    try:
        from app.config import settings

        if (settings.resend_api_key or "").strip():
            return "resend"
        if (settings.brevo_api_key or "").strip():
            return "brevo"
        if (settings.smtp_user or "").strip() and (settings.smtp_password or "").strip():
            return "smtp"
    except Exception:
        return None
    return None


async def _send_resend_once(
    *,
    to: str,
    subject: str,
    text: str,
    html: str,
    headers: dict[str, str],
) -> bool:
    """Single Resend HTTPS POST. Never falls through to Brevo/SMTP."""
    try:
        import httpx

        from app.config import settings
        from app.integrations.email_api import _from

        resend = (settings.resend_api_key or "").strip()
        if not resend:
            raise ProviderNotCalledError("resend_not_configured")
        from_email, from_name = _from()
        payload: dict[str, Any] = {
            "from": f"{from_name} <{from_email}>",
            "to": [to],
            "subject": subject,
            "html": html,
            "text": text or "",
        }
        if headers:
            payload["headers"] = dict(headers)
        client = httpx.AsyncClient(timeout=20.0)
    except ProviderNotCalledError:
        raise
    except Exception as e:
        raise ProviderNotCalledError(type(e).__name__) from e
    async with client:
        r = await client.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {resend}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    return 200 <= r.status_code < 300


async def _send_brevo_once(
    *,
    to: str,
    subject: str,
    text: str,
    html: str,
    headers: dict[str, str],
) -> bool:
    """Single Brevo HTTPS POST. Never falls through to SMTP."""
    try:
        import httpx

        from app.config import settings
        from app.integrations.email_api import _from

        brevo = (settings.brevo_api_key or "").strip()
        if not brevo:
            raise ProviderNotCalledError("brevo_not_configured")
        from_email, from_name = _from()
        payload: dict[str, Any] = {
            "sender": {"email": from_email, "name": from_name},
            "to": [{"email": to}],
            "subject": subject,
            "htmlContent": html,
            "textContent": text or "",
        }
        if headers:
            payload["headers"] = dict(headers)
        client = httpx.AsyncClient(timeout=20.0)
    except ProviderNotCalledError:
        raise
    except Exception as e:
        raise ProviderNotCalledError(type(e).__name__) from e
    async with client:
        r = await client.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key": brevo,
                "Content-Type": "application/json",
                "accept": "application/json",
            },
            json=payload,
        )
    return 200 <= r.status_code < 300


async def _send_smtp_once(
    *,
    to: str,
    subject: str,
    text: str,
    html: str,
    headers: dict[str, str],
) -> bool:
    """Single SMTP send. Never falls back to another provider."""
    try:
        import aiosmtplib

        from app.config import settings

        user = (settings.smtp_user or "").strip()
        password = (settings.smtp_password or "").strip()
        if not user or not password:
            raise ProviderNotCalledError("smtp_not_configured")
        from_email = (settings.email_from or user).strip()
        msg = MIMEMultipart("alternative")
        msg["From"] = from_email
        msg["To"] = to
        msg["Subject"] = subject
        for hk, hv in (headers or {}).items():
            if hk and hv and hk not in msg:
                msg[hk] = hv
        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))
    except ProviderNotCalledError:
        raise
    except Exception as e:
        raise ProviderNotCalledError(type(e).__name__) from e
    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=user,
        password=password,
        use_tls=True,
        timeout=min(20.0, max(1.0, _TIMEOUT_S)),
    )
    return True


async def _provider_send(to: str, timeout_s: float) -> dict[str, Any]:
    """ONE transport network attempt total — no multi-provider cascade."""
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
    transport = _pick_one_transport()
    if transport is None:
        return {"sent": False, "mode": "smtp_not_configured", "provider_called": False}

    async def _once() -> bool:
        if transport == "resend":
            return await _send_resend_once(
                to=to, subject=_CANARY_SUBJECT, text=text, html=html, headers=headers
            )
        if transport == "brevo":
            return await _send_brevo_once(
                to=to, subject=_CANARY_SUBJECT, text=text, html=html, headers=headers
            )
        return await _send_smtp_once(
            to=to, subject=_CANARY_SUBJECT, text=text, html=html, headers=headers
        )

    ok = await asyncio.wait_for(_once(), timeout=timeout_s)
    return {
        "sent": bool(ok),
        "mode": transport if ok else "provider_refused",
        "provider_called": True,
        "transport": transport,
        "list_unsubscribe_attached": bool(headers),
    }


def _claim_under_lock(
    *,
    idem: str,
    to: str,
    actor_id: str,
) -> dict[str, Any]:
    """Atomically check idempotency/cap/config and append pending. No network I/O."""
    from app.platform import runtime_data as rd
    from app.utils.file_lock import file_lock

    try:
        lock_path = _lock_target()
    except rd.RuntimeDataError:
        raise

    with file_lock(lock_path) as locked:
        if not locked:
            return {
                "claimed": False,
                "lock_failed": True,
                "reason": "idempotency_lock_unavailable",
            }
        try:
            existing = find_by_idempotency(idem)
            if existing:
                prior = latest_status(idem) or existing
                return {
                    "claimed": False,
                    "duplicate": True,
                    "prior_outcome": prior.get("outcome") or existing.get("outcome"),
                }

            cfg = _smtp_or_api_configured()
            if not cfg["send_path_ready"]:
                # Definite no-config — persist for audit, do NOT consume provider slot.
                _append_attempt(
                    {
                        "event": "attempt",
                        "ts": time.time(),
                        "idempotency_key": idem,
                        "to_masked": mask_email(to),
                        "to_hash": hashlib.sha256(to.lower().encode()).hexdigest()[:16],
                        "actor_id": str(actor_id or "")[:64],
                        "outcome": FAILED,
                        "reason": "smtp_not_configured",
                        "provider_called": False,
                    }
                )
                return {
                    "claimed": False,
                    "config_failed": True,
                    "reason": "smtp_not_configured",
                }

            if _provider_slot_taken_today():
                return {
                    "claimed": False,
                    "capped": True,
                    "reason": "daily_provider_attempt_cap",
                }

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
            return {"claimed": True}
        except AttemptLedgerError as e:
            return {
                "claimed": False,
                "ledger_failed": True,
                "reason": e.reason,
                "error_type": e.detail or type(e).__name__,
            }


async def send_canary(
    *,
    to_email: str,
    idempotency_key: str,
    confirm: bool,
    actor_id: str = "",
) -> dict[str, Any]:
    """Send exactly one owner-inbox canary. Never raises."""
    from app.platform import runtime_data as rd

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

        to = str(to_email or "").strip()
        if not is_one_to_one(to):
            result["outcome"] = SKIPPED
            result["reason"] = "bulk_or_invalid_email_refused"
            return result

        if _suppressed(to):
            result["outcome"] = SKIPPED
            result["reason"] = "suppressed"
            return result

        try:
            claim = _claim_under_lock(idem=idem, to=to, actor_id=actor_id)
        except rd.RuntimeDataError as e:
            logger.error("[owner_email_canary] send authority refused: %s", type(e).__name__)
            result["outcome"] = BLOCKED
            result["reason"] = "runtime_data_authority_refused"
            result["error_type"] = type(e).__name__
            return result

        if claim.get("duplicate"):
            result["ok"] = True
            result["outcome"] = DUPLICATE
            result["reason"] = "idempotent_replay"
            result["prior_outcome"] = claim.get("prior_outcome")
            result["provider_called"] = False
            return result

        if claim.get("config_failed"):
            result["outcome"] = FAILED
            result["reason"] = str(claim.get("reason") or "smtp_not_configured")
            result["provider_called"] = False
            return result

        if claim.get("capped"):
            result["outcome"] = BLOCKED
            result["reason"] = str(claim.get("reason") or "daily_provider_attempt_cap")
            result["provider_called"] = False
            return result

        if claim.get("lock_failed"):
            result["outcome"] = BLOCKED
            result["reason"] = str(claim.get("reason") or "idempotency_lock_unavailable")
            result["provider_called"] = False
            return result

        if claim.get("ledger_failed"):
            result["outcome"] = BLOCKED
            result["reason"] = str(claim.get("reason") or "attempt_ledger_unreadable")
            result["error_type"] = claim.get("error_type")
            result["provider_called"] = False
            return result

        if not claim.get("claimed"):
            result["outcome"] = FAILED
            result["reason"] = "claim_failed"
            return result

        # Lock released — provider I/O outside the lock.
        try:
            res = await _provider_send(to, _TIMEOUT_S)
        except ProviderNotCalledError as e:
            _update_attempt(
                idem,
                outcome=FAILED,
                reason=str(e) or "provider_not_called",
                provider_called=False,
            )
            result["outcome"] = FAILED
            result["reason"] = str(e) or "provider_not_called"
            result["provider_called"] = False
            return result
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
            # Provider was entered; treat as ambiguous for retry safety.
            _update_attempt(
                idem,
                outcome=UNKNOWN_REQUIRES_REVIEW,
                reason=type(e).__name__,
                provider_called=True,
            )
            result["outcome"] = UNKNOWN_REQUIRES_REVIEW
            result["reason"] = type(e).__name__
            result["provider_called"] = True
            return result

        mode = str(res.get("mode") or "")
        called = bool(res.get("provider_called"))
        result["provider_called"] = called
        result["provider"] = {
            "mode": mode,
            "provider_called": called,
            "transport": res.get("transport"),
            "list_unsubscribe_attached": bool(res.get("list_unsubscribe_attached")),
        }

        if mode == "smtp_not_configured" or not called:
            # Definite no-provider (race after claim) — release slot semantics via status.
            _update_attempt(
                idem, outcome=FAILED, reason="smtp_not_configured", provider_called=False
            )
            result["outcome"] = FAILED
            result["reason"] = "smtp_not_configured"
            result["provider_called"] = False
            return result

        if res.get("sent"):
            _update_attempt(idem, outcome=SENT, reason="ok", provider_called=True, mode=mode)
            result["ok"] = True
            result["outcome"] = SENT
            return result

        # Ambiguous provider refusal — never retry / never cascade.
        _update_attempt(
            idem,
            outcome=UNKNOWN_REQUIRES_REVIEW,
            reason=mode or "provider_false_ambiguous",
            provider_called=True,
        )
        result["outcome"] = UNKNOWN_REQUIRES_REVIEW
        result["reason"] = mode or "provider_false_ambiguous"
        return result
    except SuppressionLedgerError as e:
        logger.error("[owner_email_canary] suppression refused: %s", str(e))
        result["outcome"] = BLOCKED
        result["reason"] = str(e) or "suppression_check_failed"
        result["provider_called"] = False
        return result
    except AttemptLedgerError as e:
        logger.error("[owner_email_canary] ledger refused: %s", e.reason)
        result["outcome"] = BLOCKED
        result["reason"] = e.reason
        result["error_type"] = e.detail or type(e).__name__
        return result
    except rd.RuntimeDataError as e:
        logger.error("[owner_email_canary] authority refused: %s", type(e).__name__)
        result["outcome"] = BLOCKED
        result["reason"] = "runtime_data_authority_refused"
        result["error_type"] = type(e).__name__
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
    "AttemptLedgerError",
    "SuppressionLedgerError",
    "ProviderNotCalledError",
    "mask_email",
    "is_one_to_one",
    "preflight",
    "send_canary",
    "find_by_idempotency",
]
