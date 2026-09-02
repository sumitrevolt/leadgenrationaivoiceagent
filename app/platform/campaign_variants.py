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
                (
                    await session.execute(
                        select(CampaignVariant).where(CampaignVariant.script_id == script_id)
                    )
                )
                .scalars()
                .all()
            )
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
                    "replies": r.replies,
                    "meetings": r.meetings,
                    "meeting_rate": r.meeting_rate,
                    "status": r.status,
                }
                for r in rows
            ]
    except Exception:
        return []


async def pick_for_outreach(
    script_id: str,
    *,
    email: str,
    niche: str = "general",
) -> dict[str, Any] | None:
    """Stable champion/challenger pick for cold email. None if <2 active arms."""
    import hashlib

    try:
        from sqlalchemy import select

        from app.models.base import get_async_session
        from app.models.campaign_variant import CampaignVariant

        async with get_async_session() as session:
            rows = (
                (
                    await session.execute(
                        select(CampaignVariant).where(
                            CampaignVariant.script_id == script_id,
                            CampaignVariant.status.in_(["champion", "challenger"]),
                        )
                    )
                )
                .scalars()
                .all()
            )
        if len(rows) < 2:
            return None
        niche_key = (niche or "general").strip()
        filtered = [
            r for r in rows if not (r.niche or "").strip() or r.niche in (niche_key, "general")
        ]
        pool = filtered if len(filtered) >= 2 else list(rows)
        if len(pool) < 2:
            return None
        key = (email or "anon").strip().lower()
        chosen = pool[int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % len(pool)]
        return {
            "id": chosen.id,
            "variant_key": chosen.variant_key,
            "status": chosen.status,
            "content": chosen.content or "",
            "niche": chosen.niche,
            "script_id": chosen.script_id,
        }
    except Exception as e:
        logger.debug("[campaign_variants] pick_for_outreach skip: %s", e)
        return None


async def promotion_summary(script_id: str = "cold_email") -> dict[str, Any]:
    """Variant arms + statistical promotion gate preview."""
    rows = await list_variants(script_id)
    champion = next((r for r in rows if r.get("status") == "champion"), None)
    challengers = [r for r in rows if r.get("status") == "challenger"]
    best = (
        max(challengers, key=lambda r: float(r.get("meeting_rate") or 0)) if challengers else None
    )
    gate: dict[str, Any] | None = None
    if champion and best:
        from app.agents.campaign_optimizer import check_promotion_gate

        gate = check_promotion_gate(
            float(champion.get("meeting_rate") or 0),
            float(best.get("meeting_rate") or 0),
            int(champion.get("impressions") or 0),
            int(best.get("impressions") or 0),
        )
    return {
        "script_id": script_id,
        "variants": rows,
        "champion": champion,
        "best_challenger": best,
        "gate": gate,
        "ready_to_promote": bool(gate and gate.get("promote")),
    }


async def auto_promote_if_ready(script_id: str = "cold_email") -> dict[str, Any]:
    """Try promote when gate passes — never raises."""
    try:
        summary = await promotion_summary(script_id)
        if not summary.get("ready_to_promote"):
            return {
                "ok": True,
                "promoted": False,
                "script_id": script_id,
                "gate": summary.get("gate"),
            }
        result = await try_promote_challenger(script_id)
        result["auto"] = True
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}


async def auto_promote_all(script_ids: list[str] | None = None) -> dict[str, Any]:
    """Try promote for each script (email + voice by default)."""
    ids = script_ids or ["cold_email", "voice_opening"]
    out: dict[str, Any] = {}
    for sid in ids:
        out[sid] = await auto_promote_if_ready(sid)
    return {"ok": True, "results": out}


__all__ = [
    "register_variant",
    "record_event",
    "try_promote_challenger",
    "list_variants",
    "pick_for_outreach",
    "promotion_summary",
    "auto_promote_if_ready",
    "auto_promote_all",
]
