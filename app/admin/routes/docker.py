"""
Admin Docker Manager API routes.

GET /admin/api/docker/containers — all containers
GET /admin/api/docker/containers/{name} — container detail
POST /admin/api/docker/containers/{name}/start
POST /admin/api/docker/containers/{name}/stop
POST /admin/api/docker/containers/{name}/restart
GET /admin/api/docker/containers/{name}/logs — container logs
GET /admin/api/docker/networks — all networks
GET /admin/api/docker/volumes — all volumes
GET /admin/api/docker/stats — resource stats
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from app.admin.services.docker_manager import (
    container_detail,
    get_logs,
    get_stats,
    list_containers,
    list_networks,
    list_volumes,
    restart_container,
    start_container,
    stop_container,
)
from app.api.auth_deps import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/api/docker", tags=["Admin Docker"])


@router.get("/containers")
async def containers(_user=Depends(require_admin)) -> dict:
    """List all Docker containers."""
    try:
        return list_containers()
    except Exception as e:
        logger.warning("containers failed: %s", e)
        return {"ok": False, "error": str(e)[:160]}


@router.get("/containers/{name}")
async def container(name: str, _user=Depends(require_admin)) -> dict:
    """Get container detail."""
    try:
        return container_detail(name)
    except Exception as e:
        logger.warning("container detail failed: %s", e)
        return {"ok": False, "error": str(e)[:160]}


@router.post("/containers/{name}/start")
async def start(name: str, _user=Depends(require_admin)) -> dict:
    """Start a container."""
    try:
        return start_container(name)
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


@router.post("/containers/{name}/stop")
async def stop(name: str, _user=Depends(require_admin)) -> dict:
    """Stop a container."""
    try:
        return stop_container(name)
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


@router.post("/containers/{name}/restart")
async def restart(name: str, _user=Depends(require_admin)) -> dict:
    """Restart a container."""
    try:
        return restart_container(name)
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


@router.get("/containers/{name}/logs")
async def logs(name: str, lines: int = Query(100, ge=1, le=1000), _user=Depends(require_admin)) -> dict:
    """Get container logs."""
    try:
        return get_logs(name, lines)
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


@router.get("/networks")
async def networks(_user=Depends(require_admin)) -> dict:
    """List Docker networks."""
    try:
        return list_networks()
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


@router.get("/volumes")
async def volumes(_user=Depends(require_admin)) -> dict:
    """List Docker volumes."""
    try:
        return list_volumes()
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


@router.get("/stats")
async def stats(_user=Depends(require_admin)) -> dict:
    """Get Docker stats."""
    try:
        return get_stats()
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}
