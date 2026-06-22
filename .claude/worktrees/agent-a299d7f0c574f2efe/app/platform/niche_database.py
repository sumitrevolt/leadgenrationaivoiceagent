"""
Niche Prospect Database — AI Voice Agent call infrastructure.
=============================================================

Har niche ke AI voice call ke liye 3 cheezein chahiye:
  1. PROSPECT DATABASE  — jinhe call karna hai (phone, name, niche-specific data)
  2. CALL SCHEMA        — AI agent ko call se pehle kya context chahiye + kya collect karna hai
  3. CALL QUEUE         — kaun-sa prospect next call karna hai (priority order)

Architecture:
  - Core storage: existing `leads` Postgres table (Lead model, qualified_data JSON field)
  - Per-niche schemas: NICHE_CALL_SCHEMA dict — AI agent reads this before dialing
  - Call queue: smart ordering (score DESC, call_attempts ASC, next_call_at first)
  - Bulk import: CSV/JSON rows → Lead records (dedupe by phone)
  - Post-call update: outcome + niche_data + schedule next action

Supported niches: all 25 voice-product niches from niches.py
Kabhi raise nahi karta. All functions defensive.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# NICHE CALL SCHEMAS
# ---------------------------------------------------------------------------
# Har niche ke liye:
#   pre_call_fields : AI agent ko call se PEHLE kya data import karna chahiye
#   collect_during  : Call ke DAURAN AI kya collect karta hai (qualification_data keys)
#   script_context  : TelecallerBrain ke liye niche-specific context hints
#   disqualifiers   : Ye sunta hai to lead drop karo (DND signal)
# ---------------------------------------------------------------------------

from app.platform.niche_database_data import (  # noqa: F401  (data extracted 2026-06-20)
    NICHE_CALL_SCHEMA,
)

# Fallback schema for any niche not explicitly defined
_DEFAULT_SCHEMA: dict = {
    "pre_call_fields": [
        {"key": "contact_name", "label": "Contact name", "type": "text", "required": False},
        {"key": "city", "label": "City", "type": "text", "required": False},
        {"key": "notes", "label": "Notes", "type": "textarea", "required": False},
    ],
    "collect_during": [
        {"key": "requirement", "question": "Aapki requirement kya hai?"},
        {"key": "budget", "question": "Budget approximately kya hai?"},
        {"key": "timeline", "question": "Kab tak chahiye?"},
    ],
    "script_context": "Generic prospect call — requirement + timeline + budget identify karo, next step book karo.",
    "disqualifiers": ["wrong number", "nahi chahiye"],
}


def get_niche_schema(niche_key: str) -> dict:
    """Niche ka call schema — AI agent reads before dialing. Fallback to default."""
    base = NICHE_CALL_SCHEMA.get((niche_key or "").strip().lower(), _DEFAULT_SCHEMA)
    from app.niches import NICHES

    niche_cfg = NICHES.get((niche_key or "").strip().lower(), {})
    return {
        "niche": niche_key,
        "display": base.get("display") or niche_cfg.get("name", niche_key),
        "pre_call_fields": base.get("pre_call_fields", []),
        "collect_during": base.get("collect_during", []),
        "script_context": base.get("script_context", ""),
        "disqualifiers": base.get("disqualifiers", []),
        "qualification_questions": niche_cfg.get("qualification_questions", []),
        "pitch_hook": niche_cfg.get("pitch_hook", ""),
        "band": niche_cfg.get("lead_band", "A"),
    }


# ---------------------------------------------------------------------------
# CALL QUEUE LOGIC
# ---------------------------------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def call_queue_next(client_id: str, niche: str, limit: int = 10) -> list[dict]:
    """Get next prospects to call for a given client+niche.

    Priority:
      1. Scheduled callbacks (next_call_at <= now, status=callback)
      2. Hot leads not yet called (is_hot_lead=True, call_attempts=0)
      3. New leads by score (lead_score DESC)
      4. Attempted leads (call_attempts > 0, status=contacted, score DESC)

    Returns list of dicts with lead data + niche schema context.
    Kabhi raise nahi karta.
    """
    try:
        from app.models.base import get_async_session
        from app.models.lead import Lead, LeadStatus

        results: list[dict] = []
        async with get_async_session() as session:
            from sqlalchemy import and_, or_, select

            now = _now_utc()
            cid = (client_id or "").strip()
            n = (niche or "").strip().lower()

            base_filter = and_(
                Lead.assigned_to == cid,
                Lead.niche == n,
                Lead.status.notin_(
                    [
                        LeadStatus.DND,
                        LeadStatus.WRONG_NUMBER,
                        LeadStatus.NOT_INTERESTED,
                        LeadStatus.CONVERTED,
                        LeadStatus.LOST,
                    ]
                ),
            )

            # Priority 1: callbacks due
            cb_q = (
                select(Lead)
                .where(
                    and_(base_filter, Lead.status == LeadStatus.CALLBACK, Lead.next_call_at <= now)
                )
                .order_by(Lead.next_call_at.asc())
                .limit(limit)
            )
            cb_res = await session.execute(cb_q)
            for lead in cb_res.scalars():
                results.append(_lead_to_call_dict(lead))

            remaining = limit - len(results)
            if remaining <= 0:
                return results

            # Priority 2 + 3: new leads (hot first, then by score)
            new_q = (
                select(Lead)
                .where(and_(base_filter, Lead.status == LeadStatus.NEW))
                .order_by(Lead.is_hot_lead.desc(), Lead.lead_score.desc(), Lead.created_at.asc())
                .limit(remaining)
            )
            new_res = await session.execute(new_q)
            for lead in new_res.scalars():
                results.append(_lead_to_call_dict(lead))

            remaining = limit - len(results)
            if remaining > 0:
                # Priority 4: contacted (retry) — max 3 attempts
                retry_q = (
                    select(Lead)
                    .where(
                        and_(
                            base_filter,
                            Lead.status == LeadStatus.CONTACTED,
                            Lead.call_attempts < 3,
                        )
                    )
                    .order_by(Lead.lead_score.desc(), Lead.call_attempts.asc())
                    .limit(remaining)
                )
                retry_res = await session.execute(retry_q)
                for lead in retry_res.scalars():
                    results.append(_lead_to_call_dict(lead))

        return results
    except Exception as e:
        logger.warning(f"call_queue_next error: {e}")
        return []


def _lead_to_call_dict(lead: Any) -> dict:
    """Lead ORM object -> call queue item dict."""
    try:
        qual = json.loads(lead.qualification_data or "{}") if lead.qualification_data else {}
    except Exception:
        qual = {}
    return {
        "id": lead.id,
        "company_name": lead.company_name,
        "contact_name": lead.contact_name,
        "phone": lead.phone,
        "email": lead.email,
        "city": lead.city,
        "niche": lead.niche,
        "lead_score": lead.lead_score,
        "is_hot_lead": lead.is_hot_lead,
        "status": lead.status.value if lead.status else None,
        "call_attempts": lead.call_attempts,
        "last_called_at": lead.last_called_at.isoformat() if lead.last_called_at else None,
        "next_call_at": lead.next_call_at.isoformat() if lead.next_call_at else None,
        "notes": lead.notes,
        "qualification_data": qual,
        "niche_context": get_niche_schema(lead.niche or ""),
    }


async def update_after_call(
    lead_id: str,
    outcome: str,  # qualified | callback | not_interested | wrong_number | dnd | voicemail
    notes: str = "",
    niche_data: dict | None = None,
    callback_hours: int = 24,
) -> dict:
    """Post-call update — status + niche_data + schedule next action.

    outcome:
      qualified       -> status=QUALIFIED, is_hot_lead=True, score+=20
      callback        -> status=CALLBACK, next_call_at=+callback_hours
      not_interested  -> status=NOT_INTERESTED
      wrong_number    -> status=WRONG_NUMBER
      dnd             -> status=DND, tag dnd
      voicemail       -> status stays CONTACTED, call_attempts++, retry next day
    """
    try:
        from app.models.base import get_async_session
        from app.models.lead import Lead, LeadStatus

        async with get_async_session() as session:
            result = await session.get(Lead, lead_id)
            if not result:
                return {"ok": False, "error": "lead not found"}

            lead = result
            lead.mark_called()

            if niche_data:
                existing = lead.get_qualification_data()
                existing.update(niche_data)
                lead.set_qualification_data(existing)

            if notes:
                lead.notes = f"{lead.notes or ''}\n[{_now_utc().strftime('%Y-%m-%d %H:%M')} UTC] {notes}".strip()

            outcome_l = (outcome or "").strip().lower()
            if outcome_l == "qualified":
                lead.status = LeadStatus.QUALIFIED
                lead.is_hot_lead = True
                lead.update_score(min(100, lead.lead_score + 20))
            elif outcome_l == "callback":
                lead.status = LeadStatus.CALLBACK
                lead.next_call_at = _now_utc() + timedelta(hours=max(1, callback_hours))
            elif outcome_l == "not_interested":
                lead.mark_not_interested(notes)
            elif outcome_l == "wrong_number":
                lead.status = LeadStatus.WRONG_NUMBER
            elif outcome_l == "dnd":
                lead.mark_dnd()
            elif outcome_l == "voicemail":
                lead.status = LeadStatus.CONTACTED
                lead.next_call_at = _now_utc() + timedelta(hours=24)
            # default: CONTACTED (mark_called already set)

            await session.commit()
            return {
                "ok": True,
                "lead_id": lead_id,
                "status": lead.status.value,
                "score": lead.lead_score,
            }
    except Exception as e:
        logger.warning(f"update_after_call error: {e}")
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# BULK IMPORT
# ---------------------------------------------------------------------------


async def bulk_import(
    rows: list[dict],
    niche: str,
    client_id: str,
    source: str = "import",
) -> dict:
    """Bulk import prospects for a niche → Lead records (dedupe by phone).

    row keys (flexible, alias-mapped):
      phone/Phone/mobile/Mobile  →  phone
      name/Name/company/Company/business/Business  →  company_name
      contact/contact_name/owner  →  contact_name
      email/Email  →  email
      city/City    →  city
      state/State  →  state
      + any extra key goes into qualification_data (niche-specific)

    Returns {inserted, skipped, errors}.
    """
    from app.models.base import get_async_session
    from app.models.lead import Lead, LeadSource, LeadStatus

    inserted = 0
    skipped = 0
    errors = 0
    n = (niche or "").strip().lower()
    cid = (client_id or "").strip()

    _PHONE_KEYS = {"phone", "Phone", "mobile", "Mobile", "contact_number", "ContactNumber", "ph"}
    _NAME_KEYS = {"company", "Company", "business", "Business", "name", "Name", "shop", "Shop"}
    _CONTACT_KEYS = {"contact_name", "contact", "owner", "Owner", "person"}
    _EMAIL_KEYS = {"email", "Email", "e-mail"}
    _CITY_KEYS = {"city", "City", "location", "Location"}

    try:
        src_enum = (
            LeadSource[source.upper()]
            if source.upper() in LeadSource.__members__
            else LeadSource.IMPORT
        )
    except Exception:
        src_enum = LeadSource.IMPORT

    async with get_async_session() as session:
        for row in rows:
            try:
                # --- extract phone ---
                phone = ""
                for k in _PHONE_KEYS:
                    if row.get(k):
                        phone = str(row[k]).strip()
                        break
                if not phone:
                    errors += 1
                    continue

                # clean phone
                digits = "".join(c for c in phone if c.isdigit())
                if len(digits) < 10:
                    errors += 1
                    continue
                if len(digits) == 10:
                    phone = "+91" + digits
                elif len(digits) == 12 and digits.startswith("91"):
                    phone = "+" + digits
                elif not phone.startswith("+"):
                    phone = "+91" + digits[-10:]

                # --- dedupe by phone + client ---
                from sqlalchemy import and_, select

                exists = await session.execute(
                    select(Lead.id)
                    .where(and_(Lead.phone == phone, Lead.assigned_to == cid))
                    .limit(1)
                )
                if exists.scalar():
                    skipped += 1
                    continue

                # --- extract other fields ---
                company = ""
                for k in _NAME_KEYS:
                    if row.get(k):
                        company = str(row[k]).strip()
                        break
                if not company:
                    company = phone  # fallback

                contact = ""
                for k in _CONTACT_KEYS:
                    if row.get(k):
                        contact = str(row[k]).strip()
                        break

                email = ""
                for k in _EMAIL_KEYS:
                    if row.get(k):
                        email = str(row[k]).strip()
                        break

                city = ""
                for k in _CITY_KEYS:
                    if row.get(k):
                        city = str(row[k]).strip()
                        break

                # remaining keys → qualification_data
                used = (
                    _PHONE_KEYS
                    | _NAME_KEYS
                    | _CONTACT_KEYS
                    | _EMAIL_KEYS
                    | _CITY_KEYS
                    | {"state", "State"}
                )
                niche_data = {k: v for k, v in row.items() if k not in used and v not in (None, "")}

                lead = Lead(
                    id=str(uuid.uuid4()),
                    company_name=company,
                    contact_name=contact or None,
                    phone=phone,
                    email=email or None,
                    city=city or None,
                    state=(row.get("state") or row.get("State") or ""),
                    niche=n,
                    category=n,
                    assigned_to=cid,
                    source=src_enum,
                    status=LeadStatus.NEW,
                    qualification_data=json.dumps(niche_data) if niche_data else None,
                )
                session.add(lead)
                inserted += 1

            except Exception as row_err:
                logger.debug(f"bulk_import row error: {row_err}")
                errors += 1

        try:
            await session.commit()
        except Exception as ce:
            logger.warning(f"bulk_import commit error: {ce}")
            return {
                "inserted": 0,
                "skipped": skipped,
                "errors": errors + inserted,
                "error": str(ce),
            }

    return {"inserted": inserted, "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# STATS
# ---------------------------------------------------------------------------


async def niche_stats(client_id: str, niche: str | None = None) -> dict:
    """Per-niche prospect stats for a client. Kabhi raise nahi."""
    try:
        from sqlalchemy import and_, func, select

        from app.models.base import get_async_session
        from app.models.lead import Lead, LeadStatus

        cid = (client_id or "").strip()
        async with get_async_session() as session:
            q = select(
                Lead.niche,
                Lead.status,
                func.count(Lead.id).label("cnt"),
                func.avg(Lead.lead_score).label("avg_score"),
            ).where(Lead.assigned_to == cid)
            if niche:
                q = q.where(Lead.niche == niche.strip().lower())
            q = q.group_by(Lead.niche, Lead.status)

            rows = await session.execute(q)
            out: dict[str, dict] = {}
            for row in rows:
                n_key = row.niche or "unknown"
                if n_key not in out:
                    out[n_key] = {
                        "niche": n_key,
                        "total": 0,
                        "by_status": {},
                        "avg_score": 0,
                        "callable": 0,
                    }
                status_val = row.status.value if row.status else "unknown"
                out[n_key]["by_status"][status_val] = row.cnt
                out[n_key]["total"] += row.cnt
                out[n_key]["avg_score"] = round(row.avg_score or 0, 1)
                if status_val in ("new", "contacted", "callback"):
                    out[n_key]["callable"] += row.cnt

            return {"niches": list(out.values()), "client_id": cid}
    except Exception as e:
        logger.warning(f"niche_stats error: {e}")
        return {"niches": [], "error": str(e)}
