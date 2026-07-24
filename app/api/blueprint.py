"""Master Project Blueprint — canonical read-only graph API.

Serves the versioned architecture graph defined in
:mod:`app.platform.blueprint_graph` so the ``/app/explorer`` Master Blueprint
mode consumes ONE canonical contract instead of hard-coding architecture truth
in the HTML. Read-only, no auth (architecture map = no secrets, like
``/api/activation/summary``), never-raises, cheap to poll.

Routes (prefix ``/api/blueprint``):
  * ``GET /graph``    — full canonical graph payload (layers/domains/nodes/edges/flows)
  * ``GET /validate`` — schema-integrity pass/fail report (evidence artifact)
  * ``GET /meta``     — lightweight version + counts (poll-cheap)

Live runtime status is deliberately NOT baked in here — the frontend joins live
signals from the already-approved endpoints (``/health``, ``/api/activation/summary``,
``/api/growth/infra/*``) so nodes with no live binding stay honestly ``Unknown``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/api/blueprint", tags=["Blueprint"])


@router.get("/graph")
async def blueprint_graph(check_files: bool = False) -> dict[str, Any]:
    """Canonical versioned architecture graph (no secrets, no auth).

    ``check_files=1`` adds a per-node ``file_ok`` marker for the drift HUD.
    Never raises — returns an empty-but-shaped payload if the module is missing.
    """
    try:
        from app.platform import blueprint_graph as bg

        return bg.build_graph(check_files=check_files)
    except Exception as e:  # pragma: no cover — defensive, never crash the page
        logger.warning(f"blueprint graph unavailable: {type(e).__name__}: {e}")
        return {
            "schema_version": "unavailable",
            "layers": [],
            "domains": [],
            "nodes": [],
            "edges": [],
            "flows": [],
            "evidence_labels": [],
            "node_types": [],
            "edge_kinds": [],
            "counts": {"nodes": 0, "edges": 0, "layers": 0, "domains": 0, "flows": 0},
        }


@router.get("/validate")
async def blueprint_validate(strict_files: bool = True) -> dict[str, Any]:
    """Schema-integrity pass/fail report (dup ids, dangling edges, orphans,
    missing evidence, HARD-OFF invariant). Mirrors the test-suite gate so the
    Explorer can surface a live integrity badge. Never raises."""
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


@router.get("/meta")
async def blueprint_meta() -> dict[str, Any]:
    """Version + counts only (cheap poll for a header badge). Never raises."""
    try:
        from app.platform import blueprint_graph as bg

        return {
            "schema_version": bg.SCHEMA_VERSION,
            "counts": {
                "nodes": len(bg.NODES),
                "edges": len(bg.EDGES),
                "layers": len(bg.LAYERS),
                "domains": len(bg.DOMAINS),
                "flows": len(bg.FLOWS),
            },
        }
    except Exception as e:  # pragma: no cover
        logger.warning(f"blueprint meta unavailable: {type(e).__name__}: {e}")
        return {"schema_version": "unavailable", "counts": {}}
