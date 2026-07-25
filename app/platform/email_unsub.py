"""RFC 8058 one-click unsubscribe for COLD EMAIL OUTREACH (deliverability + DPDP).

WHY
---
Gmail/Yahoo 2026 bulk-sender rules expect promotional mail to carry a
``List-Unsubscribe`` header AND a ``List-Unsubscribe-Post: List-Unsubscribe=One-Click``
header (RFC 8058) so the mail client can show a native one-click unsubscribe and
POST to our endpoint. Missing this hurts inbox placement (and spam-complaint rate
must stay < 0.3%). Our cold-outreach (Rohan) previously sent NO List-Unsubscribe
header — this closes that gap.

Transactional mail (lead alerts, reports, confirmations) must NOT use these —
one-click List-Unsubscribe is for marketing/promotional mail only.

This module is fully self-contained and never-raise:
  - stateless HMAC token per email (no DB),
  - header + footer builders,
  - tiny append-only email suppression list (data/email_suppression.jsonl),
  - inert/safe even if env unset.

Env (all optional):
  EMAIL_UNSUB_SECRET  HMAC secret (falls back to SECRET_KEY, then a constant)
  PUBLIC_BASE_URL     public base (default https://leadsgenai.in)
  OUTREACH_UNSUB_MAILTO  mailto fallback (default admin@leadsgenai.in)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_SECRET = (
    os.environ.get("EMAIL_UNSUB_SECRET") or os.environ.get("SECRET_KEY") or "leadsgenai-unsub-v1"
).encode()
_STORE = Path("data") / "email_suppression.jsonl"

# --- canonical suppression scopes -------------------------------------------
#: Blocks the exact normalized email address only (hard bounce, invalid mailbox).
#: Deliberately does NOT block a valid WhatsApp number for the same contact — a
#: dead mailbox says nothing about the phone.
SCOPE_EMAIL_ADDRESS = "email_address"
#: Blocks this contact on ONE channel.
SCOPE_CHANNEL_CONTACT = "channel_contact"
#: Blocks EVERY automated outreach channel for this contact. Explicit opt-out.
SCOPE_ALL_OUTREACH = "all_outreach"

_VALID_SCOPES = frozenset({SCOPE_EMAIL_ADDRESS, SCOPE_CHANNEL_CONTACT, SCOPE_ALL_OUTREACH})


def normalize_email(value: object) -> str:
    """Lowercase + strip. The send path used to `.strip()` only while the
    suppression lookup lowercased, so a mixed-case address could be suppressed
    and still mailable. One normalizer, used by both sides."""
    return str(value or "").strip().lower()


def normalize_phone(value: object) -> str:
    """Digits only, compared on the last 10 (India-domestic invariant).

    ``+91 98765 43210``, ``919876543210`` and ``9876543210`` are the same person;
    a suppression that missed on formatting would keep messaging someone who
    asked to stop.
    """
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def _mask_email(value: str) -> str:
    name, _, dom = (value or "").partition("@")
    return (name[:2] + "***@" + dom) if name and dom else "***"


def _mask_phone(value: str) -> str:
    return ("***" + value[-4:]) if len(value) >= 4 else "***"


def _store_lock():
    """Best-effort cross-process lock — app/worker/scheduler share ./data.

    Falls back to a no-op so a lock timeout degrades to an unlocked append
    rather than dropping a suppression on the floor. Losing a suppression write
    is worse than an interleaved line: the ledger is append-only and readers
    tolerate duplicates.
    """
    try:
        from filelock import FileLock

        return FileLock(str(_STORE) + ".lock", timeout=5)
    except Exception:  # pragma: no cover - filelock always present in prod
        import contextlib

        return contextlib.nullcontext()


def _event_seen(event_id: str) -> bool:
    """True if a row with this provider/reply event id already exists."""
    if not event_id:
        return False
    try:
        return any(str(r.get("event_id") or "") == event_id for r in _iter_suppression_rows())
    except Exception:  # pragma: no cover
        return False


# Path lives on the lifecycle router: app.include_router(..., prefix="/api") +
# router prefix "/lifecycle"  ->  /api/lifecycle/outreach-unsub/{token}
_UNSUB_PATH = "/api/lifecycle/outreach-unsub"


def _base_url() -> str:
    return (os.environ.get("PUBLIC_BASE_URL") or "https://leadsgenai.in").rstrip("/")


def _mailto() -> str:
    addr = (os.environ.get("OUTREACH_UNSUB_MAILTO") or "admin@leadsgenai.in").strip()
    return f"mailto:{addr}?subject=unsubscribe"


def make_token(email: str) -> str:
    """Stateless, URL-safe HMAC token encoding the email (no DB lookup needed)."""
    e = (email or "").strip().lower()
    sig = hmac.new(_SECRET, e.encode(), hashlib.sha256).hexdigest()[:32]
    return base64.urlsafe_b64encode(f"{e}|{sig}".encode()).decode().rstrip("=")


def verify_token(token: str) -> str | None:
    """Return the email if the token is authentic, else None. Never raises."""
    try:
        pad = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode((token + pad).encode()).decode()
        e, sig = raw.rsplit("|", 1)
        good = hmac.new(_SECRET, e.encode(), hashlib.sha256).hexdigest()[:32]
        return e if hmac.compare_digest(sig, good) else None
    except Exception:
        return None


def unsub_url(email: str) -> str:
    return f"{_base_url()}{_UNSUB_PATH}/{make_token(email)}"


def headers_for(email: str) -> dict[str, str]:
    """RFC 2369 + RFC 8058 headers for ONE promotional recipient.

    Returns {} when email is blank so callers can splat unconditionally.
    """
    e = (email or "").strip()
    if not e:
        return {}
    return {
        "List-Unsubscribe": f"<{unsub_url(e)}>, <{_mailto()}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


def footer_text(email: str) -> str:
    return f"\n\n—\nIn emails se opt-out: {unsub_url(email)}"


def footer_html(email: str) -> str:
    return (
        '<p style="font-size:11px;color:#888;margin-top:16px">'
        f'Yeh emails nahi chahiye? <a href="{unsub_url(email)}">Unsubscribe</a>.'
        "</p>"
    )


def _iter_suppression_rows() -> list[dict[str, object]]:
    """Best-effort JSONL reader for ops/dashboard use. Never raises."""
    rows: list[dict[str, object]] = []
    try:
        if not _STORE.is_file():
            return rows
        with open(_STORE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        continue
                    email = normalize_email(row.get("email"))
                    phone = normalize_phone(row.get("phone"))
                    prospect_id = str(row.get("prospect_id") or "")
                    # A row is usable if it identifies a contact by ANY means.
                    # This used to require an email, which silently discarded every
                    # phone-only or prospect-only suppression row.
                    if not email and not phone and not prospect_id:
                        continue
                    rows.append(
                        {
                            "email": email,
                            "phone": phone,
                            "prospect_id": prospect_id,
                            "scope": str(row.get("scope") or SCOPE_EMAIL_ADDRESS),
                            "channel": str(row.get("channel") or "email"),
                            "reason": str(row.get("reason") or ""),
                            "source": str(row.get("source") or ""),
                            "tenant": str(row.get("tenant") or ""),
                            "event_id": str(row.get("event_id") or ""),
                            "ts": int(row.get("ts") or 0),
                        }
                    )
                except Exception:
                    continue
    except Exception:  # pragma: no cover
        return []
    return rows


def suppressed_emails() -> set[str]:
    """Return normalized suppressed emails for bulk send filtering. Never raises."""
    try:
        # Blank-guarded: phone-only / prospect-only rows carry no email, and an
        # empty string in this set would make `"" in suppressed_emails()` true.
        return {e for r in _iter_suppression_rows() if (e := normalize_email(r.get("email")))}
    except Exception:  # pragma: no cover
        return set()


def list_suppressed(limit: int = 500) -> list[dict[str, object]]:
    """Recent suppression rows, newest first, for ops/audit surfaces. Never raises."""
    try:
        n = max(1, min(int(limit or 500), 5000))
    except Exception:
        n = 500
    rows = _iter_suppression_rows()
    rows.sort(key=lambda r: int(r.get("ts") or 0), reverse=True)
    return rows[:n]


def suppress(
    email: str = "",
    reason: str = "one_click",
    *,
    scope: str = SCOPE_EMAIL_ADDRESS,
    channel: str = "email",
    phone: str = "",
    tenant: str = "",
    prospect_id: str = "",
    event_id: str = "",
    source: str = "",
) -> bool:
    """Append to the canonical suppression ledger. Never raises.

    This is the ONE suppression authority. Before scopes existed every row meant
    "block this email address", which is why a reply saying REMOVE could not be
    represented at all — the stated opt-out mechanism ("reply REMOVE") wrote
    nothing, so only the one-click link actually suppressed anyone.

    ``scope`` decides what is blocked:
      * ``SCOPE_EMAIL_ADDRESS``  — this exact address only. Hard bounce / invalid
        mailbox. Must NOT block an unrelated valid WhatsApp number.
      * ``SCOPE_CHANNEL_CONTACT`` — this contact on ``channel`` only.
      * ``SCOPE_ALL_OUTREACH``   — every automated channel for this contact.
        Explicit opt-out (STOP/REMOVE/UNSUBSCRIBE) per the cross-channel
        suppression invariant.

    ``event_id`` makes provider webhook retries and reply reprocessing idempotent.
    Legacy rows carry no ``scope`` and are read as ``SCOPE_EMAIL_ADDRESS``.
    """
    e = normalize_email(email)
    p = normalize_phone(phone)
    scope = (scope or SCOPE_EMAIL_ADDRESS).strip().lower()
    if scope not in _VALID_SCOPES:
        # Unknown scope: fail CLOSED to the broadest safe block rather than
        # silently writing a row nothing will ever match.
        logger.warning("[email_unsub] unknown scope %r -> ALL_OUTREACH", scope)
        scope = SCOPE_ALL_OUTREACH
    if not e and not p and not prospect_id:
        return False
    if event_id and _event_seen(str(event_id)):
        logger.debug("[email_unsub] duplicate event_id %s ignored", event_id)
        return True
    try:
        rec = {
            "email": e,
            "phone": p,
            "scope": scope,
            "channel": (channel or "email").strip().lower(),
            "reason": reason,
            "source": source or reason,
            "tenant": str(tenant or ""),
            "prospect_id": str(prospect_id or ""),
            "event_id": str(event_id or ""),
            "ts": int(time.time()),
        }
        _STORE.parent.mkdir(parents=True, exist_ok=True)
        with _store_lock():
            with open(_STORE, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        logger.info(
            "[email_unsub] suppressed scope=%s email=%s phone=%s (%s)",
            scope,
            _mask_email(e),
            _mask_phone(p),
            reason,
        )
        # Deliverability gate: one-click opt-out = strongest recipient negative signal
        # → feed spam-complaint-rate tracker (auto-pauses outreach at 0.25% over 7d).
        try:
            from app.platform import email_warmup

            email_warmup.record_complaint(e, f"unsub_{reason}")
        except Exception:
            pass
        return True
    except Exception as ex:  # pragma: no cover — never-raise
        logger.debug("[email_unsub] suppress failed: %s", ex)
        return False


def _row_scope(row: dict[str, object]) -> str:
    """Scope of a ledger row. Legacy rows (no scope) mean 'block this address'."""
    return str(row.get("scope") or SCOPE_EMAIL_ADDRESS).strip().lower()


def _row_blocks_email(row: dict[str, object], email: str) -> bool:
    if normalize_email(row.get("email")) != email:
        return False
    scope = _row_scope(row)
    if scope in (SCOPE_EMAIL_ADDRESS, SCOPE_ALL_OUTREACH):
        return True
    return scope == SCOPE_CHANNEL_CONTACT and str(row.get("channel") or "") == "email"


def _row_blocks_phone(row: dict[str, object], phone: str, prospect_id: str) -> bool:
    scope = _row_scope(row)
    # A dead mailbox must NEVER silence a working phone.
    if scope == SCOPE_EMAIL_ADDRESS:
        return False
    identity_match = (phone and normalize_phone(row.get("phone")) == phone) or (
        prospect_id and str(row.get("prospect_id") or "") == prospect_id
    )
    if not identity_match:
        return False
    if scope == SCOPE_ALL_OUTREACH:
        return True
    return scope == SCOPE_CHANNEL_CONTACT and str(row.get("channel") or "") == "whatsapp"


def is_suppressed(email: str) -> bool:
    """True if this email must not receive automated outreach. Never raises."""
    e = normalize_email(email)
    if not e:
        return False
    try:
        return any(_row_blocks_email(r, e) for r in _iter_suppression_rows())
    except Exception:  # pragma: no cover
        return False


def is_phone_suppressed(phone: str = "", prospect_id: str = "") -> bool:
    """True if this phone/contact must not receive automated WhatsApp. Never raises.

    Matches on the normalized phone OR the prospect id, because an explicit
    opt-out arriving by email knows the address and prospect but often not the
    number — without the prospect fallback a cross-channel opt-out would be
    unenforceable on WhatsApp, which is exactly the invariant this exists for.
    """
    p = normalize_phone(phone)
    pid = str(prospect_id or "")
    if not p and not pid:
        return False
    try:
        return any(_row_blocks_phone(r, p, pid) for r in _iter_suppression_rows())
    except Exception:  # pragma: no cover
        return False


def is_contact_suppressed(
    *, email: str = "", phone: str = "", prospect_id: str = "", channel: str = "email"
) -> bool:
    """Single entry point for eligibility checks on either channel. Never raises."""
    ch = (channel or "email").strip().lower()
    if ch == "whatsapp":
        return is_phone_suppressed(phone=phone, prospect_id=prospect_id)
    if is_suppressed(email):
        return True
    # An ALL_OUTREACH row recorded against the prospect (identity known, address
    # maybe not) still has to block email.
    pid = str(prospect_id or "")
    if not pid:
        return False
    try:
        return any(
            _row_scope(r) == SCOPE_ALL_OUTREACH and str(r.get("prospect_id") or "") == pid
            for r in _iter_suppression_rows()
        )
    except Exception:  # pragma: no cover
        return False


__all__ = [
    "make_token",
    "verify_token",
    "unsub_url",
    "headers_for",
    "footer_text",
    "footer_html",
    "suppress",
    "is_suppressed",
    "is_phone_suppressed",
    "is_contact_suppressed",
    "suppressed_emails",
    "list_suppressed",
    "normalize_email",
    "normalize_phone",
    "SCOPE_EMAIL_ADDRESS",
    "SCOPE_CHANNEL_CONTACT",
    "SCOPE_ALL_OUTREACH",
]
