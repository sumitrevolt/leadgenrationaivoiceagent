"""Usage-threshold upsell alerts — 80%/100% voice-minute triggers (expansion revenue).

Research (June 2026): usage-threshold-triggered upsell prompts 20-40% convert vs
5-15% cold email. Humara metering (`app/billing/usage.py`) cap enforce karta tha
par client ko KABHI batata nahi tha — 100% pe calls chupchaap block ho jaati
(bad surprise = churn risk) aur 80% pe upgrade nudge ka mauka miss hota tha.

Design:
  - run_check(): saare metered-plan (Advanced) clients -> pct used -> 80% / 100%
    threshold cross pe Hinglish email (client) + NOTIFY_EMAIL copy.
  - Dedupe: per client+threshold+period (data/usage_alerts.jsonl) — period key =
    YYYY-MM (renewal watermark usage.py me already handle hota; month-key kaafi).
  - GATED `USAGE_ALERTS=1` (default OFF => sirf record, koi email nahi).
  - Wired: team_scheduler digest job (daily). Kabhi raise nahi karta.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STORE = os.path.join("data", "usage_alerts.jsonl")

THRESHOLDS = (80, 100)  # pct
PRICING_URL = "https://leadsgenai.in/pricing"
SUPPORT_EMAIL = "admin@leadsgenai.in"


def _enabled() -> bool:
    return os.environ.get("USAGE_ALERTS", "0").strip().lower() in ("1", "true", "yes")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _period_key() -> str:
    n = _now()
    return f"{n.year:04d}-{n.month:02d}"


def _read() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(_STORE):
            with open(_STORE, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows


def _append(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_STORE) or ".", exist_ok=True)
        with open(_STORE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _already_alerted(client_id: str, threshold: int, period: str) -> bool:
    enabled = _enabled()
    return any(
        r.get("client_id") == client_id
        and int(r.get("threshold") or 0) == threshold
        and r.get("period") == period
        and (
            bool(r.get("sent")) or not enabled
        )  # only a DELIVERED alert dedups when enabled — otherwise presence in log is enough to avoid log spam
        for r in _read()
    )


def build_message(threshold: int, business_name: str, used: int, cap: int) -> dict[str, str]:
    """Hinglish alert/upsell message. Pure function — testable."""
    biz = (business_name or "Aapka business").strip()
    if threshold >= 100:
        return {
            "subject": f"⛔ {biz} — AI calling minutes khatam (is mahine ke)",
            "body": (
                f"Namaste!\n\n{biz} ke is period ke AI voice minutes poore use ho gaye "
                f"({used}/{cap} min) — nayi outbound AI calls ab agle renewal tak pause hain.\n\n"
                f"Turant chalu rakhna hai? Plan renew/upgrade karo: {PRICING_URL}\n"
                f"Ya humein likho: {SUPPORT_EMAIL} — top-up arrange kar denge.\n\n— Team LeadsGenAI"
            ),
        }
    return {
        "subject": f"📞 {biz} — AI calling minutes {threshold}% use ho gaye",
        "body": (
            f"Namaste!\n\nGood news pehle: {biz} ka AI agent khoob kaam kar raha hai — "
            f"{used}/{cap} min ({threshold}%+) is period me use ho chuke.\n\n"
            f"Minutes khatam hone par calls pause ho jaati hain. Bina ruke chalana hai to "
            f"abhi upgrade/renew dekh lo: {PRICING_URL}\n\n— Team LeadsGenAI"
        ),
    }


async def _topup_link(client_id: str, business_name: str) -> str:
    """Razorpay payment-links removed 2026-06-18 — always "".

    Usage-alert email body already carries PRICING_URL (manual UPI path).
    Kept as a named helper so callers stay readable; never raises.
    """
    _ = (client_id, business_name)
    return ""


async def _send(to_email: str, subject: str, body: str) -> bool:
    try:
        if not to_email:
            return False
        from app.integrations.email_sender import email_sender

        return bool(await email_sender.send_email([to_email], subject, body))
    except Exception:
        return False


def _client_email(client_id: str, rec: dict[str, Any]) -> str:
    email = str(rec.get("email") or "").strip().lower()
    if email:
        return email
    try:
        for row in _readf(os.path.join("data", "customer_auth.jsonl")):
            if str(row.get("client_id") or "") == client_id and row.get("email"):
                return str(row["email"]).strip().lower()
    except Exception:
        pass
    return ""


def _readf(path: str) -> list[dict[str, Any]]:
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


async def run_check() -> dict[str, Any]:
    """Daily sweep — metered clients ke thresholds check karo. Never raises."""
    out: dict[str, Any] = {"checked": 0, "alerts": 0, "sent": 0, "enabled": _enabled()}
    try:
        from app.billing import usage
        from app.marketing.clients_store import list_clients

        period = _period_key()
        for cl in list_clients() or []:
            try:
                cid = str(cl.get("id") or "")
                plan = str(cl.get("plan") or "").strip().lower()
                # Include purchased top-ups so the threshold denominator matches the real
                # enforcement gate (usage.has_minutes() = plan + topups). Else the 100%
                # "calls paused" email fires while top-up minutes (and service) remain.
                cap = usage.plan_minutes(plan) + usage.topup_minutes(cid)
                if not cid or cap <= 0:
                    continue
                out["checked"] += 1
                used = usage.minutes_used_this_period(cid)
                pct = used * 100 // cap
                for th in sorted(THRESHOLDS, reverse=True):  # highest crossed threshold only
                    if pct < th or _already_alerted(cid, th, period):
                        continue
                    msg = build_message(th, str(cl.get("business_name") or ""), used, cap)
                    rec = {
                        "at": _now().isoformat(),
                        "client_id": cid,
                        "period": period,
                        "threshold": th,
                        "used": used,
                        "cap": cap,
                        "sent": False,
                    }
                    out["alerts"] += 1
                    if _enabled():
                        email = _client_email(cid, cl)
                        body = msg["body"]
                        if th >= 100:  # out-of-minutes => 1-tap top-up link (best-effort)
                            tl = await _topup_link(cid, str(cl.get("business_name") or ""))
                            if tl:
                                body += f"\n\nTurant 100 min top-up (1-tap, UPI/card): {tl}"
                        ok = await _send(email, msg["subject"], body)
                        rec["sent"] = bool(ok)
                        notify = os.environ.get("NOTIFY_EMAIL", "").strip()
                        if notify:
                            await _send(
                                notify,
                                f"[usage] {cl.get('business_name')} @ {th}% ({used}/{cap} min)",
                                f"Upsell window: {msg['subject']}\nClient email: {email or '—'} (sent={ok})",
                            )
                        if ok:
                            out["sent"] += 1
                    _append(rec)
                    try:
                        from app.platform import team

                        team.log_event(
                            "nikhil",
                            "usage_alert",
                            f"{cl.get('business_name')} {th}% minutes ({used}/{cap})",
                        )
                    except Exception:
                        pass
                    break  # ek run me ek (highest) threshold per client
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"[usage-alerts] run_check failed: {e}")
    return out


def recent(limit: int = 50) -> list[dict[str, Any]]:
    return _read()[-max(1, min(int(limit or 50), 500)) :][::-1]


__all__ = ["run_check", "recent", "build_message", "THRESHOLDS"]
