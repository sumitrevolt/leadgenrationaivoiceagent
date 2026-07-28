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


def _store_path() -> Path:
    """Unified suppression ledger — resolved per call, never captured at import.

    A module-level constant froze this path when the module was first imported,
    which is exactly what makes a store impossible to redirect from a fixture
    that runs later and impossible to follow a runtime-data cutover.
    """
    from app.platform import runtime_data_authority as _auth

    return _auth.resolve_store_path(
        store_id="compliance.email_suppression",
        legacy_path=Path("data") / "email_suppression.jsonl",
        target_segments=("compliance", "email_suppression.jsonl"),
    )


def _store_or_none() -> Path | None:
    """Active ledger path, or None if the authority cannot be resolved.

    Missing file → callers treat as not-suppressed (a legitimate answer).
    Unresolvable authority → callers fail CLOSED (an outage is not consent).
    """
    try:
        return _store_path()
    except Exception as exc:  # noqa: BLE001 — any resolution failure is the same verdict
        logger.error("[email_unsub] compliance.email_suppression authority UNRESOLVABLE: %s", exc)
        return None


def __getattr__(name: str) -> Path:
    """DEPRECATED shim: ``email_unsub._STORE`` as a Path attribute.

    ``app/platform/reply_agent.py`` still reads ``_STORE.parent`` (outside this
    wave's allowed_paths). ``from email_unsub import _STORE`` freezes the Path
    once; this shim cannot deliver operation-time resolution to that form.
    Call ``_store_path()`` instead.
    """
    import warnings

    if name == "_STORE":
        message = (
            "email_unsub._STORE as a Path attribute is deprecated and does NOT "
            "track later environment changes; call _store_path() instead."
        )
        warnings.warn(message, DeprecationWarning, stacklevel=2)
        logger.error("FROZEN COMPLIANCE PATH: %s", message)
        return _store_path()
    raise AttributeError(name)


# --- canonical suppression scopes -------------------------------------------
#: Blocks the exact normalized email address only (hard bounce, invalid mailbox).
#: Deliberately does NOT block a valid WhatsApp number for the same contact — a
#: dead mailbox says nothing about the phone.
SCOPE_EMAIL_ADDRESS = "email_address"
#: Blocks this contact on ONE channel.
SCOPE_CHANNEL_CONTACT = "channel_contact"
#: Blocks EVERY automated outreach channel for this contact. Explicit opt-out.
SCOPE_ALL_OUTREACH = "all_outreach"
#: An UNRESOLVED compliance quarantine — someone asked to stop, but we could not
#: tie the request to a tenant or prospect. It blocks sending exactly like a
#: permanent record, but it is NOT a business-policy decision: it is a
#: conservative hold awaiting admin reconciliation. Collapsing it into
#: `EMAIL_ADDRESS` would make an unreviewed guess indistinguishable from a
#: verified opt-out, and nothing would ever prompt anyone to resolve it.
SCOPE_QUARANTINE = "quarantine"

_VALID_SCOPES = frozenset(
    {SCOPE_EMAIL_ADDRESS, SCOPE_CHANNEL_CONTACT, SCOPE_ALL_OUTREACH, SCOPE_QUARANTINE}
)

#: Scopes that represent a settled decision (as opposed to an open question).
_PERMANENT_SCOPES = frozenset({SCOPE_EMAIL_ADDRESS, SCOPE_CHANNEL_CONTACT, SCOPE_ALL_OUTREACH})

# --- eligibility states (distinguishable, not one boolean) -------------------
STATE_NONE = "none"
STATE_PERMANENT = "permanent"
STATE_QUARANTINE = "quarantine"

# --- suppression write outcomes ---------------------------------------------
#: Ledger written AND durable cancellation applied.
RESULT_COMPLETE = "COMPLETE"
#: An idempotent replay — the event was already recorded.
RESULT_ALREADY_APPLIED = "ALREADY_APPLIED"
#: Ledger written, but the durable prospect/follow-up transition did NOT land.
#: Sending is already blocked (eligibility + pre-provider both read the ledger);
#: only the cancellation metadata needs repair. Reporting this as success would
#: hide a real inconsistency, so it is a distinct outcome.
RESULT_NEEDS_RECONCILIATION = "SUPPRESSED_NEEDS_RECONCILIATION"
#: Nothing was written. Callers must treat this as "still sendable".
RESULT_FAILED = "FAILED"


def build_event_id(
    *,
    source: str,
    event_type: str,
    raw_id: str,
    tenant: str = "",
) -> str:
    """Namespace an idempotency key so it cannot collide across contexts.

    A bare provider/message id is NOT globally unique: two providers can emit the
    same id, the same inbound message can produce both a bounce and a complaint
    event, and the same raw id can legitimately recur in different tenants.
    Deduplicating on the bare value would silently drop a real second event.
    """
    parts = [
        str(tenant or "_global"),
        str(source or "_unknown"),
        str(event_type or "_unknown"),
        str(raw_id or ""),
    ]
    return "|".join(p.replace("|", "_") for p in parts)


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
    """Best-effort cross-process lock colocated with the ACTIVE ledger.

    Uses ``resolve_lock_path`` so the lock and the ledger share one root — a
    lock beside the legacy file while data lives externally coordinates
    nothing across five containers. When tests redirect ``_STORE``, the lock
    follows that redirected ledger instead.
    """
    try:
        from filelock import FileLock

        from app.platform import runtime_data_authority as _auth

        store = _store_path()
        auth_store = _auth.resolve_store_path(
            store_id="compliance.email_suppression",
            legacy_path=Path("data") / "email_suppression.jsonl",
            target_segments=("compliance", "email_suppression.jsonl"),
        )
        auth_lock = _auth.resolve_lock_path(
            store_id="compliance.email_suppression",
            legacy_path=Path("data") / "email_suppression.jsonl",
            target_segments=("compliance", "email_suppression.jsonl"),
        )
        try:
            same = store.expanduser().resolve() == Path(auth_store).expanduser().resolve()
        except Exception:
            same = False
        lock_path = auth_lock if same else store.with_suffix(store.suffix + ".lock")
        return FileLock(str(lock_path), timeout=5)
    except Exception:  # pragma: no cover - filelock always present in prod
        import contextlib

        return contextlib.nullcontext()


#: Carries the outcome of the most recent suppress() on this thread. `suppress()`
#: keeps its historical bool contract (many existing callers), while
#: `suppress_with_result()` exposes the explicit outcome the compliance flow needs.
_last_result: dict[str, str] = {"value": RESULT_FAILED}


def suppress_with_result(*args: object, **kwargs: object) -> str:
    """`suppress()` but returning the explicit outcome.

    One of RESULT_COMPLETE / RESULT_ALREADY_APPLIED /
    RESULT_NEEDS_RECONCILIATION / RESULT_FAILED.
    """
    ok = suppress(*args, **kwargs)  # type: ignore[arg-type]
    if not ok:
        return RESULT_FAILED
    return _last_result.get("value") or RESULT_COMPLETE


def reconcile_suppressions(limit: int = 500) -> dict[str, int]:
    """Repair contacts whose ledger row landed but whose cancellation did not.

    Bounded, idempotent, and READ-ONLY with respect to outreach — it never sends.
    Safe to call immediately after a partial failure, from a scheduled job, or
    from an admin repair command.

    A broader existing suppression is never downgraded: only ALL_OUTREACH rows
    drive the terminal status, and `mark_status` to an already-terminal value is
    a no-op.
    """
    out = {"scanned": 0, "repaired": 0, "already_ok": 0, "failed": 0}
    try:
        from app.platform.sales_autopilot import store as _sa_store

        all_rows = _iter_suppression_rows()
        if all_rows is None:
            return out
        rows = [r for r in all_rows if _row_scope(r) == SCOPE_ALL_OUTREACH]
        seen: set[str] = set()
        for row in rows[: max(1, int(limit))]:
            pid = str(row.get("prospect_id") or "")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            out["scanned"] += 1
            rec = _sa_store.get_prospect(pid)
            if rec is None:
                continue
            if rec.get("status") == _sa_store.STATUS_OPTED_OUT:
                out["already_ok"] += 1
                continue
            if _cancel_pending_outreach(
                scope=SCOPE_ALL_OUTREACH,
                prospect_id=pid,
                reason=str(row.get("reason") or "reconciled"),
            ):
                out["repaired"] += 1
            else:
                out["failed"] += 1
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[email_unsub] reconciliation failed: %s", e)
    return out


def _append_row(rec: dict[str, object]) -> None:
    """Append one ledger row under the shared cross-process lock."""
    # Resolver called at each site, not bound to a local: `runtime_data_scan`
    # attributes a finding to the expression it sees, so `open(store, ...)`
    # reported the bare name `store` and the allowlist entry declaring this
    # module's store stopped binding — the failure that turned main red.
    _store_path().parent.mkdir(parents=True, exist_ok=True)
    with _store_lock():
        with open(_store_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _event_seen(event_id: str) -> bool:
    """True if a row with this provider/reply event id already exists."""
    if not event_id:
        return False
    try:
        rows = _iter_suppression_rows()
        if rows is None:
            # Unresolvable authority: treat as unseen so suppress() still
            # attempts a write (which will itself fail closed), rather than
            # claiming a duplicate that we cannot verify.
            return False
        return any(str(r.get("event_id") or "") == event_id for r in rows)
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


def _iter_suppression_rows() -> list[dict[str, object]] | None:
    """Best-effort JSONL reader. None = authority unresolvable (fail closed).

    An empty list means the file is missing or has no usable rows — that is a
    legitimate not-suppressed answer. None means we cannot trust any answer.
    """
    # Probe for an unresolvable authority (None => cannot trust any answer), then
    # resolve at the I/O sites so the scanner keeps seeing `_store_path` rather
    # than a local name. See _append_row for why that matters.
    if _store_or_none() is None:
        return None
    rows: list[dict[str, object]] = []
    try:
        if not _store_path().is_file():
            return rows
        with open(_store_path(), encoding="utf-8") as f:
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
                            # Quarantine lifecycle. Dropping these here would make
                            # a released hold look active forever — the same
                            # fixed-key-set bug that silently discarded scope and
                            # phone before.
                            "resolution": str(row.get("resolution") or ""),
                            "evidence": str(row.get("evidence") or ""),
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
        rows = _iter_suppression_rows()
        if rows is None:
            # Decision APIs (is_suppressed / is_contact_suppressed) fail CLOSED
            # when the authority is unresolvable. This bulk set cannot invent
            # every address; callers that gate a send must use those APIs.
            return set()
        # Blank-guarded: phone-only / prospect-only rows carry no email, and an
        # empty string in this set would make `"" in suppressed_emails()` true.
        return {e for r in rows if (e := normalize_email(r.get("email")))}
    except Exception:  # pragma: no cover
        return set()


def list_suppressed(limit: int = 500) -> list[dict[str, object]]:
    """Recent suppression rows, newest first, for ops/audit surfaces. Never raises."""
    try:
        n = max(1, min(int(limit or 500), 5000))
    except Exception:
        n = 500
    rows = _iter_suppression_rows()
    if rows is None:
        return []
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
    _last_result["value"] = RESULT_FAILED
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
        _last_result["value"] = RESULT_ALREADY_APPLIED
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
        _store_path().parent.mkdir(parents=True, exist_ok=True)
        with _store_lock():
            with open(_store_path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        logger.info(
            "[email_unsub] suppressed scope=%s email=%s phone=%s (%s)",
            scope,
            _mask_email(e),
            _mask_phone(p),
            reason,
        )
        # SAFETY ORDER: the ledger write above is the load-bearing one — once it
        # lands, eligibility and the pre-provider recheck both block the send.
        # Cancellation metadata is a second, separate write; if it fails the
        # contact is still protected, but the state is inconsistent and must be
        # reported as such rather than as plain success.
        _cancelled = _cancel_pending_outreach(
            scope=scope, prospect_id=str(prospect_id or ""), reason=reason
        )
        _last_result["value"] = RESULT_COMPLETE if _cancelled else RESULT_NEEDS_RECONCILIATION
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


def _cancel_pending_outreach(*, scope: str, prospect_id: str, reason: str) -> bool:
    """Durably stop scheduled follow-ups for a suppressed contact. Never raises.

    There is no pending-follow-up QUEUE to delete from: sales-autopilot follow-ups
    are *derived* on each tick by ``followups.due_followups`` from prospect state.
    The durable equivalent of "cancel" is therefore a terminal prospect status,
    which both ``due_followups`` (hard-stop list) and ``eligibility`` (opted_out
    gate) already honour. Writing that status is what makes cancellation real
    rather than relying solely on the pre-provider recheck.

    Scope-correct by construction:
      * ALL_OUTREACH  -> terminal opted-out status; stops email AND WhatsApp.
      * EMAIL_ADDRESS -> records the email block only; must NOT stop WhatsApp,
        because a dead mailbox is not an opt-out.
    """
    if not prospect_id:
        # No prospect to transition. Nothing pending exists to cancel, so this
        # is a complete outcome — not a partial one.
        return True
    try:
        from app.platform.sales_autopilot import store as _sa_store

        if scope == SCOPE_ALL_OUTREACH:
            _sa_store.mark_status(
                prospect_id,
                _sa_store.STATUS_OPTED_OUT,
                suppression_reason=reason,
                suppressed_at=int(time.time()),
                suppression_scope=scope,
            )
        elif scope in (SCOPE_EMAIL_ADDRESS, SCOPE_CHANNEL_CONTACT):
            # Durable marker without a status change — the contact may still be
            # reachable on another channel.
            _sa_store.mark_status(
                prospect_id,
                (_sa_store.get_prospect(prospect_id) or {}).get("status") or _sa_store.STATUS_NEW,
                email_suppressed=True,
                suppression_reason=reason,
                suppressed_at=int(time.time()),
                suppression_scope=scope,
            )
        return True
    except Exception as e:  # never break the suppression write
        logger.warning(
            "[email_unsub] cancellation FAILED for prospect=%s (%s) — suppression "
            "still holds; state needs reconciliation",
            prospect_id,
            e,
        )
        return False


def _row_scope(row: dict[str, object]) -> str:
    """Scope of a ledger row. Legacy rows (no scope) mean 'block this address'."""
    return str(row.get("scope") or SCOPE_EMAIL_ADDRESS).strip().lower()


def _quarantine_resolutions() -> dict[str, str]:
    """Latest resolution per destination, derived from the append-only ledger.

    Resolution CANNOT be a per-row flag: the ledger is append-only, so the
    original hold row is never rewritten and would keep blocking forever after a
    release (and would keep re-resolving as "not yet resolved"). The state of a
    quarantine is therefore the newest resolution marker for that destination.
    """
    out: dict[str, tuple[int, str]] = {}
    rows = _iter_suppression_rows()
    if rows is None:
        return {}
    for row in rows:
        res = str(row.get("resolution") or "")
        if not res:
            continue
        dest = normalize_email(row.get("email"))
        ts = int(row.get("ts") or 0)
        if dest and (dest not in out or ts >= out[dest][0]):
            out[dest] = (ts, res)
    return {k: v[1] for k, v in out.items()}


def _row_is_active(row: dict[str, object], resolutions: dict[str, str] | None = None) -> bool:
    """False once a quarantine for this destination has been RELEASED."""
    if _row_scope(row) != SCOPE_QUARANTINE:
        return True
    res = (resolutions if resolutions is not None else _quarantine_resolutions()).get(
        normalize_email(row.get("email")), ""
    )
    return res != "released"


def _row_blocks_email(row: dict[str, object], email: str) -> bool:
    if normalize_email(row.get("email")) != email:
        return False
    if not _row_is_active(row):
        return False
    scope = _row_scope(row)
    if scope in (SCOPE_EMAIL_ADDRESS, SCOPE_ALL_OUTREACH, SCOPE_QUARANTINE):
        return True
    return scope == SCOPE_CHANNEL_CONTACT and str(row.get("channel") or "") == "email"


def _row_blocks_phone(row: dict[str, object], phone: str, prospect_id: str) -> bool:
    if not _row_is_active(row):
        return False
    scope = _row_scope(row)
    # A dead mailbox must NEVER silence a working phone. A quarantine is an
    # email-destination hold for the same reason: we only know the address.
    if scope in (SCOPE_EMAIL_ADDRESS, SCOPE_QUARANTINE):
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
    """True if this email must not receive automated outreach. Never raises.

    Missing ledger file → not suppressed (a missing file is an answer).
    Unresolvable authority → suppressed (an outage is not consent).
    """
    e = normalize_email(email)
    if not e:
        return False
    try:
        rows = _iter_suppression_rows()
        if rows is None:
            return True
        return any(_row_blocks_email(r, e) for r in rows)
    except Exception:  # pragma: no cover
        return False


def is_phone_suppressed(phone: str = "", prospect_id: str = "") -> bool:
    """True if this phone/contact must not receive automated WhatsApp. Never raises.

    Matches on the normalized phone OR the prospect id, because an explicit
    opt-out arriving by email knows the address and prospect but often not the
    number — without the prospect fallback a cross-channel opt-out would be
    unenforceable on WhatsApp, which is exactly the invariant this exists for.

    Unresolvable authority → suppressed (fail closed).
    """
    p = normalize_phone(phone)
    pid = str(prospect_id or "")
    if not p and not pid:
        return False
    try:
        rows = _iter_suppression_rows()
        if rows is None:
            return True
        return any(_row_blocks_phone(r, p, pid) for r in rows)
    except Exception:  # pragma: no cover
        return False


def suppression_state(
    *, email: str = "", phone: str = "", prospect_id: str = "", channel: str = "email"
) -> str:
    """Explicit eligibility state: STATE_PERMANENT / STATE_QUARANTINE / STATE_NONE.

    `is_contact_suppressed()` remains a boolean for existing callers, but the
    three conditions are NOT the same thing and must be distinguishable
    internally: a verified opt-out is a settled decision, while a quarantine is
    an open question that someone still has to answer.

    Unresolvable authority → STATE_PERMANENT (fail closed).
    """
    try:
        ch = (channel or "email").strip().lower()
        e = normalize_email(email)
        p = normalize_phone(phone)
        pid = str(prospect_id or "")
        rows = _iter_suppression_rows()
        if rows is None:
            return STATE_PERMANENT
        matched: list[dict[str, object]] = []
        for row in rows:
            if ch == "whatsapp":
                if _row_blocks_phone(row, p, pid):
                    matched.append(row)
            elif _row_blocks_email(row, e) or (
                pid
                and _row_scope(row) == SCOPE_ALL_OUTREACH
                and str(row.get("prospect_id") or "") == pid
                and _row_is_active(row)
            ):
                matched.append(row)
        if not matched:
            return STATE_NONE
        # A settled decision outranks an open question — a real opt-out must not
        # be downgraded to "quarantine" just because a stray hold also exists.
        if any(_row_scope(r) in _PERMANENT_SCOPES for r in matched):
            return STATE_PERMANENT
        return STATE_QUARANTINE
    except Exception as e:  # pragma: no cover - fail closed
        logger.warning("[email_unsub] suppression_state failed: %s", e)
        return STATE_PERMANENT


def resolve_quarantine(
    destination: str,
    *,
    resolution: str,
    tenant: str = "",
    prospect_id: str = "",
    resolved_by: str = "admin",
    evidence: str = "",
) -> str:
    """Convert an unresolved quarantine into a settled outcome. Idempotent.

    ``resolution``:
      * ``"suppress"``  — confirm it; writes the corresponding permanent record.
      * ``"released"``  — verified false positive. REQUIRES explicit evidence,
        because releasing a hold that a real person asked for is the one
        irreversible mistake available here.
    """
    dest = normalize_email(destination)
    if not dest:
        return RESULT_FAILED
    if resolution == "released" and not str(evidence or "").strip():
        logger.warning("[email_unsub] quarantine release refused: no evidence supplied")
        return RESULT_FAILED
    try:
        rows = _iter_suppression_rows()
        if rows is None:
            return RESULT_FAILED
        # Already resolved (either way) -> idempotent no-op.
        resolutions: dict[str, tuple[int, str]] = {}
        for row in rows:
            res = str(row.get("resolution") or "")
            if not res:
                continue
            d = normalize_email(row.get("email"))
            ts = int(row.get("ts") or 0)
            if d and (d not in resolutions or ts >= resolutions[d][0]):
                resolutions[d] = (ts, res)
        if resolutions.get(dest):
            return RESULT_ALREADY_APPLIED
        has_open_hold = any(
            _row_scope(r) == SCOPE_QUARANTINE and normalize_email(r.get("email")) == dest
            for r in rows
        )
        if not has_open_hold:
            return RESULT_ALREADY_APPLIED
        if resolution == "suppress":
            scope = SCOPE_ALL_OUTREACH if prospect_id else SCOPE_EMAIL_ADDRESS
            suppress(
                dest,
                reason="quarantine_confirmed",
                scope=scope,
                tenant=tenant,
                prospect_id=prospect_id,
                source=f"resolved_by:{resolved_by}",
                event_id=build_event_id(
                    source="admin", event_type="quarantine_confirm", raw_id=dest, tenant=tenant
                ),
            )
        _append_row(
            {
                "email": dest,
                "phone": "",
                "scope": SCOPE_QUARANTINE,
                "channel": "email",
                "reason": f"quarantine_{resolution}",
                "source": f"resolved_by:{resolved_by}",
                "tenant": str(tenant or ""),
                "prospect_id": str(prospect_id or ""),
                "event_id": "",
                "resolution": resolution,
                "evidence": str(evidence or "")[:300],
                "ts": int(time.time()),
            }
        )
        return RESULT_COMPLETE
    except Exception as e:  # pragma: no cover
        logger.warning("[email_unsub] quarantine resolution failed: %s", e)
        return RESULT_FAILED


def list_quarantined(limit: int = 200) -> list[dict[str, object]]:
    """Open compliance quarantines awaiting admin reconciliation."""
    try:
        rows = _iter_suppression_rows()
        if rows is None:
            return []
        out = [r for r in rows if _row_scope(r) == SCOPE_QUARANTINE and _row_is_active(r)]
        out.sort(key=lambda r: int(r.get("ts") or 0), reverse=True)
        return out[: max(1, int(limit))]
    except Exception:  # pragma: no cover
        return []


def is_contact_suppressed(
    *, email: str = "", phone: str = "", prospect_id: str = "", channel: str = "email"
) -> bool:
    """Single entry point for eligibility checks on either channel. Never raises.

    Unresolvable authority → suppressed (fail closed).
    """
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
        rows = _iter_suppression_rows()
        if rows is None:
            return True
        return any(
            _row_scope(r) == SCOPE_ALL_OUTREACH and str(r.get("prospect_id") or "") == pid
            for r in rows
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
    "SCOPE_QUARANTINE",
    "suppression_state",
    "resolve_quarantine",
    "list_quarantined",
    "reconcile_suppressions",
    "build_event_id",
    "suppress_with_result",
    "STATE_NONE",
    "STATE_PERMANENT",
    "STATE_QUARANTINE",
]
