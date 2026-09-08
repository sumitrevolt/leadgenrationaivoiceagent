"""month_planner.py — one-click 30-din content calendar → content_schedule queue.

Plan logic (deterministic, NO LLM — captions baad me content_schedule.run_due
generate karta hai EXISTING post_generator se):
  - festivals.upcoming(days) → festival days pe festival post (occasion set)
  - Friday = offer day (offer text param ya default)
  - baaki din weekly THEMES rotation: content_feedback.best_themes (proven
    themes pehle) + NICHES content_focus + default rotation

DEFAULT dry_run=True → sirf preview list. commit=True → EXISTING
content_schedule.schedule() me dup-safe enqueue (same business+date already
scheduled → skip; future dates only). NEVER raises, sab imports lazy.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DEFAULT_THEMES = [
    "Tip / Gyaan",
    "Customer Story / Testimonial",
    "Service Spotlight",
    "Behind the Scenes",
    "Engagement Question",
    "Before / After Proof",
]
_DEFAULT_OFFER = "Is hafte ki special deal — abhi inquiry karo!"


def _themes_for(niche: str) -> list[str]:
    """Proven (feedback) themes pehle, phir niche content_focus, phir defaults."""
    themes: list[str] = []

    def _add(t: str) -> None:
        t = (t or "").strip()
        if t and t.lower() not in [x.lower() for x in themes]:
            themes.append(t[:60])

    try:
        from app.marketing import content_feedback

        for t in content_feedback.best_themes(niche, n=4) or []:
            _add(t)
    except Exception:
        pass
    try:
        from app.niches import NICHES

        cfg = NICHES.get((niche or "").strip().lower(), {}) or {}
        for t in cfg.get("content_focus") or []:
            _add(str(t))
    except Exception:
        pass
    for t in _DEFAULT_THEMES:
        _add(t)
    return themes


def _festival_map(days: int) -> dict[str, dict[str, str]]:
    """date_iso → festival entry (window ke andar). Fail = {}."""
    try:
        from app.marketing import festivals

        return {f.get("date", ""): f for f in festivals.upcoming(days) if f.get("date")}
    except Exception as e:
        logger.debug(f"[month_planner] festivals skip: {e}")
        return {}


def _parse_start(start: str | None) -> date:
    try:
        if start:
            return date.fromisoformat(str(start).strip()[:10])
    except Exception:
        pass
    return date.today() + timedelta(days=1)  # default: kal se


def plan_month(
    niche: str = "general",
    client_id: str = "",
    slug: str = "",
    business_name: str = "",
    start: str | None = None,
    days: int = 30,
    offer: str = "",
    channel: str = "instagram",
    dry_run: bool = True,
    commit: bool = False,
) -> dict[str, Any]:
    """30-din plan banao; commit=True pe content_schedule me dup-safe enqueue.

    Returns {ok, plan:[{date,theme,occasion,offer,is_festival}], committed, skipped}.
    """
    try:
        niche = (niche or "general").strip().lower() or "general"
        business = (business_name or "").strip()

        # client resolve (id/slug) — business+niche default
        if (client_id or slug) and True:
            try:
                from app.marketing import clients_store

                c = clients_store.get_client(client_id) if client_id else None
                if c is None and slug:
                    c = clients_store.get_by_slug(slug)
                if c:
                    business = business or str(c.get("business_name") or "")
                    niche = str(c.get("niche") or niche) or niche
                    client_id = str(c.get("id") or client_id or "")
            except Exception:
                pass
        business = business or "Aapka Business"

        try:
            days = max(7, min(int(days), 31))
        except Exception:
            days = 30
        start_d = _parse_start(start)
        today = date.today()
        if start_d <= today:  # future dates only
            start_d = today + timedelta(days=1)

        window = (start_d - today).days + days + 1
        fest = _festival_map(window)
        themes = _themes_for(niche)
        offer_text = (offer or "").strip() or _DEFAULT_OFFER

        plan: list[dict[str, Any]] = []
        ti = 0
        for i in range(days):
            d = start_d + timedelta(days=i)
            iso = d.isoformat()
            f = fest.get(iso)
            if f:
                plan.append(
                    {
                        "date": iso,
                        "theme": "Festival",
                        "occasion": f.get("name", ""),
                        "offer": "",
                        "is_festival": True,
                        "angle": f.get("marketing_angle", ""),
                    }
                )
            elif d.weekday() == 4:  # Friday = offer day
                plan.append(
                    {
                        "date": iso,
                        "theme": "Offer / Deal",
                        "occasion": "",
                        "offer": offer_text,
                        "is_festival": False,
                    }
                )
            else:
                plan.append(
                    {
                        "date": iso,
                        "theme": themes[ti % len(themes)],
                        "occasion": "",
                        "offer": "",
                        "is_festival": False,
                    }
                )
                ti += 1

        result: dict[str, Any] = {
            "ok": True,
            "business_name": business,
            "niche": niche,
            "client_id": client_id,
            "start": start_d.isoformat(),
            "days": days,
            "plan": plan,
            "committed": 0,
            "skipped": 0,
            "dry_run": not commit,
        }

        if not commit:  # dry_run default — sirf preview
            return result

        # COMMIT — dup-safe: same business+date already scheduled → skip
        try:
            from app.marketing import content_schedule

            existing = {
                (str(it.get("business_name", "")).lower(), it.get("date", ""))
                for it in content_schedule.list_scheduled(limit=1000)
                if it.get("status") in ("scheduled", "ready")
            }
            for p in plan:
                key = (business.lower(), p["date"])
                if key in existing or p["date"] <= today.isoformat():
                    result["skipped"] += 1
                    continue
                content_schedule.schedule(
                    business_name=business,
                    niche=niche,
                    date_iso=p["date"],
                    occasion=p.get("occasion", ""),
                    offer=p.get("offer", ""),
                    channel=channel,
                    client_id=client_id,
                )
                existing.add(key)
                result["committed"] += 1
        except Exception as e:
            logger.info(f"[month_planner] commit err: {e}")
            result["commit_error"] = str(e)[:160]

        try:
            from app.platform.team import log_event

            log_event(
                "isha",
                "month_planned",
                f"{business}: {result['committed']} posts queued ({result['skipped']} dup-skip)",
            )
        except Exception:
            pass
        return result
    except Exception as e:  # NEVER raise
        logger.info(f"[month_planner] plan err: {e}")
        return {"ok": False, "error": str(e)[:160], "plan": [], "committed": 0}


__all__ = ["plan_month"]
