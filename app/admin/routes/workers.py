"""
Admin Worker Manager API routes.

GET /admin/api/workers            — all workers with status
GET /admin/api/workers/{name}     — single worker detail
GET /admin/api/workers/idle       — idle workers for assignment
POST /admin/api/workers/{name}/kill — kill worker process
POST /admin/api/workers/{name}/restart — restart worker (kill + relaunch)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.admin.services.worker_manager import (
    get_idle_workers,
    get_worker,
    get_worker_count,
    get_workers,
    kill_worker,
    list_profiles,
)
from app.api.auth_deps import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/api/workers", tags=["Admin Workers"])


@router.get("")
async def list_workers(_user=Depends(require_admin)) -> dict:
    """List all Hermes workers with status, RAM usage, and current task."""
    try:
        return {"workers": get_workers()}
    except Exception as e:
        logger.warning("list_workers failed: %s", e)
        return {"workers": [], "error": str(e)[:160]}


@router.get("/idle")
async def idle_workers(_user=Depends(require_admin)) -> dict:
    """List idle workers available for task assignment."""
    try:
        return {"workers": get_idle_workers()}
    except Exception as e:
        logger.warning("idle_workers failed: %s", e)
        return {"workers": [], "error": str(e)[:160]}


@router.get("/{name}")
async def get_worker_route(name: str, _user=Depends(require_admin)) -> dict:
    """Get single worker detail."""
    try:
        worker = get_worker(name)
        if not worker:
            return {"error": f"Worker '{name}' not found"}
        return worker
    except Exception as e:
        logger.warning("get_worker failed: %s", e)
        return {"error": str(e)[:160]}


@router.post("/{name}/kill")
async def kill_worker_route(name: str, _user=Depends(require_admin)) -> dict:
    """Kill a worker process."""
    try:
        result = kill_worker(name)
        if result.get("ok"):
            return {"ok": True, "message": f"Worker '{name}' killed"}
        return {"ok": False, "error": result.get("error", "Kill failed")}
    except Exception as e:
        logger.warning("kill_worker failed: %s", e)
        return {"ok": False, "error": str(e)[:160]}


@router.post("/{name}/restart")
async def restart_worker(name: str, _user=Depends(require_admin)) -> dict:
    """Restart a worker (kill + relaunch Hermes with profile)."""
    import os
    import subprocess

    try:
        # Kill first
        kill_result = kill_worker(name)
        # Restart via hermes launch command
        # Default Hermes launch on Windows: hermes.exe --profile <name>
        hermes_paths = [
            os.path.expanduser(r"~\AppData\Local\Programs\Hermes\hermes.exe"),
            r"C:\Program Files\Hermes\hermes.exe",
        ]
        hermes_exe = None
        for p in hermes_paths:
            if os.path.isfile(p):
                hermes_exe = p
                break
        if not hermes_exe:
            return {"ok": False, "error": "hermes.exe not found in standard paths"}
        subprocess.Popen(
            [hermes_exe, "--profile", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        return {"ok": True, "message": f"Worker '{name}' restarted", "kill_result": kill_result}
    except Exception as e:
        logger.warning("restart_worker failed: %s", e)
        return {"ok": False, "error": str(e)[:160]}
