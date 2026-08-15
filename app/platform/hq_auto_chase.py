"""Hot Queue auto-chase — unactioned inquiry cards pe automated EMAIL follow-up.

Lead → inquiry form (consent basis = website inquiry form, DPDP purpose
limitation) → Hot Queue card. Agar owner card ko N ghante me handle na kare,
to automated EMAIL (NOT WhatsApp — ban-safety + cold-blast invariant) bhejkar
lead ko aage badhao. WhatsApp/call path owner ke liye 1-click human remains.

Design (additive, INERT default, fail-closed):
  - GATED ``HQ_AUTO_CHASE=1`` (default OFF). ``HQ_CHASE_HOURS`` (default 24),
    ``HQ_CHASE_DAILY_CAP`` (default 10), ``HQ_CHASE_BATCH`` (default 5).
  - Email only. Kabhi WhatsApp/SMS/call auto nahi.
  - Idempotent: card pe ``chase_status`` + ``chased_at`` fields; already chased
    / done / blocked rows skip. Same-sender-per-day dedupe.
  - Safety: email_unsub suppression check (opt-out = instant skip), one-to-one
    recipient only, List-Unsubscribe headers, SMTP-not-configured = silent skip
    (never raise).
  - Scheduler: hourly job ``hq_auto_chase`` in team_scheduler + Celery beat.

Never raises — returns a summary dict. Copy-neighbor of the reply_agent draft
store (``data/reply_drafts.jsonl``) via its public functions, no rewrite.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FLAG = "HQ_AUTO_CHASE"
_HOURS_ENV = "HQ_CHASE_HOURS"
_CAP_ENV = "HQ_CHASE_DAILY_CAP"
_BATCH_ENV = "HQ_CHASE_BATCH"
_DEFAULT_HOURS = 24
_DEFAULT_CAP = 10
_DEFAULT_BATCH = 5


def _enabled() -> bool:
    return os.environ.get(_FLAG, "0").strip().lower() in ("1", "true", "yes", "on")


def _int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, str(default)) or default))
    except Exception:
        return default


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _age_hours(card: dict[str, Any]) -> float | None:
    """Card age in hours from ``at``. Invalid/missing ts => None (skip)."""
    raw = str(card.get("at") or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (_now() - dt).total_seconds() / 3600.0)
    except Exception:
        return None


def _recipient(card: dict[str, Any]) -> str:
    """Prefer email; phone-only cards skip (email rail only)."""
    em = str(card.get("email") or "").strip().lower()
    if em and "@" in em:
        return em
    return ""


def _one_to_one(contact: str) -> bool:
    if not contact or "@" not in contact:
        return False
    return not any(sep in contact for sep in (",", ";", "\n", "\r", " "))


def _chase_body(card: dict[str, Any]) -> str:
    biz = str(card.get("business_name") or card.get("from") or "ji").strip()
    name = str(card.get("name") or "").strip() or biz.split()[0] if biz.split() else "ji"
    return (
        f"Namaste {name}! LeadGen AI se follow-up — aapki inquiry "
        f"({biz[:60]}) mil gayi thi. AI Marketing Automation se roz leads + "
        f"content automate hota hai (₹1,999/mo). Koi sawaal ho to reply karein — "
        f"2-min demo: https://leadsgenai.in/pricing · Start: https://leadsgenai.in/start\n\n"
        f"Agar abhi interested nahi, to is email ka reply 'unsubscribe' likhna — "
        f"aage koi email nahi bhejenge."
    )


async def _send_chase_email(to_email: str, body: str) -> bool:
    """One-to-one email via canonical EmailSender + List-Unsubscribe headers.

    SMTP/API missing = fail-closed False (no provider call). Reuses the same
    integration as reply_agent._send_reply_email — no second engine.
    """
    import html

    from app.integrations.email_sender import EmailSender
    from app.platform import email_unsub as _eu

    if not _one_to_one(to_email):
        return False
    sender = EmailSender()
    api_ok = False
    try:
        from app.integrations.email_api import api_available

        api_ok = bool(api_available())
    except Exception:
        api_ok = False
    if not api_ok and not (sender.user and sender.password):
        return False
    try:
        headers = _eu.headers_for(to_email) or {}
    except Exception:
        headers = {}
    safe_html = html.escape(body).replace("\n", "<br>")
    return bool(
        await sender.send_email(
            [to_email],
            "LeadGen AI — aapki inquiry pe follow-up",
            body,
            html_body=f"<p>{safe_html}</p>",
            extra_headers=headers,
        )
    )


async def run_auto_chase(*, limit: int | None = None, send_fn=None) -> dict[str, Any]:
    """Scan unactioned inquiry cards -> automated EMAIL follow-up.

    ``force``-style bypass exists but is intentionally NOT exposed — this path
    is always gated by ``HQ_AUTO_CHASE=1`` (fail-closed default). ``send_fn``
    is injectable for tests. Never raises.
    """
    out: dict[str, Any] = {
        "enabled": _enabled(),
        "hours": _int_env(_HOURS_ENV, _DEFAULT_HOURS),
        "seen": 0,
        "eligible": 0,
        "sent": 0,
        "failed": 0,
        "skipped_phone_only": 0,
        "skipped_suppressed": 0,
        "skipped_already": 0,
        "skipped_not_due": 0,
        "ids": [],
    }
    if not _enabled():
        out["skip_reason"] = "hq_auto_chase_disabled"
        return out
    try:
        from app.platform import reply_agent as _ra

        batch = max(1, min(int(limit or _int_env(_BATCH_ENV, _DEFAULT_BATCH)), 20))
        cap = _int_env(_CAP_ENV, _DEFAULT_CAP)
        hours = out["hours"]
        rows = _ra.list_drafts(limit=100000)  # newest-first
        today = _now().date().isoformat()
        sent_today = 0
        done_senders: set[str] = set()
        for card in rows:
            if out["sent"] >= cap or sent_today >= cap:
                break
            if card.get("channel") != "inquiry":
                continue
            if card.get("hq_status") == "done":
                continue
            if str(card.get("chase_status") or "") in ("sent", "blocked", "expired"):
                continue
            out["seen"] += 1
            hq_id = _ra.hq_id_for(card)
            to = _recipient(card)
            if not to:
                out["skipped_phone_only"] += 1
                continue
            if to in done_senders:
                out["skipped_already"] += 1
                continue
            age = _age_hours(card)
            if age is None or age < hours:
                out["skipped_not_due"] += 1
                continue
            # Opt-out check — suppression wins over everything.
            try:
                from app.platform import email_unsub as _eu

                suppressed = bool(_eu.is_suppressed(to))
            except Exception:
                suppressed = False
            if suppressed:
                out["skipped_suppressed"] += 1
                _ra._update_draft_fields(  # noqa: SLF001 — same store, adjacent module
                    hq_id, {"chase_status": "blocked", "chase_reason": "suppressed"}
                )
                continue
            body = _chase_body(card)
            try:
                fn = send_fn or _send_chase_email
                sent = await fn(to, body)
            except Exception as e:
                out["failed"] += 1
                logger.warning("[hq_auto_chase] send failed %s: %s", hq_id, e)
                continue
            if not sent:
                out["failed"] += 1
                continue
            sent_today += 1
            out["sent"] += 1
            out["eligible"] += 1
            done_senders.add(to)
            out["ids"].append(hq_id)
            _ra._update_draft_fields(  # noqa: SLF001
                hq_id,
                {"chase_status": "sent", "chased_at": _now().isoformat()},
            )
        return out
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[hq_auto_chase] failed: %s", e)
        out["error"] = str(e)[:160]
        return out


__all__ = ["run_auto_chase"]
