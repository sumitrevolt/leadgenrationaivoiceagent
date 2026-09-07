"""Admin System Health Monitor API routes.

GET /admin/api/system/health  — aggregate CPU/RAM/Disk + processes + ports
GET /admin/api/system/processes — top 15 watched processes by RAM
GET /admin/api/system/ports  — port status for key service ports
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.admin.services.system_monitor import get_health, get_ports, get_top_processes
from app.api.auth_deps import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/api/system", tags=["Admin System Health"])


@router.get("/health")
async def system_health(_user=Depends(require_admin)) -> dict:
    """Full system health snapshot: CPU/RAM/Disk aggregates, top processes, port status."""
    try:
        return get_health()
    except Exception as e:
        logger.warning("system_health endpoint failed: %s", e)
        return {"error": str(e)[:160]}


@router.get("/processes")
async def system_processes(_user=Depends(require_admin)) -> dict:
    """Top 15 watched processes by RAM usage."""
    try:
        return {"processes": get_top_processes(limit=15)}
    except Exception as e:
        logger.warning("system_processes endpoint failed: %s", e)
        return {"processes": [], "error": str(e)[:160]}


@router.get("/ports")
async def system_ports(_user=Depends(require_admin)) -> dict:
    """Port status for key service ports (3100, 8000, 20128, 56835)."""
    try:
        return {"ports": get_ports()}
    except Exception as e:
        logger.warning("system_ports endpoint failed: %s", e)
        return {"ports": [], "error": str(e)[:160]}
