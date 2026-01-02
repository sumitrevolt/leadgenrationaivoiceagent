"""API Package"""
from app.api.leads import router as leads_router
from app.api.campaigns import router as campaigns_router
from app.api.analytics import router as analytics_router
from app.api.webhooks import router as webhooks_router
from app.api.platform import router as platform_router

__all__ = ["leads_router", "campaigns_router", "analytics_router", "webhooks_router", "platform_router"]
