"""Revenue Ops Digest — Sumit ko weekly MRR/funnel/health ka ek email (Baremetrics-
style metrics, free-stack).

Kya cover karta: MRR estimate (active subs), subscription counts (active/trial/
past_due), dunning (open/recovered), lifecycle nurture funnel, hot leads, sales
deals, churn-risk (red/yellow clients). Sab EXISTING engines se read-only.

GATED `REVENUE_DIGEST=1` + NOTIFY_EMAIL (default OFF). Scheduler digest job se
`maybe_run_weekly()` — sirf Monday (IST) + week-dedupe (data/revenue_digest.jsonl).
Kabhi raise nahi.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_LOG = os.path.join("data", "revenue_digest.jsonl")
_IST = timezone(timedelta(hours=5, minutes=30))

# plan -> monthly price (packages.py truth se mirror; import-fail pe yahi fallback)
_PLAN_PRICE = {"starter": 1999, "growth": 2999, "advanced": 5999}  # packages.py truth (ADR-009)


def _enabled() -> bool:
    return os.environ.get("REVENUE_DIGEST", "0").strip().lower() in ("1", "true", "yes")


def _week_key(now: datetime | None = None) -> str:
    d = (now or datetime.now(_IST)).date()
    return f"{d.isocalendar().year}-W{d.isocalendar().week:02d}"


def _already_sent(week: str) -> bool:
    try:
        if os.path.exists(_LOG):
            with open(_LOG, encoding="utf-8") as f:
                for line in f:
                    try:
                        if json.loads(line).get("week") == week:
                            return True
                    except Exception:
                        pass
    except Exception:
        pass
    return False


def _mark_sent(week: str) -> None:
    try:
        os.makedirs(os.path.dirname(_LOG) or ".", exist_ok=True)
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"week": week, "at": datetime.now(timezone.utc).isoformat()}) + "\n")
    except Exception:
        pass


async def _collect() -> dict[str, Any]:
    """Saare engines se stats (har block defensive — fail = skip)."""
    stats: dict[str, Any] = {}
    # Subscriptions + MRR
    try:
        from sqlalchemy import select

        from app.models.base import get_async_session
        from app.models.payment import Subscription

        counts = {"active": 0, "trial": 0, "past_due": 0, "other": 0}
        mrr = 0.0
        async with get_async_session() as session:  # type: ignore
            res = await session.execute(select(Subscription).limit(1000))
            for s in res.scalars().all():
                st = str(getattr(s, "status", "")).lower()
                if "active" in st:
                    counts["active"] += 1
                    price = float(getattr(s, "base_price", 0) or 0)
                    if price <= 0:
                        price = float(_PLAN_PRICE.get(str(getattr(s, "plan_id", "")).lower(), 0))
                    if price <= 0 and str(getattr(s, "plan_id", "")).startswith("voice_"):
                        try:
                            from app.marketing.voice_packages import voice_plan_price

                            price = float(voice_plan_price(str(getattr(s, "plan_id", ""))) or 0)
                        except Exception:
                            pass
                    mrr += price
                elif "trial" in st:
                    counts["trial"] += 1
                elif "past_due" in st:
                    counts["past_due"] += 1
                else:
                    counts["other"] += 1
        stats["subscriptions"] = counts
        stats["mrr"] = round(mrr)
    except Exception as e:
        logger.debug(f"[digest] subs skipped: {e}")
    # Dunning
    try:
        from app.billing import dunning

        stats["dunning"] = {k: v for k, v in dunning.stats().items() if k != "open_cases"}
    except Exception:
        pass
    # Lifecycle nurture
    try:
        from app.marketing import lifecycle_nurture

        stats["lifecycle"] = lifecycle_nurture.stats()
    except Exception:
        pass
    # Hot leads
    try:
        from app.platform import lead_scoring

        hot = await lead_scoring.top_hot_leads(50)
        stats["hot_leads"] = len(hot or [])
    except Exception:
        pass
    # Sales deals
    try:
        from app.marketing import sales_pipeline

        stats["deals"] = sales_pipeline.stats()
    except Exception:
        pass
    # Client health
    try:
        from app.platform import client_health

        rep = await client_health.health_report()
        stats["health"] = {
            "clients": len(rep),
            "red": sum(1 for r in rep if r.get("band") == "red"),
            "yellow": sum(1 for r in rep if r.get("band") == "yellow"),
        }
    except Exception:
        pass
    return stats


def compose(stats: dict[str, Any], week: str) -> tuple[str, str]:
    """Stats -> (subject, Hinglish body). Pure function — testable."""
    mrr = stats.get("mrr", 0)
    subs = stats.get("subscriptions", {}) or {}
    dn = stats.get("dunning", {}) or {}
    lc = stats.get("lifecycle", {}) or {}
    hl = stats.get("health", {}) or {}
    deals = stats.get("deals", {}) or {}
    subject = f"📊 Revenue Digest {week} — MRR ₹{mrr}, {subs.get('active', 0)} active clients"
    lines = [
        f"Week {week} ka revenue snapshot:",
        "",
        f"💰 MRR (estimate): ₹{mrr}",
        f"📦 Subscriptions: {subs.get('active', 0)} active · {subs.get('trial', 0)} trial · {subs.get('past_due', 0)} past_due",
        f"🛟 Dunning: {dn.get('open', 0)} open · {dn.get('recovered', 0)} recovered · {dn.get('lapsed', 0)} lapsed",
        f"🌱 Nurture funnel: {lc.get('active', 0)} active · {lc.get('converted', 0)} converted · {lc.get('finished', 0)} finished (no-pay)",
        f"🔥 Hot leads: {stats.get('hot_leads', 0)}",
        f"🤝 Deals: {json.dumps(deals, ensure_ascii=False)[:200]}",
        f"❤️ Client health: {hl.get('red', 0)} red · {hl.get('yellow', 0)} yellow (of {hl.get('clients', 0)})",
        "",
        "Action: red clients pe save-call, past_due pe dunning follow, hot leads pe outreach.",
        "(Auto-generated by revenue_digest)",
    ]
    return subject, "\n".join(lines)


async def run(force: bool = False) -> dict[str, Any]:
    """Digest banao + bhejo. force=True = gate/dedupe skip (manual API). Kabhi raise nahi."""
    try:
        week = _week_key()
        if not force:
            if not _enabled():
                return {"enabled": False}
            if _already_sent(week):
                return {"enabled": True, "skipped": "already sent this week"}
        stats = await _collect()
        subject, body = compose(stats, week)
        notify = os.environ.get("NOTIFY_EMAIL", "").strip()
        sent = False
        if notify:
            try:
                from app.integrations.email_sender import email_sender

                sent = bool(await email_sender.send_email([notify], subject, body))
            except Exception as e:
                logger.warning(f"[digest] send failed: {e}")
        if sent and not force:
            _mark_sent(week)
        try:
            from app.platform import team

            # "boss" is not a STAFF key ("manager" is) -- was silently invisible in
            # team_status(). Nikhil (Revenue Ops) is the correct owner. Fixed 2026-07-01.
            team.log_event(
                "nikhil", "revenue_digest", f"{week}: MRR ₹{stats.get('mrr', 0)}, sent={sent}"
            )
        except Exception:
            pass
        return {"enabled": True, "week": week, "sent": sent, "stats": stats, "subject": subject}
    except Exception as e:
        logger.warning(f"[digest] run failed: {e}")
        return {"error": str(e)}


async def maybe_run_weekly() -> dict[str, Any]:
    """Scheduler hook: sirf Monday IST + gated + week-dedupe. Kabhi raise nahi."""
    try:
        if not _enabled():
            return {"enabled": False}
        if datetime.now(_IST).weekday() != 0:  # Monday=0
            return {"enabled": True, "skipped": "not monday"}
        return await run(force=False)
    except Exception as e:
        return {"error": str(e)}
