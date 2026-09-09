"""
Admin Module Main Router
Combines all admin sub-routers into a single router.
"""

from fastapi import APIRouter

from app.admin.routes.system import router as system_router
from app.admin.routes.tasks import router as tasks_router

# NOTE: docker + workers routers are included DIRECTLY by app/main.py
# (lines ~1271-1277) to avoid first-route-wins shadow. Only add
# NEW Command Center–specific sub-routers here.

admin_router = APIRouter(tags=["Admin Command Center"])

admin_router.include_router(system_router)
admin_router.include_router(tasks_router)

# Alias for app/main.py import compatibility
router = admin_router
