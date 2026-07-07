"""API Package"""

from app.api.analytics import router as analytics_router
from app.api.campaigns import router as campaigns_router
from app.api.data import router as data_router
from app.api.platform import router as platform_router
from app.api.webhooks import router as webhooks_router

__all__ = [
    "campaigns_router",
    "analytics_router",
    "webhooks_router",
    "platform_router",
    "data_router",
]
