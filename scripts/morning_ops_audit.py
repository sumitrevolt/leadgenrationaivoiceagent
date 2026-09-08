#!/usr/bin/env python3
"""One-shot morning ops audit — emails, calls, agent_events, scheduler heartbeats."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

IST = timezone(timedelta(hours=5, minutes=30))


def _since_hours(h: int = 24):
    return datetime.now(timezone.utc) - timedelta(hours=h)


def main() -> int:
    out: dict = {"generated_utc": datetime.now(timezone.utc).isoformat()}
    since = _since_hours(24)

    # --- flags ---
    flags = [
        "AUTO_EMAIL_OUTREACH",
        "REPLY_AGENT",
        "NICHE_ROTATION",
        "AUTO_ONBOARD",
        "OPS_WATCHDOG",
        "RUN_IN_PROCESS_SCHEDULER",
        "TEAM_AUTOMATION",
        "JOURNEY_ENGINE",
        "CADENCE_ENGINE",
        "SALES_ENGINE",
    ]
    out["flags"] = {f: os.getenv(f, "") for f in flags}

    # --- emails ---
    try:
        from app.platform.auto_outreach import outreach_stats

        out["outreach_stats"] = outreach_stats()
    except Exception as e:
        out["outreach_stats_error"] = str(e)

    # --- calls ---
    try:
        from sqlalchemy import func, select

        from app.models import Call
        from app.models.base import get_async_session

        async def _calls():
            async with get_async_session() as s:
                total = (await s.execute(select(func.count()).select_from(Call))).scalar() or 0
                recent = (
                    await s.execute(
                        select(func.count()).select_from(Call).where(Call.created_at >= since)
                    )
                ).scalar() or 0
                return {"total": int(total), "last_24h": int(recent)}

        import asyncio

        out["calls"] = asyncio.run(_calls())
    except Exception as e:
        out["calls_error"] = str(e)

    # --- agent_events last 24h ---
    try:
        from sqlalchemy import select

        from app.models import AgentEvent
        from app.models.base import get_async_session

        async def _events():
            async with get_async_session() as s:
                rows = (
                    (
                        await s.execute(
                            select(AgentEvent)
                            .where(AgentEvent.created_at >= since)
                            .order_by(AgentEvent.created_at.desc())
                            .limit(200)
                        )
                    )
                    .scalars()
                    .all()
                )
                by_agent: dict[str, int] = {}
                by_kind: dict[str, int] = {}
                samples = []
                for r in rows:
                    by_agent[r.agent_name or "?"] = by_agent.get(r.agent_name or "?", 0) + 1
                    by_kind[r.event_type or "?"] = by_kind.get(r.event_type or "?", 0) + 1
                    if len(samples) < 15:
                        samples.append(
                            {
                                "at": r.created_at.isoformat() if r.created_at else None,
                                "agent": r.agent_name,
                                "type": r.event_type,
                                "detail": (r.detail or "")[:120],
                            }
                        )
                return {
                    "count_24h": len(rows),
                    "by_agent": dict(sorted(by_agent.items(), key=lambda x: -x[1])[:12]),
                    "by_kind": dict(sorted(by_kind.items(), key=lambda x: -x[1])[:12]),
                    "recent": samples,
                }

        import asyncio

        out["agent_events"] = asyncio.run(_events())
    except Exception as e:
        out["agent_events_error"] = str(e)

    # --- job heartbeats ---
    hb_path = os.path.join("data", "job_heartbeats.json")
    if os.path.isfile(hb_path):
        try:
            with open(hb_path, encoding="utf-8") as f:
                hb = json.load(f)
            out["heartbeats"] = hb
        except Exception as e:
            out["heartbeats_error"] = str(e)

    # --- prospects / leads counts ---
    try:
        from sqlalchemy import func, select

        from app.models import Lead
        from app.models.base import get_async_session

        async def _leads():
            async with get_async_session() as s:
                total = (await s.execute(select(func.count()).select_from(Lead))).scalar() or 0
                hot = (
                    await s.execute(
                        select(func.count()).select_from(Lead).where(Lead.is_hot_lead.is_(True))
                    )
                ).scalar() or 0
                return {"total": int(total), "hot": int(hot)}

        import asyncio

        out["leads"] = asyncio.run(_leads())
    except Exception as e:
        out["leads_error"] = str(e)

    # --- reply drafts ---
    rd = os.path.join("data", "reply_drafts.jsonl")
    if os.path.isfile(rd):
        n = 0
        try:
            with open(rd, encoding="utf-8") as f:
                for _ in f:
                    n += 1
            out["reply_drafts_total"] = n
        except Exception:
            pass

    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
