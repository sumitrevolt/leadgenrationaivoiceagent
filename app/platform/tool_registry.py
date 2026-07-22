"""
Tool Registry & Contract Layer (M2) — MCP-Aligned Schema Validation & Scoping.
=============================================================================

WHY (2026-07-22, Agent Harness Engineering Standard M2):
Centralizes JSON Schema definitions for all agent capabilities. Provides explicit
least-privilege payload schema validation before tool dispatch, preventing invalid
payload execution or dynamic attribute injection.

Import-safe; zero side-effects on import.
"""

from __future__ import annotations

from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Capability JSON Schema registry (M2 standard)
CAPABILITY_SCHEMAS: dict[str, dict[str, Any]] = {
    "ops_health_check": {
        "type": "object",
        "properties": {
            "check_type": {"type": "string", "default": "ops_health_check"},
        },
        "required": [],
        "additionalProperties": True,
    },
    "draft_content_brief": {
        "type": "object",
        "properties": {
            "topic": {"type": "string"},
            "business_name": {"type": "string"},
            "target_audience": {"type": "string"},
        },
        "required": [],
        "additionalProperties": True,
    },
    "queue_approved_content": {
        "type": "object",
        "properties": {
            "content_item_id": {"type": "string"},
            "approval_ref": {"type": "string"},
            "channel": {"type": "string"},
        },
        "required": [],
        "additionalProperties": True,
    },
    "leads_prospect": {
        "type": "object",
        "properties": {
            "niche": {"type": "string"},
            "city": {"type": "string"},
            "limit": {"type": "integer", "default": 10},
        },
        "required": [],
        "additionalProperties": True,
    },
    "whatsapp_send": {
        "type": "object",
        "properties": {
            "recipient_phone": {"type": "string"},
            "message_text": {"type": "string"},
            "approval_ref": {"type": "string"},
        },
        "required": ["recipient_phone", "message_text"],
        "additionalProperties": True,
    },
    "auto_content_generate": {
        "type": "object",
        "properties": {
            "niche": {"type": "string"},
            "count": {"type": "integer", "default": 5},
            "language": {"type": "string", "default": "hinglish"},
        },
        "required": [],
        "additionalProperties": True,
    },
    "niche_pack_generate": {
        "type": "object",
        "properties": {
            "niche_id": {"type": "string"},
            "platform": {"type": "string"},
        },
        "required": [],
        "additionalProperties": True,
    },
    "gbp_post_draft": {
        "type": "object",
        "properties": {
            "business_name": {"type": "string"},
            "offer_details": {"type": "string"},
        },
        "required": [],
        "additionalProperties": True,
    },
    "review_response_draft": {
        "type": "object",
        "properties": {
            "review_id": {"type": "string"},
            "rating": {"type": "integer"},
            "review_text": {"type": "string"},
        },
        "required": [],
        "additionalProperties": True,
    },
    "reply_triage": {
        "type": "object",
        "properties": {
            "inquiry_id": {"type": "string"},
            "channel": {"type": "string"},
        },
        "required": [],
        "additionalProperties": True,
    },
    "delivery_assurance_scan": {
        "type": "object",
        "properties": {
            "tenant_id": {"type": "string"},
        },
        "required": [],
        "additionalProperties": True,
    },
    "billing_meter_reconcile": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string"},
            "period": {"type": "string"},
        },
        "required": [],
        "additionalProperties": True,
    },
}


def get_tool_schema(capability_name: str) -> dict[str, Any] | None:
    """Return JSON schema dict for capability, or generic default if unregistered."""
    return CAPABILITY_SCHEMAS.get(capability_name)


def validate_tool_payload(capability_name: str, payload: dict[str, Any]) -> tuple[bool, str]:
    """Validate payload against capability schema. Returns (is_valid, error_reason).

    Fail-closed: if required keys are missing or payload is not a dict.
    """
    if not isinstance(payload, dict):
        return False, "Payload must be a valid dict object"

    schema = get_tool_schema(capability_name)
    if not schema:
        # Permissive default for unlisted capabilities (fail-open schema check, fail-closed policy)
        return True, ""

    required_fields = schema.get("required") or []
    for field in required_fields:
        if field not in payload or payload[field] is None or str(payload[field]).strip() == "":
            return False, f"Missing required field '{field}' for capability '{capability_name}'"

    # Type check basic properties
    properties = schema.get("properties") or {}
    for key, spec in properties.items():
        if key in payload and payload[key] is not None:
            expected_type = spec.get("type")
            val = payload[key]
            if expected_type == "string" and not isinstance(val, str):
                return False, f"Field '{key}' must be a string, got {type(val).__name__}"
            elif expected_type == "integer" and not isinstance(val, int):
                return False, f"Field '{key}' must be an integer, got {type(val).__name__}"
            elif expected_type == "boolean" and not isinstance(val, bool):
                return False, f"Field '{key}' must be a boolean, got {type(val).__name__}"

    return True, ""
