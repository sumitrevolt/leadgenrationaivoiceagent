"""Interaction log — append omnichannel touches to DB + jsonl audit.

Every outreach/call/reply writes here when INTERACTION_LOG=1 (default ON).
An OUTBOUND touch also promotes the resolved lead NEW -> CONTACTED via
Lead.mark_contacted() (forward lead-status wiring, 2026-07-25).
Never raises.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _JSONL() -> str:
    """Omnichannel interaction JSONL audit — resolved per call, never frozen at import.

    DB dual-write stays in ``record()``; only this file path follows the shared
    runtime-data authority.
    """
    from app.platform import runtime_data_authority as _auth

    return str(
        _auth.resolve_store_path(
            store_id="communications.interactions",
            legacy_path=Path("data") / "interactions.jsonl",
            target_segments=("communications", "interactions.jsonl"),
        )
    )


def _enabled() -> bool:
    v = os.environ.get("INTERACTION_LOG", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def record(
    *,
    channel: str,
    direction: str = "out",
    phone: str = "",
    email: str = "",
    client_id: str = "",
    lead_id: str = "",
    body_summary: str = "",
    outcome: str = "",
    campaign_variant_id: str = "",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record one interaction — jsonl always, Postgres best-effort."""
    if not _enabled():
        return {"skipped": "INTERACTION_LOG off"}
    iid = str(uuid.uuid4())
    rec = {
        "id": iid,
        "channel": channel[:30],
        "direction": direction[:10],
        "phone": phone,
        "email": email,
        "client_id": client_id,
        "lead_id": lead_id,
        "body_summary": (body_summary or "")[:2000],
        "outcome": outcome[:50],
        "campaign_variant_id": campaign_variant_id,
        "meta": meta or {},
        "occurred_at": _now().isoformat(),
    }
    try:
        # Resolver at each I/O site — derive dir from the active file (A4 lesson:
        # bare os.makedirs("data") is a permanent hole for the next literal).
        os.makedirs(os.path.dirname(_JSONL()) or ".", exist_ok=True)
        with open(_JSONL(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass
    try:
        from sqlalchemy import func, select

        from app.models.base import get_async_session
        from app.models.contact import Contact
        from app.models.interaction import Interaction
        from app.models.lead import Lead
        from app.platform.identity_resolver import _phone10

        contact_id = None
        resolved_lead_id = (lead_id or "").strip() or None
        ph10 = _phone10(phone)
        em = (email or "").strip().lower()
        async with get_async_session() as session:
            if ph10:
                row = (
                    await session.execute(
                        select(Contact).where(Contact.phone_e164.contains(ph10)).limit(1)
                    )
                ).scalar_one_or_none()
                if row:
                    contact_id = row.id
                    resolved_lead_id = resolved_lead_id or getattr(row, "lead_id", None)

            # --- email identity resolution (2026-07-25) --------------------
            # Outreach is overwhelmingly EMAIL (1,951 of 2,611 interactions),
            # and an email interaction carries no phone — so the phone-only
            # lookup above left EVERY email interaction orphaned: 2,611 rows
            # with lead_id=0, incl. 295 replies whose outcome was "interested".
            # Those warm prospects were invisible to the lead pipeline, which
            # is why all 10,559 leads sat at status='new' with an empty
            # lead_status_history. Measured on prod: email resolves 82% of all
            # interactions and 96% of the "interested" ones.
            if em:
                if not contact_id:
                    row = (
                        await session.execute(
                            select(Contact).where(func.lower(Contact.email) == em).limit(1)
                        )
                    ).scalar_one_or_none()
                    if row:
                        contact_id = row.id
                        resolved_lead_id = resolved_lead_id or getattr(row, "lead_id", None)
                if not resolved_lead_id:
                    row = (
                        await session.execute(
                            select(Lead).where(func.lower(Lead.email) == em).limit(1)
                        )
                    ).scalar_one_or_none()
                    if row:
                        resolved_lead_id = row.id

            lead_id = resolved_lead_id or None
            session.add(
                Interaction(
                    id=iid,
                    client_id=client_id or "",
                    contact_id=contact_id,
                    lead_id=lead_id,
                    channel=channel[:30],
                    direction=direction[:10],
                    body_summary=(body_summary or "")[:2000],
                    outcome=outcome[:50],
                    campaign_variant_id=campaign_variant_id or None,
                    meta_json=json.dumps(meta or {}, ensure_ascii=False)[:4000],
                    occurred_at=_now().replace(tzinfo=None),
                )
            )
            # Forward lead-status wiring (2026-07-25): an OUTBOUND touch means we
            # have now contacted this lead. Promote NEW -> CONTACTED via the model
            # helper so a lead_status_history row (changed_by='outreach') is written
            # in the SAME commit. Only direction=='out' (never inbound replies or
            # drafts) and only NEW leads advance — mark_contacted() never downgrades.
            # Best-effort: any failure here must not drop the interaction write.
            if lead_id and (direction or "").strip().lower() == "out":
                try:
                    lead_obj = await session.get(Lead, lead_id)
                    if lead_obj is not None:
                        lead_obj.mark_contacted("outreach")
                except Exception as _e:
                    logger.debug("[interaction_log] mark_contacted skip: %s", _e)
            await session.commit()
    except Exception as e:
        logger.debug("[interaction_log] db skip: %s", e)
    return {"ok": True, "id": iid}


def list_for_phone(phone: str, limit: int = 50) -> list[dict[str, Any]]:
    """Read jsonl interactions for phone (fallback when DB unavailable)."""
    from app.platform.identity_resolver import _phone10

    ph10 = _phone10(phone)
    if not ph10:
        return []
    rows: list[dict[str, Any]] = []
    try:
        if os.path.isfile(_JSONL()):
            with open(_JSONL(), encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            r = json.loads(line)
                            if _phone10(r.get("phone")) == ph10:
                                rows.append(r)
                        except Exception:
                            pass
    except Exception:
        pass
    return rows[-limit:]


__all__ = ["record", "list_for_phone"]
