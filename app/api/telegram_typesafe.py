"""
LeadGen AI — Telegram TypeSafe Router (Compatibility Alias)
===========================================================
Mounts the TypeSafe-specific Telegram endpoints under prefix:
`/api/telegram/typesafe`
"""

from fastapi import APIRouter
from app.api.telegram_bot_api import (
    classify_message,
    get_health,
    get_status,
    route_message,
    validate_response,
    coordinate_handoff,
)

router = APIRouter(prefix="/api/telegram/typesafe", tags=["Telegram TypeSafe"])

router.add_api_route("/health", get_health, methods=["GET"])
router.add_api_route("/status", get_status, methods=["GET"])
router.add_api_route("/classify", classify_message, methods=["POST"])
router.add_api_route("/route", route_message, methods=["POST"])
router.add_api_route("/validate", validate_response, methods=["POST"])
router.add_api_route("/handoff", coordinate_handoff, methods=["POST"])
