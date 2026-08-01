"""
Data API Endpoints
B2B Intelligence Platform - Company Search, Enrichment, and Reports API
"""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth_deps import get_current_user_optional, require_admin
from app.models.base import get_async_db
from app.models.data_credits import CREDIT_COSTS, APIUsageType
from app.services.data_service import DataService
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/data", tags=["Data Intelligence"])


# ==================== PYDANTIC MODELS ====================


class CompanySearchRequest(BaseModel):
    """Company search filters"""

    niche: str | None = Field(None, description="Industry niche (e.g., 'real_estate', 'solar')")
    city: str | None = Field(None, description="City name")
    state: str | None = Field(None, description="State name")
    min_score: int | None = Field(None, ge=0, le=100, description="Minimum quality score")
    verified_only: bool = Field(False, description="Only verified companies")
    has_email: bool = Field(False, description="Must have email")
    has_phone: bool = Field(True, description="Must have phone")


class CompanySearchResponse(BaseModel):
    """Company search results"""

    companies: list[dict[str, Any]]
    total: int
    page: int
    limit: int
    credits_consumed: int = 0


class EnrichResponse(BaseModel):
    """Company enrichment response"""

    company: dict[str, Any]
    credits_consumed: int


class ExportRequest(BaseModel):
    """Export request"""

    company_ids: list[str] = Field(..., min_length=1, max_length=1000)


class ExportResponse(BaseModel):
    """Export response"""

    companies: list[dict[str, Any]]
    count: int
    credits_consumed: int


class ReportRequest(BaseModel):
    """Market report request"""

    report_type: str = Field(..., pattern="^(basic|detailed|custom)$")
    niche: str
    city: str | None = None


class ReportResponse(BaseModel):
    """Market report response"""

    report: dict[str, Any]
    credits_consumed: int


class APIKeyCreateRequest(BaseModel):
    """API key creation request"""

    name: str = Field(..., min_length=1, max_length=100)
    scopes: list[str] = Field(default=["read"])
    rate_limit_per_minute: int = Field(default=60, ge=1, le=1000)
    expires_in_days: int | None = Field(None, ge=1, le=365)


class APIKeyResponse(BaseModel):
    """API key response"""

    id: str
    name: str
    key: str | None = None  # Only returned on creation
    prefix: str
    scopes: list[str]
    created_at: str


class CreditBalanceResponse(BaseModel):
    """Credit balance response"""

    balance: int
    lifetime_credits: int
    used_credits: int
    monthly_limit: int
    monthly_used: int


class AddCreditsRequest(BaseModel):
    """Add credits request"""

    amount: int = Field(..., ge=1, le=1000000)
    description: str | None = ""


# ==================== DEPENDENCY ====================


async def get_api_key_client(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_async_db),
) -> str | None:
    """Validate API key and return client_id"""
    if not x_api_key:
        return None

    service = DataService(db)
    api_key = await service.validate_api_key(x_api_key)

    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")

    return api_key.client_id


async def get_client_id(
    request: Request,
    api_client_id: str | None = Depends(get_api_key_client),
    user=Depends(get_current_user_optional),
) -> str:
    """Get client ID from API key or authenticated user"""
    if api_client_id:
        return api_client_id

    if user and hasattr(user, "client_id"):
        return user.client_id

    # Anonymous request: PRODUCTION me block karo — warna koi bhi bina auth ke
    # metered lead-search/export/reports hit karke shared credits drain kar leta.
    # Dev/test me hi "demo-client" shortcut allowed.
    from app.config import settings

    if getattr(settings, "is_production", False):
        raise HTTPException(
            status_code=401,
            detail="Is endpoint ke liye API key ya login chahiye.",
        )
    return "demo-client"


# ==================== SEARCH ENDPOINTS ====================


@router.get("/companies", response_model=CompanySearchResponse)
async def search_companies(
    niche: str | None = Query(None, description="Industry niche"),
    city: str | None = Query(None, description="City name"),
    state: str | None = Query(None, description="State name"),
    min_score: int | None = Query(None, ge=0, le=100, description="Minimum quality score"),
    verified_only: bool = Query(False, description="Only verified companies"),
    has_email: bool = Query(False, description="Must have email"),
    has_phone: bool = Query(True, description="Must have phone"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=200, description="Results per page"),
    client_id: str = Depends(get_client_id),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Search companies in the database.

    **FREE** - Searches don't consume credits. Credits are used when you export or enrich.

    Returns preview data with masked contact information.
    """
    service = DataService(db)

    offset = (page - 1) * limit
    companies, total = await service.search_companies(
        client_id=client_id,
        niche=niche,
        city=city,
        state=state,
        min_score=min_score,
        verified_only=verified_only,
        has_email=has_email,
        has_phone=has_phone,
        limit=limit,
        offset=offset,
    )

    return CompanySearchResponse(
        companies=companies,
        total=total,
        page=page,
        limit=limit,
        credits_consumed=0,  # Searches are free
    )


@router.get("/companies/{company_id}", response_model=EnrichResponse)
async def get_company_details(
    company_id: str,
    client_id: str = Depends(get_client_id),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get full company details including contact information.

    **Costs 2 credits** per enrichment.
    """
    service = DataService(db)

    company, error = await service.enrich_company(
        client_id=client_id,
        company_id=company_id,
    )

    if error:
        raise HTTPException(status_code=400, detail=error)

    return EnrichResponse(
        company=company, credits_consumed=CREDIT_COSTS[APIUsageType.COMPANY_ENRICH]
    )


@router.post("/companies/export", response_model=ExportResponse)
async def export_companies(
    request: ExportRequest,
    client_id: str = Depends(get_client_id),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Export multiple companies with full contact details.

    **Costs 1 credit per company** exported.
    """
    service = DataService(db)

    companies, error = await service.export_companies(
        client_id=client_id,
        company_ids=request.company_ids,
    )

    if error:
        raise HTTPException(status_code=400, detail=error)

    return ExportResponse(
        companies=companies,
        count=len(companies),
        credits_consumed=len(companies) * CREDIT_COSTS[APIUsageType.COMPANY_EXPORT],
    )


# ==================== REPORTS ENDPOINTS ====================


@router.post("/reports", response_model=ReportResponse)
async def generate_report(
    request: ReportRequest,
    client_id: str = Depends(get_client_id),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Generate a market intelligence report.

    **Costs**:
    - Basic: 10 credits
    - Detailed: 50 credits
    - Custom: 100 credits
    """
    service = DataService(db)

    report, error = await service.generate_report(
        client_id=client_id,
        report_type=request.report_type,
        niche=request.niche,
        city=request.city,
    )

    if error:
        raise HTTPException(status_code=400, detail=error)

    type_map = {
        "basic": APIUsageType.REPORT_BASIC,
        "detailed": APIUsageType.REPORT_DETAILED,
        "custom": APIUsageType.REPORT_CUSTOM,
    }

    return ReportResponse(
        report=report, credits_consumed=CREDIT_COSTS[type_map[request.report_type]]
    )


# ==================== NICHES & CITIES ====================


_niches_cache = None  # module-level lazy init


def _get_niches_cache():
    global _niches_cache
    if _niches_cache is None:
        try:
            from app.cache import Cache

            _niches_cache = Cache(prefix="api_niches", default_ttl=300)
        except Exception:
            pass
    return _niches_cache


async def _niches_cache_gen(cache) -> int:
    """Current cache generation. Every listing key is namespaced by this; bumping it
    (on create/delete) invalidates ALL filter-combo keys at once — works regardless of
    key format and across workers (token lives in the shared cache). Fail-soft → 0."""
    if not cache:
        return 0
    try:
        return int(await cache.get("__gen__") or 0)
    except Exception:
        return 0


async def _invalidate_niches_cache() -> None:
    """Bust the cached niches listing after a create/delete so the new/removed niche
    shows up immediately (else stale up to TTL — and stale across tests in a shared
    process). Bumps the generation token; old keys orphan + TTL-expire. Never raises.
    The real Cache exposes only get/set/delete (no keys/flush), so we can't prefix-scan
    — generation bump is the portable invalidation."""
    cache = _get_niches_cache()
    if not cache:
        return
    try:
        gen = await _niches_cache_gen(cache)
        # store as str: Cache.set only json-encodes dict/list, and Cache.get does
        # json.loads(value) (TypeError on a raw int via the in-memory fallback).
        # str round-trips on both backends (json.loads("1") -> 1).
        await cache.set("__gen__", str(gen + 1), ttl=86400)
    except Exception:
        pass


@router.get("/niches")
async def get_available_niches(target_type: str = None, tier: str = None, product: str = None):
    """
    List available industry niches (research-finalized top 25 + custom).
    Optional filters: target_type=b2c|b2b (end-customer audience), tier=S|A|B|C,
    product=marketing|voice (ADR-009 — dono products ke niche sets ALAG).
    Redis-cached 5 min (static data, hot endpoint).
    """
    cache = _get_niches_cache()
    gen = await _niches_cache_gen(cache)
    cache_key = f"g{gen}:{target_type or ''}:{tier or ''}:{product or ''}"
    if cache:
        try:
            cached = await cache.get(cache_key)
            if cached:
                return cached
        except Exception:
            pass

    from app.niches import NICHES, niche_products, refresh_custom_niches

    refresh_custom_niches()

    p = (product or "").strip().lower()
    niches = [
        {
            "id": key,
            "name": config.get("name", key.replace("_", " ").title()),
            "description": config.get("pitch_hook", ""),
            "keywords": config.get("keywords", [])[:5],
            "tier": config.get("tier"),
            "custom": bool(config.get("custom")),
            "target_type": config.get("target_type"),
            "b2b_client": config.get("b2b_client"),
            "end_customer": config.get("end_customer"),
            "avg_ticket_inr": config.get("avg_ticket_inr", config.get("avg_deal_value")),
            "products": niche_products(config),
            "lead_band": config.get("lead_band", "A"),
        }
        for key, config in NICHES.items()
        if (not target_type or config.get("target_type") in (target_type.lower(), "both"))
        and (not tier or config.get("tier") == tier.upper())
        and (p not in ("marketing", "voice") or p in niche_products(config))
    ]

    result = {"niches": niches, "count": len(niches), "product": p or "all"}
    if cache:
        try:
            await cache.set(cache_key, result)
        except Exception:
            pass
    return result


class NicheCreate(BaseModel):
    """Custom niche — sirf name zaroori, baaki optional (defaults sensible)."""

    name: str
    key: str | None = None
    target_type: str = "b2c"  # b2c | b2b | both
    b2b_client: str = ""
    end_customer: str = ""
    avg_ticket_inr: str = ""
    pitch_hook: str = ""
    keywords: list[str] | None = None
    qualification_questions: list[str] | None = None
    lead_band: str = "A"  # voice-product band A|B|C (ADR-009; per-lead pricing removed)


@router.post("/niches")
async def create_custom_niche(
    payload: NicheCreate,
    current_user=Depends(require_admin),
):
    """
    Naya custom niche add karo — turant flows/KB/agents/web-call sab me
    kaam karta hai. data/custom_niches.json me persist hota hai.
    """
    from app.niches import add_custom_niche

    try:
        key, cfg = add_custom_niche(
            name=payload.name,
            key=payload.key,
            target_type=payload.target_type.lower(),
            b2b_client=payload.b2b_client,
            end_customer=payload.end_customer,
            avg_ticket_inr=payload.avg_ticket_inr,
            pitch_hook=payload.pitch_hook,
            keywords=payload.keywords,
            qualification_questions=payload.qualification_questions,
            lead_band=payload.lead_band,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # KB seed (best-effort) — naya niche turant grounded-answers de sake.
    try:
        from app.voice_agent.kb_loader import bootstrap_default_kb

        kb = bootstrap_default_kb()
        facts = [
            f"Niche: {cfg['name']}. Typical deal value: {cfg['avg_ticket_inr']}.",
            f"Pitch: {cfg['pitch_hook']}",
            f"End customers: {cfg['end_customer']}",
        ] + [f"Qualification question: {q}" for q in cfg["qualification_questions"]]
        kb.add_documents(facts, source=f"niche:{key}", namespace=key)
        kb.add_documents(facts, source=f"niche:{key}", namespace="_global")
    except Exception:
        pass

    await _invalidate_niches_cache()  # new niche turant listing me dikhe (stale cache bust)
    return {"id": key, "niche": cfg, "message": "Custom niche added — agents/flows/KB sab me live"}


@router.delete("/niches/{niche_key}")
async def delete_custom_niche(
    niche_key: str,
    current_user=Depends(require_admin),
):
    """Custom niche remove karo (built-in 25 protected hain)."""
    from app.niches import remove_custom_niche

    try:
        removed = remove_custom_niche(niche_key)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not removed:
        raise HTTPException(status_code=404, detail="Custom niche not found")
    await _invalidate_niches_cache()  # removed niche listing se turant hate (stale cache bust)
    return {"id": niche_key, "message": "Custom niche removed"}


# ── Pending Niches (admin review queue) ──────────────────────────────────── #

import json as _json_pending
import re as _re_pending
import uuid as _uuid_pending
from pathlib import Path as _Path_pending

_PENDING_FILE = (
    _Path_pending(__file__).resolve().parent.parent.parent / "data" / "pending_niches.json"
)


def _slugify_pending(name: str) -> str:
    s = _re_pending.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return (s[:50] or "custom") + "_" + _uuid_pending.uuid4().hex[:4]


def _read_pending() -> list:
    try:
        if _PENDING_FILE.exists():
            return _json_pending.loads(_PENDING_FILE.read_text(encoding="utf-8")) or []
    except Exception:
        pass
    return []


def _write_pending(items: list) -> None:
    try:
        _PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PENDING_FILE.write_text(
            _json_pending.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


class PendingNicheIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    submitted_by: str = Field("", max_length=80)  # admin email / client context


@router.post("/niches/pending")
async def submit_pending_niche(payload: PendingNicheIn, current_user=Depends(require_admin)):
    """Admin ne koi nayi niche submit ki — review queue me save karo."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name required")
    items = _read_pending()
    # dedupe by normalized name
    norm = name.lower()
    if any(i.get("name", "").lower() == norm for i in items):
        raise HTTPException(status_code=409, detail="Yeh niche pehle se pending me hai")
    item = {
        "id": _slugify_pending(name),
        "name": name,
        "submitted_by": payload.submitted_by or getattr(current_user, "email", "admin"),
        "status": "pending",
        "submitted_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }
    items.append(item)
    _write_pending(items)
    return {
        "ok": True,
        "id": item["id"],
        "name": name,
        "status": "pending",
        "message": "Niche review queue me add ho gayi — admin approve karne ke baad permanent list me aayegi",
    }


@router.get("/niches/pending")
async def list_pending_niches(current_user=Depends(require_admin)):
    """Admin: review queue ki sabhi pending niches."""
    return {"pending": _read_pending(), "count": len(_read_pending())}


@router.post("/niches/pending/{pending_id}/approve")
async def approve_pending_niche(pending_id: str, current_user=Depends(require_admin)):
    """Admin: pending niche approve karo → custom niches permanent list me add ho jaati hai."""
    items = _read_pending()
    item = next((i for i in items if i.get("id") == pending_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Pending niche nahi mili")
    from app.niches import _BUILTIN_KEYS, NICHES, add_custom_niche, refresh_custom_niches

    name = item["name"]
    refresh_custom_niches()
    slug = _re_pending.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:50]
    if slug in NICHES:
        # already added — just remove from pending
        items = [i for i in items if i.get("id") != pending_id]
        _write_pending(items)
        return {"ok": True, "message": "Niche pehle se exist karti hai — pending se remove kiya"}
    try:
        key, cfg = add_custom_niche(name=name, lead_band="A")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    # remove from pending
    items = [i for i in items if i.get("id") != pending_id]
    _write_pending(items)
    await _invalidate_niches_cache()
    return {
        "ok": True,
        "niche_key": key,
        "name": name,
        "message": f"'{name}' approve ho gayi — ab permanently niches list me hai",
    }


@router.delete("/niches/pending/{pending_id}")
async def reject_pending_niche(pending_id: str, current_user=Depends(require_admin)):
    """Admin: pending niche reject/delete karo."""
    items = _read_pending()
    before = len(items)
    items = [i for i in items if i.get("id") != pending_id]
    if len(items) == before:
        raise HTTPException(status_code=404, detail="Pending niche nahi mili")
    _write_pending(items)
    return {"ok": True, "message": "Pending niche reject kar di"}


@router.get("/cities")
async def get_available_cities(
    db: AsyncSession = Depends(get_async_db),
    client_id: str = Depends(
        get_client_id
    ),  # metered Lead aggregate — block anon in prod (matches siblings)
):
    """Get list of cities with company counts"""
    from sqlalchemy import func, select

    from app.models.lead import Lead

    query = (
        select(Lead.city, func.count(Lead.id).label("count"))
        .where(Lead.city.isnot(None))
        .group_by(Lead.city)
        .order_by(func.count(Lead.id).desc())
        .limit(50)
    )

    result = await db.execute(query)
    cities = [{"city": row.city, "company_count": row.count} for row in result]

    return {"cities": cities}


# ==================== CREDITS & API KEYS ====================


@router.get("/credits", response_model=CreditBalanceResponse)
async def get_credit_balance(
    client_id: str = Depends(get_client_id),
    db: AsyncSession = Depends(get_async_db),
):
    """Get current credit balance"""
    service = DataService(db)
    balance = await service.get_credit_balance(client_id)
    return CreditBalanceResponse(**balance)


@router.get("/credits/pricing")
async def get_credit_pricing():
    """Get credit costs for each operation.

    Single source: app/models/data_credits.py CREDIT_COSTS. The old hardcoded
    credit-PACK list (₹2,500/8,000/17,500/30,000) was dead data — no consumer
    ever fetched it (grep 2026-08-01) aur hardcoded pricing billing-truth ka
    violation hai. Operations costs hi kaafi hain."""
    return {
        "operations": {
            usage_type.value: {"credits": cost, "description": _get_usage_description(usage_type)}
            for usage_type, cost in CREDIT_COSTS.items()
        },
    }


def _get_usage_description(usage_type: APIUsageType) -> str:
    """Get description for usage type"""
    descriptions = {
        APIUsageType.COMPANY_SEARCH: "Search companies (FREE)",
        APIUsageType.COMPANY_ENRICH: "Get full company details",
        APIUsageType.COMPANY_EXPORT: "Export company to CSV/CRM",
        APIUsageType.REPORT_BASIC: "Basic market report",
        APIUsageType.REPORT_DETAILED: "Detailed market report with top companies",
        APIUsageType.REPORT_CUSTOM: "Custom research report",
        APIUsageType.API_LOOKUP: "Single API lookup",
    }
    return descriptions.get(usage_type, "")


@router.post("/api-keys", response_model=APIKeyResponse)
async def create_api_key(
    request: APIKeyCreateRequest,
    client_id: str = Depends(get_client_id),
    db: AsyncSession = Depends(get_async_db),
):
    """Create a new API key for programmatic access"""
    service = DataService(db)

    raw_key, api_key = await service.create_api_key(
        client_id=client_id,
        name=request.name,
        scopes=request.scopes,
        rate_limit_per_minute=request.rate_limit_per_minute,
        expires_in_days=request.expires_in_days,
    )

    return APIKeyResponse(
        id=api_key.id,
        name=api_key.name,
        key=raw_key,  # Only returned once!
        prefix=api_key.key_prefix,
        scopes=request.scopes,
        created_at=api_key.created_at.isoformat(),
    )


@router.get("/api-keys")
async def list_api_keys(
    client_id: str = Depends(get_client_id),
    db: AsyncSession = Depends(get_async_db),
):
    """List all API keys"""
    service = DataService(db)
    keys = await service.list_api_keys(client_id)
    return {"api_keys": keys}


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    client_id: str = Depends(get_client_id),
    db: AsyncSession = Depends(get_async_db),
):
    """Revoke an API key"""
    service = DataService(db)
    success = await service.revoke_api_key(client_id, key_id)

    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    return {"message": "API key revoked"}


# ==================== USAGE ANALYTICS ====================


@router.get("/usage")
async def get_usage_stats(
    days: int = Query(30, ge=1, le=90),
    client_id: str = Depends(get_client_id),
    db: AsyncSession = Depends(get_async_db),
):
    """Get usage statistics for the past N days"""
    service = DataService(db)
    stats = await service.get_usage_stats(client_id, days)
    return stats
