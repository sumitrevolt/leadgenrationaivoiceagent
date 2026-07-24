"""Master Project Blueprint — canonical graph API (admin full + public sanitized).

Serves the versioned architecture graph defined in
:mod:`app.platform.blueprint_graph` so the ``/app/explorer`` Master Blueprint
mode consumes ONE canonical contract instead of hard-coding architecture truth.

Security (PR #125 hardening):
  * ``/graph`` ``/validate`` ``/trace`` → **admin-only** (``require_admin``).
    These carry repo file paths, feature-flag inventory, runtime probe keys,
    tech-refs and internal edges — internal architecture, not for the public.
  * ``/public`` → **sanitized** business-safe contract (labels + high-level
    connections + coarse state only; no paths/flags/runtime/desc).
  * ``/meta`` → version + counts only (business-safe, no sensitive metadata).

Read-only, no secrets, never-raises. Live runtime status is joined client-side
from already-approved endpoints; nodes with no live binding stay honestly
``Unknown`` (never fabricated ``Healthy``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.auth_deps import require_admin
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/api/blueprint", tags=["Blueprint"])


@router.get("/graph")
async def blueprint_graph(
    check_files: bool = False, _user=Depends(require_admin)
) -> dict[str, Any]:
    """FULL canonical architecture graph — **admin-only** (repo paths, flags,
    runtime keys, tech_refs). ``check_files=1`` adds per-node ``file_ok``.
    Never raises — returns an empty-but-shaped payload if the module is missing."""
    try:
        from app.platform import blueprint_graph as bg

        return bg.build_graph(check_files=check_files)
    except Exception as e:  # pragma: no cover — defensive, never crash
        logger.warning(f"blueprint graph unavailable: {type(e).__name__}: {e}")
        return {
            "schema_version": "unavailable",
            "visibility": "admin",
            "layers": [],
            "domains": [],
            "nodes": [],
            "edges": [],
            "flows": [],
            "evidence_labels": [],
            "node_types": [],
            "edge_kinds": [],
            "edge_types": [],
            "counts": {"nodes": 0, "edges": 0, "layers": 0, "domains": 0, "flows": 0},
        }


@router.get("/public")
async def blueprint_public() -> dict[str, Any]:
    """SANITIZED public contract (no auth). Business-safe labels + high-level
    connections + coarse state ONLY. No repo paths, flags, runtime keys, or
    operational-weakness detail. Never raises."""
    try:
        from app.platform import blueprint_graph as bg

        return bg.build_public_graph()
    except Exception as e:  # pragma: no cover
        logger.warning(f"blueprint public unavailable: {type(e).__name__}: {e}")
        return {
            "schema_version": "unavailable",
            "visibility": "public",
            "layers": [],
            "domains": [],
            "nodes": [],
            "edges": [],
            "flows": [],
            "counts": {"nodes": 0, "edges": 0, "layers": 0, "domains": 0, "flows": 0},
        }


@router.get("/validate")
async def blueprint_validate(
    strict_files: bool = True, _user=Depends(require_admin)
) -> dict[str, Any]:
    """Schema-integrity pass/fail report — **admin-only** (surfaces internal
    structure). Mirrors the test-suite gate. Never raises."""
    try:
        from app.platform import blueprint_graph as bg

        return bg.validate_graph(strict_files=strict_files)
    except Exception as e:  # pragma: no cover
        logger.warning(f"blueprint validate unavailable: {type(e).__name__}: {e}")
        return {
            "ok": False,
            "errors": [f"validator unavailable: {type(e).__name__}"],
            "warnings": [],
            "schema_version": "unavailable",
            "counts": {},
        }


@router.get("/trace")
async def blueprint_trace(
    src: str = Query(..., min_length=1, max_length=64),
    tgt: str | None = Query(None, max_length=64),
    direction: str = Query("down", pattern="^(up|down|both)$"),
    depth: int = Query(3, ge=0, le=12),
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Multi-hop traversal — **admin-only**. Upstream/downstream (bounded depth),
    shortest path (when ``tgt`` given), and downstream impact. Cycle-safe,
    deterministic. Never raises."""
    try:
        from app.platform import blueprint_graph as bg

        out: dict[str, Any] = {
            "src": src,
            "direction": direction,
            "depth": depth,
            "reachable": bg.traverse(src, direction, depth),
            "impact": bg.impact(src, depth),
        }
        if tgt:
            out["tgt"] = tgt
            out["shortest_path"] = bg.shortest_path(src, tgt)
        return out
    except Exception as e:  # pragma: no cover
        logger.warning(f"blueprint trace unavailable: {type(e).__name__}: {e}")
        return {"src": src, "reachable": [], "impact": [], "shortest_path": []}


@router.get("/meta")
async def blueprint_meta() -> dict[str, Any]:
    """Version + counts only (business-safe public poll). Never raises."""
    try:
        from app.platform import blueprint_graph as bg

        wf = bg._workforce()
        return {
            "schema_version": bg.SCHEMA_VERSION,
            "counts": {
                "nodes": len(bg.NODES),
                "edges": len(bg.EDGES),
                "layers": len(bg.LAYERS),
                "domains": len(bg.DOMAINS),
                "flows": len(bg.FLOWS),
                "workforce": wf["count"],
            },
        }
    except Exception as e:  # pragma: no cover
        logger.warning(f"blueprint meta unavailable: {type(e).__name__}: {e}")
        return {"schema_version": "unavailable", "counts": {}}
