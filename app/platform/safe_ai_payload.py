"""Safe AI Payload — PII masking + provider safety routing.

Privacy layer that MUST be applied before any external model call.
Masks Indian business PII: names, phones, emails, addresses, GST/PAN,
business IDs, social tokens, API keys, WhatsApp numbers.

Usage:
    from app.platform.safe_ai_payload import mask_customer_data, validate_no_secrets

    safe_payload = mask_customer_data(raw_payload)
    validate_no_secrets(safe_payload)  # raises SafePayloadError if secrets leak
"""

from __future__ import annotations

import json
import re
from typing import Any


class SafePayloadError(ValueError):
    """Payload contains sensitive data that must NOT be sent externally."""


# ---- Patterns for Indian business PII ----

_PHONE_RE = re.compile(
    r"""(?: \+?\s*91[\s.-]* | 91[\s.-]* | 0[\s.-]* )?[6-9](?:\d[\s.-]*){8,11}\d\b""", re.VERBOSE
)

_EMAIL_RE = re.compile(
    r"""(?i)
    [a-z0-9._%+\-]{3,} @ [a-z0-9.\-]+\.[a-z]{2,}
""",
    re.VERBOSE,
)

_GSTIN_RE = re.compile(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
_PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")

# Generic address/landmark patterns (Indian cities + pincodes)
_ADDRESS_HINTS = [
    r"(?i)\b(?:address|pata|location|near|opposite|beside|shop\s*no|flat\s*no|plot\s*no|building|floor|road|lane|colony|nagar|sector|phase|complex|mall|market|chowk)\b.*?(?:\n|$)",
    r"\b[1-9][0-9]{5}\b",  # Indian pincode
]

# API key / token patterns — broader: cover "api key is sk-..." syntax too
_SECRET_PATTERNS = [
    re.compile(r"(?:api[_\-\.\s]*key|password|auth)\s*[:=\s]+\s*[\S]+", re.IGNORECASE),
    re.compile(
        r"(?<![a-zA-Z_])token\s*[:=\s]+\s*[\S]+", re.IGNORECASE
    ),  # not oauth_token/access_token
    re.compile(r"\b(?:sk-[a-zA-Z0-9]{20,}|AIza[0-9A-Za-z\-_]{30,})\b"),  # OpenAI / Google key
    re.compile(r"\b(?:ghp_|gho_|ghu_|ghs_|ghr_)[a-zA-Z0-9]{36,}\b"),  # GitHub PAT
    re.compile(r"\bear\s*[:=]\s*[\S]+", re.IGNORECASE),  # JWT-ish
]

# Social / OAuth token patterns
_OAUTH_PATTERNS = [
    re.compile(r"(?:access_token|refresh_token|oauth_token)\s*[:=\s]+\s*[\S]+", re.IGNORECASE),
    re.compile(r"\bEA[A-Za-z0-9]{30,}\b"),  # Facebook page token
]

# WhatsApp number patterns — cover @wa.gateway, @s.whatsapp.net, etc.
_WA_NUMBER_RE = re.compile(r"\+?\d{10,15}@(?:wa|whatsapp|s\.whatsapp)[a-z.]*", re.IGNORECASE)


# ---- Provider safety tiers ----

# Providers where raw customer data CANNOT be sent
_UNSAFE_PROVIDERS = {
    "glm",
    "qwen",
    "kimi",
    "deepseek",  # Chinese providers
    # Opaque credential-free gateways are development-only and may not receive PII.
    "opencode",
    "duckduckgo",
    "unknown",
    "custom",
}

# Providers where masked data is OK but NEVER secrets
_STRICT_PROVIDERS = {
    "mistral",
    "groq",
    "cerebras",
    "gemini",
    "openrouter",
    "nvidia",
    "sambanova",
    "hermes",
    "grok",
    "codex",
}

# Providers we trust with Claude-level safety (only these can receive unmasked data)
_SAFE_PROVIDERS = {
    "claude",
    "anthropic",
}


def mask_customer_data(payload: dict[str, Any] | str | list[Any] | None) -> Any:
    """Mask PII from any payload structure. Returns same type with PII replaced."""
    if payload is None:
        return None
    if isinstance(payload, str):
        return _mask_string(payload)
    if isinstance(payload, list):
        return [mask_customer_data(item) for item in payload]
    if not isinstance(payload, dict):
        return payload

    _pii_fields = {
        "name": _mask_name,
        "customer_name": _mask_name,
        "business_name": _mask_name,
        "owner_name": _mask_name,
        "contact_name": _mask_name,
        "phone": _mask_phone,
        "mobile": _mask_phone,
        "contact_number": _mask_phone,
        "whatsapp_number": _mask_phone,
        "whatsapp_phone": _mask_phone,
        "email": _mask_email,
        "email_address": _mask_email,
        "customer_email": _mask_email,
        "address": lambda v: "[ADDRESS REDACTED]",
        "business_address": lambda v: "[ADDRESS REDACTED]",
        "shop_address": lambda v: "[ADDRESS REDACTED]",
        "gstin": lambda v: "[GST REDACTED]",
        "gst_number": lambda v: "[GST REDACTED]",
        "gst": lambda v: "[GST REDACTED]",
        "pan": lambda v: "[PAN REDACTED]",
        "pan_number": lambda v: "[PAN REDACTED]",
        "api_key": lambda v: "[SECRET REDACTED]",
        "secret": lambda v: "[SECRET REDACTED]",
        "token": lambda v: "[SECRET REDACTED]",
        "password": lambda v: "[SECRET REDACTED]",
        "key": lambda v: "[SECRET REDACTED]",
    }

    masked: dict[str, Any] = {}
    for key, value in payload.items():
        key_lower = key.lower()
        if key_lower in _pii_fields and isinstance(value, str):
            masked[key] = _pii_fields[key_lower](value)
        else:
            masked[key] = mask_customer_data(value)

    return masked


def _mask_string(text: str) -> str:
    """Apply all PII regex patterns to a string."""
    # WhatsApp numbers first (most specific phone pattern)
    text = _WA_NUMBER_RE.sub("[WHATSAPP REDACTED]", text)
    # Phone numbers
    text = _PHONE_RE.sub("[PHONE REDACTED]", text)
    # Email
    text = _EMAIL_RE.sub("[EMAIL REDACTED]", text)
    # Business IDs
    text = _GSTIN_RE.sub("[GST REDACTED]", text)
    text = _PAN_RE.sub("[PAN REDACTED]", text)
    # OAuth tokens (most specific secret-like pattern)
    for pattern in _OAUTH_PATTERNS:
        text = pattern.sub("[OAUTH REDACTED]", text)
    # API keys / generic secrets
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[SECRET REDACTED]", text)
    return text


def _mask_name(name: str) -> str:
    """Mask a name: keep first initial, redact rest."""
    if not name or len(name) < 2:
        return "[NAME REDACTED]"
    return name[0] + "***"


def _mask_phone(phone: str) -> str:
    """Mask phone: keep last 4 digits."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 4:
        return "[PHONE REDACTED]"
    return "XXXX" + digits[-4:]


def _mask_email(email: str) -> str:
    """Mask email: keep domain, redact username."""
    if "@" not in email or len(email) < 5:
        return "[EMAIL REDACTED]"
    parts = email.rsplit("@", 1)
    return "redacted@" + parts[1]


def validate_no_secrets(payload: dict[str, Any] | str | None) -> None:
    """Raise SafePayloadError if secrets/API keys are detected in payload."""
    if payload is None:
        return
    if isinstance(payload, dict):
        # Check dict keys and values individually
        for key, value in payload.items():
            validate_no_secrets(key)
            validate_no_secrets(value)
        return
    if isinstance(payload, list):
        for item in payload:
            validate_no_secrets(item)
        return
    text = str(payload)
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            raise SafePayloadError("Secret/token detected in payload")
    for pattern in _OAUTH_PATTERNS:
        if pattern.search(text):
            raise SafePayloadError("OAuth token detected in payload")


def block_if_sensitive(payload: dict[str, Any] | str, provider: str) -> None:
    """Raise SafePayloadError if this payload cannot be sent to this provider."""
    provider = (provider or "").strip().lower()
    if provider in _UNSAFE_PROVIDERS:
        # Block ANY customer data going to unsafe providers
        text = json.dumps(payload, default=str) if isinstance(payload, dict) else str(payload)
        if _PHONE_RE.search(text) or _EMAIL_RE.search(text) or _GSTIN_RE.search(text):
            raise SafePayloadError(f"Cannot send customer PII to unsafe provider: {provider}")
    if provider in _STRICT_PROVIDERS:
        # Check dict directly — validate_no_secrets handles fragments better
        validate_no_secrets(payload)
    # SAFE_PROVIDERS (claude/anthropic) — no blocking needed, but secrets should still be redacted
