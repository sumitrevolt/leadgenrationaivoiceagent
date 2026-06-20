"""Apollo-style prospecting endpoints (search / saved-lists / import / email-finder).

Extracted from app/api/growth.py (2026-06-20 refactor) to shrink the god-router.
Mounted via growth.router.include_router(); paths unchanged (/api/growth/prospects/*).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit

router = APIRouter(tags=["Growth"])


# ------------- Apollo-inspired: prospect search/lists/import + email finder ------------- #
@router.get("/prospects/search")
async def prospects_search(
    niche: str = "",
    city: str = "",
    status: str = "",
    has_email: bool | None = None,
    q: str = "",
    min_score: int = 0,
    limit: int = 100,
    _user=Depends(require_admin),
):
    """Apollo-style filter search apne prospects pe (live score ke saath)."""
    from app.platform import prospect_lists

    return prospect_lists.search(niche, city, status, has_email, q, min_score, limit)


class ListIn(BaseModel):
    name: str
    prospect_ids: list[str] | None = None
    filters: dict | None = None


@router.post("/prospects/lists")
async def prospects_create_list(body: ListIn, _user=Depends(require_admin)):
    """Saved list banao (explicit ids ya filters-snapshot)."""
    from app.platform import prospect_lists

    return prospect_lists.create_list(body.name, body.prospect_ids, body.filters)


@router.get("/prospects/lists")
async def prospects_lists(_user=Depends(require_admin)):
    from app.platform import prospect_lists

    return prospect_lists.get_lists()


@router.post("/prospects/lists/{list_id}/enroll-cadence")
async def prospects_list_enroll(list_id: str, _user=Depends(require_admin)):
    """Poori list ko omnichannel cadence me daalo (ban-safe drafts)."""
    from app.platform import prospect_lists

    return prospect_lists.enroll_list_to_cadence(list_id)


class ImportIn(BaseModel):
    rows: list[dict] | None = None
    csv_text: str | None = None
    source: str | None = "apollo_import"


@router.post("/prospects/import")
async def prospects_import(body: ImportIn, _user=Depends(require_admin)):
    """Apollo CSV/rows import → dedupe → prospector store + DB + scoring pipeline."""
    from app.platform import prospect_lists

    if body.csv_text:
        return prospect_lists.import_csv_text(body.csv_text, body.source or "apollo_import")
    return prospect_lists.import_rows(body.rows or [], body.source or "apollo_import")


class EmailFindIn(BaseModel):
    website: str
    owner_name: str | None = ""


@router.post("/prospects/find-email")
async def prospects_find_email(body: EmailFindIn, _user=Depends(require_admin)):
    """Email-finder waterfall: site-extract → pattern-guess → MX verify (Apollo-free)."""
    from app.platform import email_finder

    return await email_finder.find(body.website, body.owner_name or "")


class EmailBatchIn(BaseModel):
    client_id: str = ""
    niche: str = ""
    limit: int = Field(50, ge=1, le=200)


@router.post("/prospects/find-email-batch")
async def prospects_find_email_batch(
    body: EmailBatchIn,
    request: Request,
    _rl=Depends(rate_limit("email_batch", 3, 60)),
    _user=Depends(require_admin),
):
    """Bulk email enrichment: DB leads with phone but no email -> waterfall find -> update."""
    import asyncio as _asyncio

    from sqlalchemy import select as _select

    from app.models.base import get_async_session
    from app.models.lead import Lead
    from app.platform import email_finder

    found = 0
    not_found = 0
    updated = 0
    errors: list = []
    try:
        async with get_async_session() as session:
            q = _select(Lead).where(
                Lead.phone.isnot(None),
                Lead.phone != "",
                Lead.email.is_(None),
            )
            if body.client_id:
                q = q.where(Lead.assigned_to == body.client_id)
            if body.niche:
                q = q.where(Lead.industry == body.niche)
            q = q.limit(body.limit)
            result = await session.execute(q)
            leads = result.scalars().all()

        async def _enrich_one(lead):
            nonlocal found, not_found, updated
            website = (lead.website or "").strip()
            name = (lead.company_name or "").strip()
            if not website:
                not_found += 1
                return {"ok": False, "phone": lead.phone}
            try:
                r = await email_finder.find(website, name)
                emails = r.get("emails") or []
                best = next((e["email"] for e in emails if e.get("verified")), None)
                if best:
                    async with get_async_session() as session:
                        obj = await session.get(Lead, lead.id)
                        if obj:
                            obj.email = best
                            obj.email_verified = True
                            await session.commit()
                    found += 1
                    updated += 1
                    return {"ok": True, "phone": lead.phone, "email": best}
                else:
                    not_found += 1
                    return {"ok": False, "phone": lead.phone}
            except Exception as e:
                errors.append(str(e)[:80])
                not_found += 1
                return {"ok": False, "phone": lead.phone, "error": str(e)[:80]}

        await _asyncio.gather(*[_enrich_one(l) for l in leads])
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}

    return {
        "ok": True,
        "total_checked": found + not_found,
        "found": found,
        "updated": updated,
        "not_found": not_found,
        "errors": errors[:10],
    }
