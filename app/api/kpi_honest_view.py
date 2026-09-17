"""Honest KPI view — admin-gated endpoint that never blends claimed into verified (M5 T05).

WHY THIS EXISTS
---------------
PRD §9: the dashboard must show **proven-executing** as 🟡/❌, not ✅, until
`dev_workers > 0`. This view exposes two separate series (`verified`, `claimed`)
so the owner sees reality, not a blended number.

FastAPI gotcha (ARCH §M5, docs/architecture/ROUTER_GOTCHA.md): a signature-level
``Depends(...)`` lands in ``route.dependant.dependencies``, NOT ``route.dependencies``.
So this route is genuinely gated by ``require_admin`` via a real signature dependency.

Evidence label: CODE-PRESENT (pinned by tests/test_kpi_ledger.py).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends

from app.api.auth_deps import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["KPI Honest View"])


@router.get("/app/kpi/honest")
async def kpi_honest(_admin=Depends(require_admin)) -> dict[str, Any]:
    """Return SEPARATE verified / claimed KPI series. Admin-gated. Never raises.

    The two lists are structurally distinct and must never be summed by any consumer.
    """
    try:
        from app.platform import kpi_ledger

        snap = kpi_ledger.build_kpi_snapshot()
        return {
            "ts": snap["ts"],
            "verified": snap["verified"],
            "claimed": snap["claimed"],
            "blended": False,
            "note": "verified and claimed are separate series — do NOT sum them.",
        }
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[kpi_honest_view] failed: %s", e)
        return {"verified": [], "claimed": [], "blended": False, "error": str(e)[:200]}


@router.get("/app/kpi/dev-workers")
async def kpi_dev_workers(_admin=Depends(require_admin)) -> dict[str, Any]:
    """Execution-proof count (the PRD §1c '#1 trust gap'). Admin-gated. Never raises."""
    try:
        from app.platform.dev_workers import default_store

        store = default_store()
        return {
            "dev_workers": store.count(),
            "verified": store.verified_count(),
            "done": store.count(state="done"),
            "proven_executing": store.verified_count() > 0,
        }
    except Exception as e:  # pragma: no cover - defensive
        return {"dev_workers": 0, "verified": 0, "proven_executing": False, "error": str(e)[:200]}


__all__ = ["router", "kpi_honest", "kpi_dev_workers"]
