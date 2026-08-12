"""Client Health / Churn-Risk Score — retention ka early-warning system.

2026 research: agencies jo proactively at-risk clients pakadti hain 34% lambi
retention paati. Har client ko 0-100 health score: payment status, recent leads
delivered, content freshness, account age. Red band = churn-risk -> Hinglish
retention action draft + (gated) email alert Sumit ko.

Score READ-ONLY hai (no flag, live). Alert email GATED `CLIENT_HEALTH_ALERTS=1`
+ NOTIFY_EMAIL. Reuse only: clients_store, Lead/Subscription models, email_sender.
Import-safe, kabhi raise nahi.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PACKS_DIR = os.path.join("data", "client_packs")

GREEN = 70
YELLOW = 40


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _alerts_enabled() -> bool:
    return os.environ.get("CLIENT_HEALTH_ALERTS", "0").strip().lower() in ("1", "true", "yes")


def score_client(signals: dict[str, Any]) -> dict[str, Any]:
    """Pure function — signals dict se score+band+reasons. Testable.

    signals: {payment_status, leads_30d, pack_age_days (None=kabhi nahi),
              age_days, status}
    """
    score = 100
    reasons: list[str] = []
    st = str(signals.get("payment_status") or "").lower()
    if "past_due" in st:
        score -= 40
        reasons.append("payment past_due — dunning chal raha hona chahiye")
    elif any(k in st for k in ("halted", "cancelled", "canceled")):
        score -= 60
        reasons.append("subscription band/halted")
    leads = int(signals.get("leads_30d") or 0)
    if leads == 0:
        score -= 20
        reasons.append("30 din me 0 leads delivered — value dikh nahi rahi")
    pack_age = signals.get("pack_age_days")
    if pack_age is None:
        score -= 10
        reasons.append("content pack kabhi nahi bana")
    elif int(pack_age) > 14:
        score -= 10
        reasons.append(f"content pack {int(pack_age)} din purana")
    cstatus = str(signals.get("status") or "").lower()
    if cstatus and cstatus != "active":
        score -= 15
        reasons.append(f"client status={cstatus}")
    score = max(0, min(100, score))
    band = "green" if score >= GREEN else ("yellow" if score >= YELLOW else "red")
    return {"score": score, "band": band, "reasons": reasons, "action": _action(band, reasons)}


def _action(band: str, reasons: list[str]) -> str:
    """Hinglish retention next-action (draft — human/journey execute kare)."""
    if band == "green":
        return "Sab theek — monthly report bhejo aur referral maango."
    joined = "; ".join(reasons[:2])
    if band == "yellow":
        return f"Check-in call/WA karo ({joined}). Fresh content pack + is hafte ke results share karo."
    return (
        f"URGENT save-call karo ({joined}). Offer: free re-onboarding + agle mahine "
        "discount. Results report saath bhejo."
    )


async def _gather_signals() -> list[dict[str, Any]]:
    """Saare clients ke live signals (DB best-effort, sab defensive)."""
    out: list[dict[str, Any]] = []
    try:
        from app.marketing.clients_store import list_clients

        clients = list_clients() or []
    except Exception:
        clients = []
    if not clients:
        return out

    # leads last 30d per client (best-effort)
    leads_by_client: dict[str, int] = {}
    subs_by_client: dict[str, str] = {}
    try:
        from sqlalchemy import select

        from app.models.base import get_async_session
        from app.models.lead import Lead

        cutoff = _now() - timedelta(days=30)
        async with get_async_session() as session:  # type: ignore
            res = await session.execute(select(Lead).limit(5000))
            for ld in res.scalars().all():
                cid = str(getattr(ld, "client_id", "") or "")
                created = getattr(ld, "created_at", None)
                if not cid or not created:
                    continue
                c_aware = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
                if c_aware >= cutoff:
                    leads_by_client[cid] = leads_by_client.get(cid, 0) + 1
    except Exception as e:
        logger.debug(f"[client_health] leads query skipped: {e}")
    try:
        from sqlalchemy import select

        from app.models.base import get_async_session
        from app.models.payment import Subscription

        async with get_async_session() as session:  # type: ignore
            res = await session.execute(select(Subscription).limit(1000))
            for s in res.scalars().all():
                subs_by_client[str(s.client_id)] = str(getattr(s, "status", ""))
    except Exception as e:
        logger.debug(f"[client_health] subs query skipped: {e}")

    for c in clients:
        cid = str(c.get("id") or "")
        pack_age = None
        try:
            p = os.path.join(_PACKS_DIR, f"{cid}.html")
            if os.path.exists(p):
                pack_age = (
                    _now() - datetime.fromtimestamp(os.path.getmtime(p), tz=timezone.utc)
                ).days
        except Exception:
            pass
        age_days = 0
        try:
            created = datetime.fromisoformat(str(c.get("created_at")))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age_days = (_now() - created).days
        except Exception:
            pass
        out.append(
            {
                "client_id": cid,
                "business_name": c.get("business_name", ""),
                "niche": c.get("niche", ""),
                "plan": c.get("plan", ""),
                "payment_status": subs_by_client.get(cid, ""),
                "leads_30d": leads_by_client.get(cid, 0),
                "pack_age_days": pack_age,
                "age_days": age_days,
                "status": c.get("status", ""),
                "login_days_ago": None,
            }
        )

    # Fill login_days_ago — User.last_login per client (best-effort)
    if out:
        try:
            from sqlalchemy import select

            from app.models.base import get_async_session
            from app.models.user import User

            cids = [r["client_id"] for r in out if r["client_id"]]
            login_map: dict[str, int] = {}
            async with get_async_session() as session:  # type: ignore
                res = await session.execute(
                    select(User.client_id, User.last_login)
                    .where(User.client_id.in_(cids))
                    .order_by(User.last_login.desc())
                )
                seen: set[str] = set()
                for cid_, last_ in res.all():
                    if cid_ and cid_ not in seen:
                        seen.add(str(cid_))
                        if last_:
                            last_aware = (
                                last_ if last_.tzinfo else last_.replace(tzinfo=timezone.utc)
                            )
                            login_map[str(cid_)] = max(0, (_now() - last_aware).days)
            for row in out:
                row["login_days_ago"] = login_map.get(row["client_id"])
        except Exception as e:
            logger.debug(f"[client_health] login_days_ago query skipped: {e}")

    return out


async def health_report() -> list[dict[str, Any]]:
    """Saare clients ka scored health report (red pehle). Kabhi raise nahi."""
    try:
        rows = await _gather_signals()
        scored = [{**r, **score_client(r)} for r in rows]
        scored.sort(key=lambda r: r["score"])
        return scored
    except Exception as e:
        logger.warning(f"[client_health] report failed: {e}")
        return []


async def run_check() -> dict[str, Any]:
    """Scheduler hook: report banao; red clients pe (gated) email alert. Kabhi raise nahi."""
    try:
        report = await health_report()
        reds = [r for r in report if r["band"] == "red"]
        yellows = [r for r in report if r["band"] == "yellow"]
        alerted = False
        notify = os.environ.get("NOTIFY_EMAIL", "").strip()
        if reds and _alerts_enabled() and notify:
            lines = [
                f"- {r['business_name']} ({r['client_id']}) score={r['score']}: {'; '.join(r['reasons'])}\n  Action: {r['action']}"
                for r in reds[:10]
            ]
            body = (
                "Churn-risk alert — yeh clients RED band me hain:\n\n"
                + "\n".join(lines)
                + "\n\n(Auto-generated by client_health engine)"
            )
            try:
                from app.integrations.email_sender import email_sender

                alerted = bool(
                    await email_sender.send_email(
                        [notify], f"⚠️ {len(reds)} client(s) churn-risk me", body
                    )
                )
            except Exception as e:
                logger.warning(f"[client_health] alert email failed: {e}")
        try:
            from app.platform import team

            team.log_event(
                "kavya",
                "client_health_check",
                f"{len(report)} clients: {len(reds)} red, {len(yellows)} yellow",
            )
        except Exception:
            pass
        return {
            "clients": len(report),
            "red": len(reds),
            "yellow": len(yellows),
            "alerted": alerted,
        }
    except Exception as e:
        logger.warning(f"[client_health] run_check failed: {e}")
        return {"error": str(e)}
