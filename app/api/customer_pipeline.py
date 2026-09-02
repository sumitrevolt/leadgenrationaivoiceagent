"""Customer-facing lead Pipeline Kanban board (Twenty-CRM parity).

The ADMIN deal-Kanban lives elsewhere and is NOT touched here. This module gives
a PAYING CUSTOMER a drag-drop board of THEIR OWN leads grouped by status.

Design rules (project conventions):
- ONE read-only endpoint ``GET /api/customer/pipeline`` under the same
  ``/api/customer`` prefix as the rest of the customer surface.
- Auth via the SAME ``require_customer`` dependency (client_id from JWT) =>
  IDOR-safe: a customer only ever sees leads scoped to its own client_id.
- Lead loading REUSES the customer-dashboard data source
  (``_build_from_db`` -> ``_build_from_files`` fallback in
  ``app.api.customer_dashboard_builders``). Those builders already apply this
  client's OWN status overrides (lead_overrides.read_overrides), so the
  ``status`` field on each LeadRow is the customer-edited Kanban column.
- never-raise: every handler + helper wrapped defensively; failure => empty board.
- All ``app.*`` imports are lazy (inside functions) so the module is import-safe.

The drag-drop UI moves a card between columns by calling the EXISTING
``PATCH /api/customer/leads/{id}`` endpoint — no new mutation here.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api.customer_auth import require_customer

router = APIRouter(prefix="/api/customer", tags=["Customer Pipeline"])

# Kanban columns == the customer-editable statuses (must stay in sync with
# app.platform.lead_overrides.ALLOWED_STATUSES). Ordered for board left->right.
PIPELINE_COLUMNS: list[str] = ["Hot", "Warm", "Cold", "Follow-up", "Won", "Lost"]


def group_by_status(leads: list[Any]) -> dict[str, Any]:
    """Group a list of leads into the fixed Kanban columns.

    Pure function (no IO, no app.* imports) so it is unit-testable in isolation.

    Each lead may be a dict OR an object (e.g. a LeadRow pydantic model). We read
    ``status`` and a small card-friendly subset of fields defensively. A lead
    whose status is missing/unknown is bucketed by a best-effort match; if it
    still does not map to a known column it is dropped from the board (never
    raises). The function NEVER mutates the input leads.

    Returns ``{"columns": [...], "leads_by_status": {col: [card,...]}, "counts": {col: n}}``.
    """
    columns = list(PIPELINE_COLUMNS)
    leads_by_status: dict[str, list[dict[str, Any]]] = {c: [] for c in columns}

    # Case-insensitive lookup so "follow-up"/"FOLLOW-UP" etc. all map correctly.
    canon = {c.lower(): c for c in columns}

    def _get(lead: Any, key: str) -> str:
        try:
            if isinstance(lead, dict):
                val = lead.get(key)
            else:
                val = getattr(lead, key, None)
            return "" if val is None else str(val)
        except Exception:
            return ""

    for lead in leads or []:
        try:
            raw_status = _get(lead, "status").strip()
            col = canon.get(raw_status.lower())
            if not col:
                # Fall back to the AI tier (`score`: Hot/Warm/Cold) if status is
                # blank/unknown — keeps real leads visible instead of dropping them.
                col = canon.get(_get(lead, "score").strip().lower())
            if not col:
                continue  # genuinely unmappable -> skip (never raise)
            card = {
                "id": _get(lead, "id"),
                "business": _get(lead, "business") or _get(lead, "business_name"),
                "phone": _get(lead, "phone"),
                "city": _get(lead, "city"),
                "niche": _get(lead, "niche"),
                "score": _get(lead, "score"),
                "status": col,
            }
            leads_by_status[col].append(card)
        except Exception:
            continue

    counts = {c: len(leads_by_status[c]) for c in columns}
    return {"columns": columns, "leads_by_status": leads_by_status, "counts": counts}


def _empty_board() -> dict[str, Any]:
    """Safe fallback board (no leads) used on any failure."""
    return group_by_status([])


@router.get("/pipeline")
async def customer_pipeline(client_id: str = Depends(require_customer)) -> dict[str, Any]:
    """Return THIS client's leads grouped into Kanban columns by status.

    Read-only. Reuses the customer-dashboard lead builders (DB-first, file
    fallback) which already scope leads to ``client_id`` and apply this client's
    own status overrides => IDOR-safe. never-raise: returns an empty board on any
    failure rather than 500-ing the customer portal.
    """
    try:
        from app.api.customer_dashboard_builders import _build_from_db, _build_from_files

        resp = None
        try:
            resp = _build_from_db(client_id=client_id, campaign=None)
        except Exception:
            resp = None
        if resp is None:
            resp = _build_from_files(client_id=client_id, campaign=None)

        leads = list(getattr(resp, "leads", None) or [])
        return group_by_status(leads)
    except Exception:
        return _empty_board()
