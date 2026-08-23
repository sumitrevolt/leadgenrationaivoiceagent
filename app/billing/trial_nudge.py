"""Trial-to-paid nudge — BLK-02: expiring/expired trials ko Starter UPI email.

Trial signup (consent basis = website signup, DPDP purpose limitation) ke baad
jo user pay nahi karta, uske liye automated EMAIL nudge with 1-tap UPI link.
Portal-side banner pehle se tha (customer_dashboard_builders._trial_banner);
yeh OUTBOUND half hai jo REVENUE_BLOCKERS.md BLK-02 close karta hai.

Design (additive, INERT default, fail-closed) — copy-neighbor hq_auto_chase +
billing/dunning:
  - GATED ``TRIAL_NUDGE_ENABLED=1`` (default OFF = run no-op).
    ``TRIAL_NUDGE_HARD_OFF=1`` emergency precedence (hamesha blocks).
    ``TRIAL_NUDGE_DAYS_BEFORE`` (default 2), ``TRIAL_NUDGE_REMIND_H`` (default
    72h same-client re-nudge gap), ``TRIAL_NUDGE_MAX_PER_CLIENT`` (default 3),
    ``TRIAL_NUDGE_BATCH`` (default 5/run == daily, job daily hai).
  - Email only. WhatsApp text sirf OWNER 1-click human send ke liye return
    hota hai — kabhi auto-send NAHI (ban-safety invariant).
  - Paid/active clients KABHI eligible nahi (status gate — billing truth).
  - Idempotent: client record pe ``trial_nudge_stage/at/count`` stamps
    (clients_store whitelist) — koi naya data-file store NAHI.
  - Safety: email_unsub suppression = instant skip; one-to-one recipient;
    List-Unsubscribe headers; SMTP-missing = silent skip. Never raises.
  - Scheduler: daily job ``trial_nudge`` in team_scheduler + Celery beat
    (staff-trial-nudge-daily 09:50 IST); RUN_DUE_EXCLUDE (no catch-up flood).

Price single source = marketing/packages.py (get_starter_price_inr / PACKAGES)
— billing truth contract, portal banner jaisa hi.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FLAG = "TRIAL_NUDGE_ENABLED"
_HARD_OFF = "TRIAL_NUDGE_HARD_OFF"
_DAYS_ENV = "TRIAL_NUDGE_DAYS_BEFORE"
_REMIND_ENV = "TRIAL_NUDGE_REMIND_H"
_MAX_ENV = "TRIAL_NUDGE_MAX_PER_CLIENT"
_BATCH_ENV = "TRIAL_NUDGE_BATCH"
_DEFAULT_DAYS = 2
_DEFAULT_REMIND_H = 72
_DEFAULT_MAX = 3
_DEFAULT_BATCH = 5

PRICING_URL = "https://leadsgenai.in/pricing"


def _enabled() -> bool:
    return os.environ.get(_FLAG, "0").strip().lower() in ("1", "true", "yes", "on")


def _hard_off() -> bool:
    return os.environ.get(_HARD_OFF, "0").strip().lower() in ("1", "true", "yes", "on")


def _int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, str(default)) or default))
    except Exception:
        return default


def _now() -> datetime:
    return datetime.now(timezone.utc)


def starter_price_inr() -> int:
    """Canonical Starter price — packages.py single source. Kabhi raise nahi."""
    try:
        from app.marketing.packages import PACKAGES, get_starter_price_inr

        for p in PACKAGES:
            if str(p.get("key") or "") == "starter":
                return int(
                    p.get("price_inr_month") or p.get("price_inr") or get_starter_price_inr()
                )
        return int(get_starter_price_inr())
    except Exception:
        return 1999


def build_message(stage: str, biz: str, days_left: int, price: int | None = None) -> dict[str, str]:
    """Hinglish nudge message (subject + body + wa_text). Pure function — testable."""
    b = (biz or "Aapka business").strip()
    amt = f"₹{int(price or starter_price_inr()):,}"
    unsub = (
        "\n\nAgar aap interested nahi hain to is email ko 'unsubscribe' reply "
        "karein — aage koi email nahi aayega."
    )
    if stage == "expired":
        subject = f"{b} — trial khatam, aapka setup safe hai (1-click restart {amt}/mahina)"
        body = (
            f"Namaste {b} team,\n\n"
            f"Aapka FREE trial khatam ho gaya. Koi baat nahi — aapka pura setup "
            f"(posts, leads, mini-site) safe pada hai. Starter {amt}/mahina se "
            f"phir se shuru karo aur roz ka automated content + leads wapas chalu:\n\n"
            f"  Plans: {PRICING_URL}\n"
            f"{unsub}"
        )
        wa_text = (
            f"Namaste! {b} ka free trial khatam ho gaya. Aapka setup safe hai — "
            f"Starter {amt}/mahina se wapas shuru kar sakte hain: {PRICING_URL}"
        )
    else:
        d = max(0, int(days_left or 0))
        subject = f"{b} — trial {d} din me khatam ({amt}/mahina pe continue karo)"
        body = (
            f"Namaste {b} team,\n\n"
            f"Aapka FREE trial {d} din me khatam ho raha hai. Content aur lead-capture "
            f"ruke na isliye abhi Starter {amt}/mahina pe upgrade kar lo — jo bana "
            f"hua sab waise ka waisa chalega:\n\n"
            f"  Plans: {PRICING_URL}\n"
            f"{unsub}"
        )
        wa_text = (
            f"Namaste! {b} ka free trial {d} din me khatam ho raha hai. Continue "
            f"karna ho to Starter {amt}/mahina: {PRICING_URL}"
        )
    return {"subject": subject, "body": body, "wa_text": wa_text}


async def _ensure_pay_link(biz: str, amount: int) -> str:
    """UPI intent deep-link (Razorpay removed 2026-06-18; manual UPI canonical).

    VPA unset = pricing-page fallback. Copy of dunning._ensure_pay_link pattern.
    Never raises.
    """
    try:
        from app.platform.upi_config import get_vpa

        vpa = str(get_vpa() or "").strip()
        if vpa and amount:
            note = f"LeadsGenAI+{(biz or 'starter').replace(' ', '+')[:30]}"
            return f"upi://pay?pa={vpa}&am={amount}&tn={note}&cu=INR"
    except Exception as e:
        logger.debug(f"[trial_nudge] upi link skipped: {e}")
    return PRICING_URL


def _one_to_one(contact: str) -> bool:
    if not contact or "@" not in contact:
        return False
    return not any(sep in contact for sep in (",", ";", "\n", "\r", " "))


async def _send_nudge_email(to_email: str, subject: str, body: str) -> bool:
    """One-to-one email via canonical EmailSender + List-Unsubscribe headers.

    SMTP/API missing = fail-closed False. Same integration as
    hq_auto_chase._send_chase_email — no second engine. Never raises.
    """
    import html

    if not _one_to_one(to_email):
        return False
    try:
        from app.integrations.email_api import api_available
        from app.integrations.email_sender import EmailSender
        from app.platform import email_unsub as _eu

        sender = EmailSender()
        api_ok = False
        try:
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
                subject,
                body,
                html_body=f"<p>{safe_html}</p>",
                extra_headers=headers,
            )
        )
    except Exception as e:
        logger.warning(f"[trial_nudge] send failed {to_email}: {e}")
        return False


def _stage_for(st: dict[str, Any], days_before: int) -> str:
    """trial_status dict -> nudge stage ("expiring"/"expired") ya ""."""
    try:
        if st.get("expired"):
            return "expired"
        if st.get("active") and int(st.get("days_left") or 0) <= days_before:
            return "expiring"
    except Exception:
        pass
    return ""


def _hours_since(iso_raw: str) -> float | None:
    raw = str(iso_raw or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (_now() - dt).total_seconds() / 3600.0)
    except Exception:
        return None


async def run_trial_nudge(*, limit: int | None = None, send_fn=None) -> dict[str, Any]:
    """Daily sweep: expiring/expired trials -> Starter UPI nudge email.

    Always gated by ``TRIAL_NUDGE_ENABLED=1`` (+ HARD_OFF precedence) —
    fail-closed default. ``send_fn`` injectable for tests. Never raises.
    """
    out: dict[str, Any] = {
        "enabled": _enabled(),
        "hard_off": _hard_off(),
        "seen": 0,
        "eligible": 0,
        "sent": 0,
        "failed": 0,
        "skipped_not_trial": 0,
        "skipped_active": 0,
        "skipped_not_due": 0,
        "skipped_no_email": 0,
        "skipped_suppressed": 0,
        "skipped_cooldown": 0,
        "items": [],
    }
    if _hard_off():
        out["skip_reason"] = "trial_nudge_hard_off"
        return out
    if not _enabled():
        out["skip_reason"] = "trial_nudge_disabled"
        return out
    try:
        from app.marketing import clients_store
        from app.marketing.packages import trial_status
        from app.platform import email_unsub as _eu

        batch = max(1, min(int(limit or _int_env(_BATCH_ENV, _DEFAULT_BATCH)), 20))
        days_before = _int_env(_DAYS_ENV, _DEFAULT_DAYS)
        remind_h = _int_env(_REMIND_ENV, _DEFAULT_REMIND_H)
        max_per = _int_env(_MAX_ENV, _DEFAULT_MAX)

        for c in clients_store.list_clients():
            if out["sent"] >= batch:
                break
            cid = str(c.get("id") or "").strip()
            if not cid:
                continue
            st = trial_status(c)
            if not st.get("trial"):
                continue
            out["seen"] += 1
            # Billing-truth gate: paid/active client ko kabhi nudge nahi.
            if str(c.get("status") or "").strip().lower() == "active":
                out["skipped_active"] += 1
                continue
            stage = _stage_for(st, days_before)
            if not stage:
                out["skipped_not_due"] += 1
                continue
            email = str(c.get("email") or c.get("contact_email") or "").strip().lower()
            if not _one_to_one(email):
                out["skipped_no_email"] += 1
                continue
            # Opt-out suppression wins over everything (DPDP).
            try:
                if bool(_eu.is_suppressed(email)):
                    out["skipped_suppressed"] += 1
                    continue
            except Exception:
                pass
            # Idempotency/cooldown: per-stage dedupe via client-record stamps.
            prev_at = c.get("trial_nudge_at")
            prev_stage = str(c.get("trial_nudge_stage") or "")
            count = int(c.get("trial_nudge_count") or 0)
            since = _hours_since(prev_at)
            if count >= max_per or (since is not None and since < remind_h):
                out["skipped_cooldown"] += 1
                continue
            if prev_stage == stage and since is not None and since < remind_h * 2:
                out["skipped_cooldown"] += 1
                continue
            biz = str(c.get("business_name") or "Aapka business")
            days_left = int(st.get("days_left") or 0)
            msg = build_message(stage, biz, days_left)
            link = await _ensure_pay_link(biz, starter_price_inr())
            body_with_link = msg["body"] + f"\n\n1-tap UPI payment link: {link}"
            fn = send_fn or _send_nudge_email
            try:
                sent = bool(await fn(email, msg["subject"], body_with_link))
            except Exception as e:
                out["failed"] += 1
                logger.warning("[trial_nudge] send failed %s: %s", cid, e)
                continue
            if not sent:
                out["failed"] += 1
                continue
            out["sent"] += 1
            out["eligible"] += 1
            out["items"].append(
                {
                    "client_id": cid,
                    "stage": stage,
                    "email": email,
                    "wa_text_owner_1click": msg["wa_text"],
                }
            )
            try:
                clients_store.update_client(
                    cid,
                    trial_nudge_stage=stage,
                    trial_nudge_at=_now().isoformat(),
                    trial_nudge_count=count + 1,
                )
            except Exception as e:
                logger.debug("[trial_nudge] stamp skipped %s: %s", cid, e)
        if out["sent"]:
            try:
                from app.platform import team

                team.log_event(
                    "nikhil",
                    "trial_nudge",
                    f"{out['sent']} trial nudges sent "
                    f"(expired/expiring; cap={batch}, max/client={max_per})",
                )
            except Exception:
                pass
        return out
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"[trial_nudge] run failed: {e}")
        out["error"] = str(e)[:160]
        return out


__all__ = ["build_message", "run_trial_nudge", "starter_price_inr"]
