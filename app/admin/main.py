"""
Admin Module Main Router
Combines all admin sub-routers into a single router.
"""

from fastapi import APIRouter

from app.admin.routes.docker import router as docker_router
from app.admin.routes.system import router as system_router
from app.admin.routes.tasks import router as tasks_router
from app.admin.routes.workers import router as workers_router

command_center_router = APIRouter(tags=["Admin Command Center"])

command_center_router.include_router(system_router)
command_center_router.include_router(workers_router)
command_center_router.include_router(docker_router)
command_center_router.include_router(tasks_router)
