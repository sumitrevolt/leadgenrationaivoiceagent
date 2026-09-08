"""Per-call sticky free-AI routing for Swara (no mid-call model churn).

Select + pin provider/model at call start. Fallback only on timeout/429/error/
invalid/circuit/quality fail. Gemini 2.5 Flash remains stable baseline/fallback.

OmniRoute gateway is OPTIONAL (local/dev). Production voice uses the same free
providers via free_ai with sticky pin — OmniRoute catalog informs route picks
when available; otherwise env defaults apply.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Logical route ids (jobs). Live audio path only uses live-primary/fallback.
ROUTE_LIVE_PRIMARY = "swara-live-primary"
ROUTE_LIVE_FALLBACK = "swara-live-fallback"
ROUTE_INTENT = "swara-intent-classifier"
ROUTE_POSTCALL_QA = "swara-postcall-qa"
ROUTE_TRAINING = "swara-training-analysis"
ROUTE_HEALTH = "swara-router-health"

_MAX_FALLBACKS_PER_CALL = 2


@dataclass
class StickyRoute:
    route_id: str
    provider: str
    model: str
    version: str = "v1"
    fallback_provider: str = "gemini"
    fallback_model: str = "gemini-2.5-flash"
    pinned_at: float = field(default_factory=time.time)
    fallbacks_used: int = 0
    last_error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "provider": self.provider,
            "model": self.model,
            "version": self.version,
            "fallback_provider": self.fallback_provider,
            "fallback_model": self.fallback_model,
            "fallbacks_used": self.fallbacks_used,
            "last_error": self.last_error[:120] if self.last_error else "",
        }


def sticky_enabled() -> bool:
    return (os.environ.get("VOICE_STICKY_ROUTE", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _env_primary() -> tuple[str, str]:
    """Pick live primary from env. Default: gemini/VOICE_LLM_MODEL (current prod)."""
    if (os.environ.get("OMNIROUTE_VOICE", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        try:
            from app.platform.omniroute_client import omniroute_available

            if omniroute_available():
                return "omniroute", "leadgen-free-first"
        except Exception:
            pass
    model = (os.environ.get("VOICE_LLM_MODEL", "") or "").strip() or "gemini-2.5-flash"
    provider = (os.environ.get("VOICE_STICKY_PROVIDER", "") or "").strip().lower()
    if not provider:
        if model.lower().startswith("gemini"):
            provider = "gemini"
        elif "llama" in model.lower() or "groq" in model.lower():
            provider = "groq"
        elif "gpt-oss" in model.lower() or "cerebras" in model.lower():
            provider = "cerebras"
        elif "nvidia" in model.lower() or model.lower().startswith("meta/"):
            provider = "nvidia"
        else:
            provider = "gemini"
    return provider, model


def _env_fallback() -> tuple[str, str]:
    fb_p = (os.environ.get("VOICE_STICKY_FALLBACK_PROVIDER", "") or "").strip().lower() or "gemini"
    fb_m = (os.environ.get("VOICE_STICKY_FALLBACK_MODEL", "") or "").strip() or "gemini-2.5-flash"
    return fb_p, fb_m


def select_at_call_start(*, prefer: str | None = None) -> StickyRoute:
    """Pin route once per call. ``prefer`` may be provider name from benchmark."""
    if prefer:
        p = prefer.strip().lower()
        # Map prefer → default model for that provider.
        defaults = {
            "gemini": (os.environ.get("VOICE_LLM_MODEL") or "gemini-2.5-flash").strip(),
            "groq": (os.environ.get("VOICE_GROQ_MODEL") or "openai/gpt-oss-20b").strip(),
            "cerebras": (os.environ.get("VOICE_CEREBRAS_MODEL") or "gpt-oss-120b").strip(),
            "nvidia": (os.environ.get("NVIDIA_LLM_MODEL") or "meta/llama-3.1-8b-instruct").strip(),
            "mistral": "mistral-small-latest",
        }
        model = defaults.get(p, defaults["gemini"])
        fb_p, fb_m = _env_fallback()
        return StickyRoute(
            route_id=ROUTE_LIVE_PRIMARY,
            provider=p,
            model=model,
            fallback_provider=fb_p,
            fallback_model=fb_m,
        )
    provider, model = _env_primary()
    fb_p, fb_m = _env_fallback()
    return StickyRoute(
        route_id=ROUTE_LIVE_PRIMARY,
        provider=provider,
        model=model,
        fallback_provider=fb_p,
        fallback_model=fb_m,
    )


def logical_routes() -> dict[str, dict[str, str]]:
    """Hierarchy: live vs batch jobs. Batch may use slower/smarter free models."""
    primary, model = _env_primary()
    fb_p, fb_m = _env_fallback()
    return {
        ROUTE_LIVE_PRIMARY: {
            "provider": primary,
            "model": model,
            "job": "live_turn",
            "latency_class": "realtime",
        },
        ROUTE_LIVE_FALLBACK: {
            "provider": fb_p,
            "model": fb_m,
            "job": "live_turn_fallback",
            "latency_class": "realtime",
        },
        ROUTE_INTENT: {
            "provider": "groq",
            "model": (os.environ.get("VOICE_GROQ_MODEL") or "openai/gpt-oss-20b").strip(),
            "job": "intent_classify",
            "latency_class": "fast",
        },
        ROUTE_POSTCALL_QA: {
            "provider": "cerebras",
            "model": (os.environ.get("VOICE_CEREBRAS_MODEL") or "gpt-oss-120b").strip(),
            "job": "postcall_qa",
            "latency_class": "batch",
        },
        ROUTE_TRAINING: {
            "provider": "cerebras",
            "model": (os.environ.get("VOICE_CEREBRAS_MODEL") or "gpt-oss-120b").strip(),
            "job": "training_analysis",
            "latency_class": "batch",
        },
        ROUTE_HEALTH: {
            "provider": "deterministic",
            "model": "router-health-v1",
            "job": "health_monitor",
            "latency_class": "none",
        },
    }


def try_fallback(route: StickyRoute, *, error: str = "") -> StickyRoute | None:
    """Return a new sticky pin on fallback provider, or None if budget exhausted."""
    if route.fallbacks_used >= _MAX_FALLBACKS_PER_CALL:
        logger.warning("[sticky_route] max mid-call fallbacks reached — fail closed")
        return None
    nxt = StickyRoute(
        route_id=ROUTE_LIVE_FALLBACK,
        provider=route.fallback_provider,
        model=route.fallback_model,
        version=route.version,
        fallback_provider=route.fallback_provider,
        fallback_model=route.fallback_model,
        fallbacks_used=route.fallbacks_used + 1,
        last_error=error or "",
    )
    logger.info(
        "[sticky_route] fallback %s/%s -> %s/%s (n=%s)",
        route.provider,
        route.model,
        nxt.provider,
        nxt.model,
        nxt.fallbacks_used,
    )
    return nxt


def routes_unavailable_reason() -> str:
    return "llm_routes_unavailable"


def health_snapshot() -> dict[str, Any]:
    """Deterministic router-health (no secrets)."""
    try:
        from app.voice_agent import free_ai

        avail = getattr(free_ai, "PROVIDERS_AVAILABLE", {}) or {}
        down = []
        try:
            for p in ("groq", "cerebras", "mistral", "gemini", "nvidia"):
                if free_ai._provider_down(p):  # noqa: SLF001 — intentional health probe
                    down.append(p)
        except Exception:
            pass
        return {
            "sticky_enabled": sticky_enabled(),
            "logical_routes": logical_routes(),
            "providers_available": {k: bool(v) for k, v in avail.items()},
            "circuit_open": down,
            "max_fallbacks_per_call": _MAX_FALLBACKS_PER_CALL,
        }
    except Exception as e:
        return {"sticky_enabled": sticky_enabled(), "error": type(e).__name__}
