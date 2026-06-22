"""Campaign variants service — champion/challenger tracking + promotion gate."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


async def register_variant(
    *,
    script_id: str,
    variant_key: str,
    content: str,
    niche: str = "",
    channel: str = "email",
    client_id: str = "",
) -> dict[str, Any]:
    try:
        from app.models.base import get_async_session
        from app.models.campaign_variant import CampaignVariant

        vid = str(uuid.uuid4())
        async with get_async_session() as session:
            session.add(
                CampaignVariant(
                    id=vid,
                    client_id=client_id,
                    script_id=script_id,
                    variant_key=variant_key,
                    niche=niche,
                    channel=channel,
                    content=content[:8000],
                    status="challenger" if variant_key != "champion" else "champion",
                )
            )
            await session.commit()
        return {"ok": True, "id": vid, "variant_key": variant_key}
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}


async def record_event(
    variant_id: str,
    *,
    impression: bool = False,
    reply: bool = False,
    meeting: bool = False,
) -> dict[str, Any]:
    try:
        from sqlalchemy import select

        from app.models.base import get_async_session
        from app.models.campaign_variant import CampaignVariant

        async with get_async_session() as session:
            row = (
                await session.execute(
                    select(CampaignVariant).where(CampaignVariant.id == variant_id)
                )
            ).scalar_one_or_none()
            if not row:
                return {"ok": False, "error": "variant not found"}
            if impression:
                row.impressions = int(row.impressions or 0) + 1
            if reply:
                row.replies = int(row.replies or 0) + 1
            if meeting:
                row.meetings = int(row.meetings or 0) + 1
            imp = max(1, int(row.impressions or 0))
            row.meeting_rate = float(row.meetings or 0) / imp
            await session.commit()
            return {
                "ok": True,
                "impressions": row.impressions,
                "meetings": row.meetings,
                "meeting_rate": row.meeting_rate,
            }
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}


async def try_promote_challenger(script_id: str) -> dict[str, Any]:
    """Promote best challenger if statistical + eval_gate pass."""
    try:
        from sqlalchemy import select

        from app.agents.campaign_optimizer import check_promotion_gate
        from app.models.base import get_async_session
        from app.models.campaign_variant import CampaignVariant

        async with get_async_session() as session:
            rows = (
                await session.execute(
                    select(CampaignVariant).where(CampaignVariant.script_id == script_id)
                )
            ).scalars().all()
            champion = next((r for r in rows if r.status == "champion"), None)
            challengers = [r for r in rows if r.status == "challenger"]
            if not champion or not challengers:
                return {"ok": False, "reason": "need champion + challenger"}
            best = max(challengers, key=lambda r: float(r.meeting_rate or 0))
            gate = check_promotion_gate(
                float(champion.meeting_rate or 0),
                float(best.meeting_rate or 0),
                int(champion.impressions or 0),
                int(best.impressions or 0),
            )
            if not gate.get("promote"):
                return {"ok": True, "promoted": False, "gate": gate}
            champion.status = "retired"
            best.status = "champion"
            best.promoted_at = datetime.utcnow()
            await session.commit()
            return {"ok": True, "promoted": True, "new_champion": best.variant_key, "gate": gate}
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}


async def list_variants(script_id: str = "") -> list[dict[str, Any]]:
    try:
        from sqlalchemy import select

        from app.models.base import get_async_session
        from app.models.campaign_variant import CampaignVariant

        async with get_async_session() as session:
            q = select(CampaignVariant)
            if script_id:
                q = q.where(CampaignVariant.script_id == script_id)
            rows = (await session.execute(q.limit(100))).scalars().all()
            return [
                {
                    "id": r.id,
                    "script_id": r.script_id,
                    "variant_key": r.variant_key,
                    "niche": r.niche,
                    "channel": r.channel,
                    "impressions": r.impressions,
                    "meetings": r.meetings,
                    "meeting_rate": r.meeting_rate,
                    "status": r.status,
                }
                for r in rows
            ]
    except Exception:
        return []


__all__ = ["register_variant", "record_event", "try_promote_challenger", "list_variants"]
