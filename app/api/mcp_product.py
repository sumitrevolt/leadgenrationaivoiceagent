"""MCP-as-product API — metered programmatic surface + A2A Agent Card.

This is the platform's outward-facing programmatic interface. Two layers:

1. **Discovery** (public, no auth):
   - GET /.well-known/agent.json   — A2A Agent Card (cross-agent interop)
   - GET /api/mcp-product/v1/discover — capability catalog + auth instructions

2. **Metered capabilities** (X-LeadGen-Key auth + quota):
   - GET  /api/mcp-product/v1/niches    — 42-niche catalog (niches.list)
   - POST /api/mcp-product/v1/score-lead — score a single lead (lead.score)

Plus admin management at /api/admin/mcp-keys for issuing / listing / revoking
keys. Master flag MCP_PRODUCT=1 gates the metered routes (503 when off).
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.platform import mcp_keys

router = APIRouter(tags=["MCP Product"])


# --------------------------------------------------------------------------- #
# Discovery (public)
# --------------------------------------------------------------------------- #
@router.get("/.well-known/agent.json")
async def a2a_agent_card() -> dict[str, Any]:
    """A2A (Agent-to-Agent) discovery card. Other AI agents that speak the
    2026 A2A spec read this to learn what we expose and how to authenticate."""
    return {
        "name": "LeadsGenAI",
        "version": "1.0",
        "description": "Hinglish AI marketing + voice agent for 42 Indian SMB niches.",
        "url": "https://leadsgenai.in",
        "icon": "https://leadsgenai.in/site/icons/icon-192.png",
        "capabilities": [
            {
                "id": cap,
                "type": "rest",
                "path": _CAPABILITY_PATHS.get(cap, ""),
            }
            for cap in mcp_keys.SUPPORTED_CAPABILITIES
        ],
        "auth": {
            "scheme": "api_key",
            "header": "X-LeadGen-Key",
            "issue_at": "/api/admin/mcp-keys (admin)",
        },
        "contact": "admin@leadsgenai.in",
    }


_CAPABILITY_PATHS = {
    "niches.list": "/api/mcp-product/v1/niches",
    "lead.score": "/api/mcp-product/v1/score-lead",
    "qualifier.run": "/api/mcp-product/v1/qualifier",
}


@router.get("/api/mcp-product/v1/discover")
async def discover() -> dict[str, Any]:
    """Capability catalog with auth + meter explanations for SDK builders."""
    return {
        "enabled": mcp_keys.enabled(),
        "capabilities": list(mcp_keys.SUPPORTED_CAPABILITIES),
        "auth": {"header": "X-LeadGen-Key", "format": "lgmcp_<random>"},
        "meter": {"unit": "calls", "window": "1 day", "reset": "00:00 UTC"},
        "paths": _CAPABILITY_PATHS,
    }


# --------------------------------------------------------------------------- #
# Auth helper for the metered surface
# --------------------------------------------------------------------------- #
async def _require_key(
    capability: str,
    x_leadgen_key: str | None,
) -> dict:
    if not mcp_keys.enabled():
        raise HTTPException(status_code=503, detail="MCP-as-product paused (MCP_PRODUCT unset)")
    if not x_leadgen_key:
        raise HTTPException(status_code=401, detail="X-LeadGen-Key header required")
    row = mcp_keys.authenticate(x_leadgen_key)
    if not row:
        raise HTTPException(status_code=401, detail="invalid or revoked key")
    verdict = mcp_keys.check_and_meter(row, capability)
    if not verdict.get("ok"):
        code = int(verdict.get("code", 403))
        headers = {}
        if code == 429 and verdict.get("retry_after_s"):
            headers["Retry-After"] = str(verdict["retry_after_s"])
        raise HTTPException(
            status_code=code, detail=verdict.get("error", "denied"), headers=headers
        )
    return verdict


# --------------------------------------------------------------------------- #
# Metered capabilities
# --------------------------------------------------------------------------- #
@router.get("/api/mcp-product/v1/niches")
async def niches(x_leadgen_key: str | None = Header(default=None, alias="X-LeadGen-Key")) -> dict:
    verdict = await _require_key("niches.list", x_leadgen_key)
    try:
        from app.niches import NICHES

        # NICHES is a list / dict in the project — wrap as-is for the client.
        if isinstance(NICHES, dict):
            data = NICHES
        else:
            data = {"niches": list(NICHES)}
    except Exception:
        data = {"niches": []}
    return {"meter_remaining": verdict.get("remaining"), **data}


class ScoreLeadIn(BaseModel):
    business_name: str = Field(..., min_length=2, max_length=200)
    niche: str = Field("general", max_length=80)
    city: str | None = Field("", max_length=80)
    notes: str | None = Field("", max_length=1000)


class QualifierRunIn(BaseModel):
    """Prospect shape accepted by sales_qualify.bant_score — every field is
    optional. The richer the input, the more accurate the score."""

    business_name: str | None = Field("", max_length=200)
    niche: str | None = Field("", max_length=80)
    city: str | None = Field("", max_length=80)
    phone: str | None = Field("", max_length=20)
    website: str | None = Field("", max_length=500)
    reviews: int | None = Field(None, ge=0, le=1_000_000)
    user_ratings_total: int | None = Field(None, ge=0, le=1_000_000)
    rating: float | None = Field(None, ge=0, le=5)
    employees: int | None = Field(None, ge=0, le=1_000_000)
    annual_revenue_inr: float | None = Field(None, ge=0)
    last_contacted_days_ago: int | None = Field(None, ge=0, le=10000)
    intent: str | None = Field("", max_length=200)
    notes: str | None = Field("", max_length=2000)


@router.post("/api/mcp-product/v1/score-lead")
async def score_lead(
    body: ScoreLeadIn,
    x_leadgen_key: str | None = Header(default=None, alias="X-LeadGen-Key"),
) -> dict:
    """Deterministic, heuristic lead score (0-100). No LLM call — the metered
    surface stays cheap; richer LLM-backed enrichment can be added behind a
    higher tier later. Customers get a stable, billable response."""
    verdict = await _require_key("lead.score", x_leadgen_key)
    name = body.business_name.strip()
    niche = (body.niche or "general").strip().lower()
    city = (body.city or "").strip()
    notes = (body.notes or "").strip()

    # Lean rubric — measurable, no LLM dependency:
    score = 50
    reasons: list[str] = []
    if len(name) >= 10:
        score += 5
        reasons.append("specific business name")
    if city:
        score += 10
        reasons.append("city provided")
    if niche != "general":
        score += 15
        reasons.append(f"niche identified ({niche})")
    if any(k in notes.lower() for k in ("urgent", "interested", "ready", "budget", "abhi")):
        score += 15
        reasons.append("high-intent words in notes")
    if any(k in notes.lower() for k in ("baad me", "later", "maybe", "not sure")):
        score -= 10
        reasons.append("low-intent words in notes")
    score = max(0, min(100, score))
    band = "hot" if score >= 75 else ("warm" if score >= 50 else "cold")
    return {
        "meter_remaining": verdict.get("remaining"),
        "score": score,
        "band": band,
        "reasons": reasons,
        "input": {"business_name": name, "niche": niche, "city": city},
    }


@router.post("/api/mcp-product/v1/qualifier")
async def qualifier_run(
    body: QualifierRunIn,
    x_leadgen_key: str | None = Header(default=None, alias="X-LeadGen-Key"),
) -> dict:
    """M.1: real BANT qualification — pure-Python, zero LLM call, identical
    rubric to the one the in-house Veer agent uses (app/platform/sales_qualify.
    bant_score). Returns total + grade (A/B/C/D) + per-dimension scores +
    reasons + recommended action.

    Field-by-field:
      budget    — derived from annual_revenue_inr + employees + rating
      authority — phone present + role hints in notes
      need      — website-quality + niche match + "intent" string keywords
      timeline  — last_contacted_days_ago + urgency keywords in notes

    Stable contract — customers can build automation that triggers when
    grade in {A, B}. Score scale, grade letters, and action strings are
    versioned via the gateway version field (v1).
    """
    verdict = await _require_key("qualifier.run", x_leadgen_key)
    from app.platform import sales_qualify

    # Convert Pydantic -> plain dict; drop None so bant_score's defaults apply
    prospect = {k: v for k, v in body.model_dump().items() if v not in (None, "")}
    score = sales_qualify.bant_score(prospect)
    return {
        "meter_remaining": verdict.get("remaining"),
        "version": "v1",
        **score,
    }


# --------------------------------------------------------------------------- #
# Admin: issue / list / revoke keys
# --------------------------------------------------------------------------- #
class IssueKeyIn(BaseModel):
    label: str = Field(..., min_length=1, max_length=80)
    daily_limit: int = Field(1000, ge=1, le=1_000_000)
    capabilities: list[str] | None = None


@router.post("/api/admin/mcp-keys")
async def admin_issue(body: IssueKeyIn, _user=Depends(require_admin)) -> dict:
    out = mcp_keys.issue(body.label, body.daily_limit, body.capabilities)
    if not out.get("ok"):
        raise HTTPException(status_code=422, detail=out.get("error", "issue failed"))
    return out


@router.get("/api/admin/mcp-keys")
async def admin_list(_user=Depends(require_admin)) -> dict:
    return {"keys": mcp_keys.list_all(), "usage": mcp_keys.usage_summary()}


@router.delete("/api/admin/mcp-keys/{key_id}")
async def admin_revoke(key_id: str, _user=Depends(require_admin)) -> dict:
    ok = mcp_keys.revoke(key_id)
    if not ok:
        raise HTTPException(status_code=404, detail="key not found or already revoked")
    return {"revoked": True}


class KeyToggleIn(BaseModel):
    enabled: bool


@router.patch("/api/admin/mcp-keys/{key_id}")
async def admin_toggle(key_id: str, body: KeyToggleIn, _user=Depends(require_admin)) -> dict:
    """L.2: pause/resume an MCP key without permanent revocation. Useful for
    quota disputes / suspected leak triage where revoke is too final."""
    ok = mcp_keys.set_enabled(key_id, body.enabled)
    if not ok:
        raise HTTPException(status_code=404, detail="key not found")
    return {"id": key_id, "enabled": body.enabled}


# --------------------------------------------------------------------------- #
# Council 2026-06-26 — Arya MCP Engineer surface (admin)
# --------------------------------------------------------------------------- #
@router.get("/api/admin/mcp/health", tags=["Platform"])
async def admin_mcp_health(_user=Depends(require_admin)) -> dict:
    """Live MCP health snapshot — last hourly pulse from Arya. Cheap (file read)."""
    from app.platform import mcp_engineer

    return mcp_engineer.health_score()


@router.post("/api/admin/mcp/health/run", tags=["Platform"])
async def admin_mcp_health_run(_user=Depends(require_admin)) -> dict:
    """Trigger an on-demand MCP health pass. Returns the full report."""
    from app.platform import mcp_engineer

    return mcp_engineer.run_mcp()


@router.get("/api/admin/mcp/audit", tags=["Platform"])
async def admin_mcp_audit(_user=Depends(require_admin)) -> dict:
    """One-shot security checklist — for /verify and pre-deploy gate."""
    from app.platform import mcp_engineer

    audit = mcp_engineer.audit_mcp_security()
    rotation = mcp_engineer.rotation_due_keys()
    return {"audit": audit, "rotation_due_keys": rotation}


__all__ = ["router"]
