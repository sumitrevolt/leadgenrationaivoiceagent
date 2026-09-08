"""Dunning / Revenue-Recovery Engine — involuntary churn ka free-stack ilaaj.

2026 research: SaaS ~9% MRR failed payments me khota hai; automated dunning
40-70% recover karta (Baremetrics/Churn Buster pattern). Razorpay/Stripe webhook
PAST_DUE sirf mark karte the — yeh engine us par RECOVERY sequence chalata:

  payment_failed -> day-0 Hinglish recovery email + WA 1-click link (human send)
                 -> day-3 gentle reminder -> day-7 urgency -> day-14 win-back + lapse
  pre-dunning    -> renewal se RENEWAL_REMINDER_DAYS pehle reminder (period-dedupe)
  recovered      -> payment success webhook pe case auto-close (MRR saved track)

GATED `DUNNING_ENGINE=1` (default OFF = run_due no-op, zero behaviour change).
`on_payment_failed` hamesha case+draft RECORD karta (additive, send nahi) — auto
email-send sirf flag ON pe. Store: data/dunning_cases.jsonl + dunning_runs.jsonl.
Reuse only: email_sender, clients_store, customer_auth store. Kabhi raise nahi.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_CASES = os.path.join("data", "dunning_cases.jsonl")
_RUNS = os.path.join("data", "dunning_runs.jsonl")

PRICING_URL = "https://leadsgenai.in/pricing"
SUPPORT_EMAIL = "admin@leadsgenai.in"
RENEWAL_REMINDER_DAYS = 5
# Recovery touch schedule (din since failure) — research-backed 0/3/7 + day-14 win-back.
_TOUCHES = [
    {"day": 0, "key": "failed_now"},
    {"day": 3, "key": "reminder"},
    {"day": 7, "key": "urgent"},
    {"day": 14, "key": "winback"},
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _enabled() -> bool:
    return os.environ.get("DUNNING_ENGINE", "0").strip().lower() in ("1", "true", "yes")


def _read(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows


def _write_all(path: str, rows: list[dict[str, Any]]) -> None:
    # Lock + atomic — web (webhooks) + celery (run_due) dono likhte hain.
    try:
        from app.utils.file_lock import locked_rewrite

        content = "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows)
        if not locked_rewrite(path, content):
            logger.warning(f"[dunning] locked write failed: {path}")
    except Exception as e:
        logger.warning(f"[dunning] write {path} failed: {e}")


def _append(path: str, rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _client_email(client_id: str) -> str:
    """customer_auth store se client ka login email (fallback client rec)."""
    cid = str(client_id or "")
    try:
        for row in _read(os.path.join("data", "customer_auth.jsonl")):
            if str(row.get("client_id") or "") == cid and row.get("email"):
                return str(row["email"]).strip().lower()
    except Exception:
        pass
    try:
        from app.marketing.clients_store import get_client

        rec = get_client(cid) or {}
        return str(rec.get("email") or "").strip().lower()
    except Exception:
        return ""


def _client_info(client_id: str) -> dict[str, Any]:
    try:
        from app.marketing.clients_store import get_client

        return get_client(str(client_id)) or {}
    except Exception:
        return {}


def build_message(
    touch_key: str, business_name: str, amount: Any = None, plan: str = ""
) -> dict[str, str]:
    """Hinglish recovery message (subject + body + WA text). Pure function — testable."""
    biz = (business_name or "Aapka business").strip()
    amt = f"₹{amount}" if amount else "payment"
    if touch_key == "failed_now":
        subject = f"{biz} — payment fail ho gaya, service chalu rakhne ke liye 1-click renew"
        body = (
            f"Namaste {biz} team,\n\n"
            f"Aapka {amt} process nahi ho paya (card/UPI issue ho sakta hai). Aapki AI "
            f"marketing service abhi chal rahi hai — bas payment retry kar dijiye:\n\n"
            f"  Renew/Pay: {PRICING_URL}\n\n"
            f"Koi dikkat ho to is email ka reply karo ya {SUPPORT_EMAIL} pe likho — turant sort karenge.\n"
        )
    elif touch_key == "reminder":
        subject = f"{biz} — reminder: payment pending hai (service pause na ho)"
        body = (
            f"Namaste,\n\n{biz} ka {amt} abhi bhi pending hai. Aapke daily posts, "
            f"lead-capture aur reports na rukein isliye jaldi renew kar lo:\n\n"
            f"  {PRICING_URL}\n\nUPI/card dono chalta hai. Help chahiye to reply karo.\n"
        )
    elif touch_key == "urgent":
        subject = f"{biz} — aakhri reminder: 7 din ho gaye, service pause hone wali hai"
        body = (
            f"Namaste,\n\n{amt} 7 din se pending hai — system jald aapki marketing "
            f"automation pause kar dega. 2 minute me renew karo:\n\n  {PRICING_URL}\n\n"
            f"Agar plan change karna hai ya koi issue hai, reply karo — hum adjust kar denge.\n"
        )
    else:  # winback
        subject = f"{biz} — wapas aao, aapka data + setup safe hai (special offer)"
        body = (
            f"Namaste,\n\nAapki service lapse ho gayi, lekin aapka pura setup (posts, "
            f"leads, mini-site) safe hai. Wapas aao to wahi se continue hoga — is mahine "
            f"renew karne par hum onboarding dobara FREE karenge:\n\n  {PRICING_URL}\n\n"
            f"Sawal ho to seedha reply karo.\n"
        )
    wa_text = (
        f"Namaste! {biz} ki LeadsGenAI service ka payment pending hai. 1-click renew: {PRICING_URL}"
    )
    return {"subject": subject, "body": body, "wa_text": wa_text}


async def _send_email(to_email: str, subject: str, body: str) -> bool:
    if not to_email:
        return False
    try:
        from app.integrations.email_sender import email_sender

        return bool(await email_sender.send_email([to_email], subject, body))
    except Exception as e:
        logger.warning(f"[dunning] email send failed: {e}")
        return False


async def _ensure_pay_link(case: dict[str, Any]) -> str:
    """UPI intent deep-link for recovery email (Razorpay removed 2026-06-18).

    UPI intent URL = no-login, opens any UPI app directly. Amount missing → pricing
    page fallback. Never raises.
    """
    try:
        if case.get("pay_link"):
            return str(case["pay_link"])
        amount = case.get("amount")
        # Build UPI intent link if VPA configured
        try:
            from app.platform.upi_config import get_vpa

            vpa = str(get_vpa() or "").strip()
            if vpa and amount:
                biz = str(case.get("business_name") or "renewal").replace(" ", "+")[:30]
                link = f"upi://pay?pa={vpa}&am={amount}&tn=LeadsGenAI+{biz}&cu=INR"
                case["pay_link"] = link
                return link
        except Exception:
            pass
        # Fallback: pricing page
        return PRICING_URL
    except Exception as e:
        logger.debug(f"[dunning] pay link skipped: {e}")
        return PRICING_URL


def _with_link(body: str, link: str) -> str:
    if not link:
        return body
    return body + f"\n\n1-tap payment link (UPI/card/netbanking): {link}"


async def on_payment_failed(
    client_id: str,
    amount: Any = None,
    gateway: str = "",
    reason: str = "",
    subscription_id: str | None = None,
) -> dict[str, Any]:
    """Webhook hook: failed payment -> open dunning case + day-0 draft (+auto-email
    sirf DUNNING_ENGINE=1 pe). Dedupe: ek client pe ek hi OPEN case. Kabhi raise nahi."""
    try:
        cid = str(client_id or "").strip()
        if not cid:
            return {"ok": False, "error": "client_id required"}
        rows = _read(_CASES)
        for r in rows:
            if r.get("client_id") == cid and r.get("status") == "open":
                return {"ok": True, "case": r, "dedupe": True}

        info = _client_info(cid)
        biz = str(info.get("business_name") or "Aapka business")
        email = _client_email(cid)
        case = {
            "id": uuid.uuid4().hex[:12],
            "client_id": cid,
            "business_name": biz,
            "email": email,
            "phone": str(info.get("phone") or ""),
            "amount": amount,
            "gateway": gateway,
            "reason": (reason or "")[:200],
            "subscription_id": subscription_id,
            "status": "open",
            "touches_done": [],
            "created_at": _now().isoformat(),
        }
        rows.append(case)
        _write_all(_CASES, rows)

        msg = build_message("failed_now", biz, amount)
        link = await _ensure_pay_link(case)  # 1-tap recovery link (creds unset = "")
        sent = False
        if _enabled() and email:
            sent = await _send_email(email, msg["subject"], _with_link(msg["body"], link))
        _append(
            _RUNS,
            {
                "case_id": case["id"],
                "client_id": cid,
                "touch": "failed_now",
                "email": email,
                "auto_sent": sent,
                **msg,
                "at": _now().isoformat(),
            },
        )
        # touch record karo (day-0 done)
        case["touches_done"] = ["failed_now"]
        _write_all(_CASES, rows)
        try:
            from app.platform import team

            team.log_event(
                "kavya",
                "dunning_case_opened",
                f"{biz}: payment failed ({gateway})",
                meta={"client_id": cid},
            )
        except Exception:
            pass
        return {"ok": True, "case": case, "auto_sent": sent}
    except Exception as e:
        logger.warning(f"[dunning] on_payment_failed failed: {e}")
        return {"ok": False, "error": str(e)}


def mark_recovered(client_id: str) -> bool:
    """Payment success webhook hook: open case close karo (recovered). Kabhi raise nahi."""
    try:
        cid = str(client_id or "")
        rows = _read(_CASES)
        changed = False
        for r in rows:
            if r.get("client_id") == cid and r.get("status") == "open":
                r["status"] = "recovered"
                r["recovered_at"] = _now().isoformat()
                changed = True
        if changed:
            _write_all(_CASES, rows)
            try:
                from app.platform import team

                team.log_event("kavya", "dunning_recovered", f"client {cid} payment recovered")
            except Exception:
                pass
        return changed
    except Exception:
        return False


async def _renewal_reminders() -> int:
    """Pre-dunning: active subscriptions jinka period RENEWAL_REMINDER_DAYS me khatam
    ho raha — ek reminder per period (dedupe by period_end date). Best-effort."""
    sent = 0
    try:
        from sqlalchemy import select

        from app.models.base import get_async_session
        from app.models.payment import Subscription

        cutoff = _now() + timedelta(days=RENEWAL_REMINDER_DAYS)
        already = {
            (r.get("client_id"), r.get("period_end"))
            for r in _read(_RUNS)
            if r.get("touch") == "renewal_reminder"
        }
        async with get_async_session() as session:  # type: ignore
            res = await session.execute(select(Subscription).limit(500))
            subs = list(res.scalars().all())
        for s in subs:
            try:
                st = str(getattr(s, "status", "")).lower()
                pe = getattr(s, "current_period_end", None)
                if "active" not in st or not pe:
                    continue
                pe_aware = pe if pe.tzinfo else pe.replace(tzinfo=timezone.utc)
                if not (_now() < pe_aware <= cutoff):
                    continue
                cid = str(s.client_id)
                key = (cid, pe_aware.date().isoformat())
                if key in already:
                    continue
                info = _client_info(cid)
                biz = str(info.get("business_name") or "Aapka business")
                email = _client_email(cid)
                subject = f"{biz} — renewal {pe_aware.date().isoformat()} ko due hai (service na rukne dein)"
                body = (
                    f"Namaste,\n\n{biz} ka plan {pe_aware.date().isoformat()} ko renew hoga. "
                    f"UPI mandate/card active rakho taaki marketing automation na ruke. "
                    f"Plan dekhna/badalna ho: {PRICING_URL}\n\nSawal ho to reply karo.\n"
                )
                ok = await _send_email(email, subject, body) if email else False
                _append(
                    _RUNS,
                    {
                        "client_id": cid,
                        "touch": "renewal_reminder",
                        "period_end": pe_aware.date().isoformat(),
                        "email": email,
                        "auto_sent": ok,
                        "subject": subject,
                        "body": body,
                        "at": _now().isoformat(),
                    },
                )
                sent += 1
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"[dunning] renewal reminders skipped: {e}")
    return sent


async def run_due() -> dict[str, Any]:
    """Daily sweep (scheduler se). GATED DUNNING_ENGINE=1 — off = no-op."""
    if not _enabled():
        return {"enabled": False}
    touched = 0
    try:
        rows = _read(_CASES)
        changed = False
        for case in rows:
            if case.get("status") != "open":
                continue
            try:
                created = datetime.fromisoformat(str(case.get("created_at")))
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                days = (_now() - created).days
                done = set(case.get("touches_done") or [])
                for t in _TOUCHES:
                    if t["key"] in done or days < t["day"]:
                        continue
                    msg = build_message(t["key"], case.get("business_name", ""), case.get("amount"))
                    link = await _ensure_pay_link(case)  # cached after first touch
                    if link and case.get("pay_link") == link:
                        changed = True  # persist cached link
                    ok = await _send_email(
                        case.get("email", ""), msg["subject"], _with_link(msg["body"], link)
                    )
                    _append(
                        _RUNS,
                        {
                            "case_id": case.get("id"),
                            "client_id": case.get("client_id"),
                            "touch": t["key"],
                            "email": case.get("email", ""),
                            "auto_sent": ok,
                            **msg,
                            "at": _now().isoformat(),
                        },
                    )
                    done.add(t["key"])
                    case["touches_done"] = sorted(done)
                    touched += 1
                    changed = True
                if "winback" in done and days >= 14:
                    case["status"] = "lapsed"
                    changed = True
            except Exception:
                continue
        if changed:
            _write_all(_CASES, rows)
        renewals = await _renewal_reminders()
        if touched or renewals:
            try:
                from app.platform import team

                team.log_event(
                    "nikhil",
                    "dunning_sweep",
                    f"{touched} recovery touches, {renewals} renewal reminders",
                )
            except Exception:
                pass
        return {"enabled": True, "touches": touched, "renewal_reminders": renewals}
    except Exception as e:
        logger.warning(f"[dunning] run_due failed: {e}")
        return {"enabled": True, "error": str(e)}


def stats() -> dict[str, Any]:
    """Dunning overview (digest/dashboard ke liye). Kabhi raise nahi."""
    try:
        rows = _read(_CASES)
        open_c = [r for r in rows if r.get("status") == "open"]
        rec_c = [r for r in rows if r.get("status") == "recovered"]
        return {
            "open": len(open_c),
            "recovered": len(rec_c),
            "lapsed": sum(1 for r in rows if r.get("status") == "lapsed"),
            "open_cases": open_c[:20],
        }
    except Exception:
        return {"open": 0, "recovered": 0, "lapsed": 0, "open_cases": []}


# ---------------------------------------------------------------------------
# SAFE RENEWAL REMINDER -- works WITHOUT DUNNING_ENGINE gate
# ---------------------------------------------------------------------------
# Subscription expiry se pehle reminder bhejta hai. Manual UPI safe.
# NEVER raises. Gated by RENEWAL_REMINDER_ENABLED (default ON).
# ---------------------------------------------------------------------------


def renewal_reminder_enabled() -> bool:
    """ON by default -- safe, no payment action, just reminder email."""
    return os.environ.get("RENEWAL_REMINDER_ENABLED", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


async def send_renewal_reminders() -> dict[str, Any]:
    """Active subscriptions ko renewal reminder bhejo.

    Independent of DUNNING_ENGINE only when dunning is OFF. When
    ``DUNNING_ENGINE=1``, ``run_due()`` already sends period-deduped
    ``_renewal_reminders`` — a second sender would double-email Jiya.
    Safe: sirf email reminder, koi payment retry. Manual UPI path intact.
    NEVER raises.
    """
    result: dict[str, Any] = {"sent": 0, "skipped": 0, "error": None}
    if _enabled():
        return {"skipped": "covered_by_dunning_run_due"}
    if not renewal_reminder_enabled():
        return {"skipped": "RENEWAL_REMINDER_ENABLED=0"}
    try:
        from app.billing import usage
        from app.integrations.email_sender import EmailSender
        from app.marketing import clients_store

        clients = clients_store.list_clients() or []
        sender = EmailSender()

        NL = chr(10)  # newline character

        for c in clients:
            try:
                cid = str(c.get("id") or "").strip()
                if not cid:
                    continue
                sub = usage.get_subscription(cid)
                if not sub or sub.get("status") not in ("active", "trialing"):
                    continue
                renewal_str = str(sub.get("current_period_end") or "")
                if not renewal_str:
                    continue
                try:
                    renewal_dt = datetime.fromisoformat(renewal_str.replace("Z", "+00:00"))
                    if renewal_dt.tzinfo is None:
                        renewal_dt = renewal_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    continue
                days_left = (renewal_dt - _now()).days
                if days_left > RENEWAL_REMINDER_DAYS or days_left < 0:
                    continue
                email = str(c.get("email") or "").strip()
                biz = str(c.get("business_name") or c.get("name") or "Customer").strip()
                if not email:
                    continue
                subject = biz + " ji -- subscription " + str(days_left) + " din me renew"
                body_text = "Namaste " + biz + " ji," + NL + NL
                body_text += (
                    "Aapka LeadGen AI subscription "
                    + str(days_left)
                    + " din me expire ho raha hai. "
                )
                body_text += (
                    "Service continue rakhne ke liye UPI se payment kar sakte hain." + NL + NL
                )
                body_text += (
                    "Plan: "
                    + str(sub.get("plan", "starter"))
                    + " -- Rs "
                    + str(sub.get("amount", 1999))
                    + "/month"
                    + NL
                )
                body_text += "Payment: leadsgenai.in/pricing" + NL + NL
                body_text += "Koi sawaal ho to reply karein -- hum madad karenge." + NL + NL
                body_text += "-- Sumit, LeadGen AI"
                try:
                    await sender.send_email([email], subject, body_text, body_text)
                    result["sent"] += 1
                except Exception:
                    result["skipped"] += 1
            except Exception:
                result["skipped"] += 1
                continue

        try:
            from app.platform.team import log_event

            log_event(
                "nikhil",
                "renewal_reminders",
                str(result["sent"]) + " renewal reminders sent",
                status="ok" if result["sent"] > 0 else "info",
                meta=result,
            )
        except Exception:
            pass

        logger.info("[dunning] renewal reminders done: " + str(result))
        return result
    except Exception as e:
        logger.warning("[dunning] send_renewal_reminders failed: " + str(e))
        result["error"] = str(e)[:200]
        return result
