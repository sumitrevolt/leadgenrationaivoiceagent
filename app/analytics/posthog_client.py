"""posthog_client.py — server-side PostHog capture + feature-flags (G3). GATED.

KYU: app/analytics/dashboard.py server-side call/lead funnels deta. Web product-
analytics (events, feature-flags, A/B) PostHog Cloud free-tier se aata. Ye thin,
never-raise wrapper hai — server-side events (signup, payment, qualified-lead) +
backend feature-flag checks ke liye.

OFF by default: `POSTHOG_API_KEY` set nahi -> har call silent no-op (zero overhead).
Self-host MAT karo (ClickHouse heavy) — PostHog Cloud free (1M events/mo) use karo.

ENV:
  POSTHOG_API_KEY=phc_xxx            # project API key (PostHog -> Project Settings)
  POSTHOG_HOST=https://us.i.posthog.com   # ya eu.i.posthog.com / reverse-proxy

Use:
  from app.analytics import posthog_client as ph
  ph.capture(distinct_id=client_id, event="lead_qualified", properties={"niche": n})
  if ph.feature_enabled("new_pricing_page", distinct_id=client_id):
      ...
"""

from __future__ import annotations

import logging
from typing import Any

from app.platform import posthog_config

logger = logging.getLogger(__name__)

_client: Any = None
_ready: bool = False


def _key() -> str:
    return posthog_config.get_api_key()


def _host() -> str:
    return posthog_config.get_host()


def enabled() -> bool:
    return bool(_key())


def _get() -> Any:
    """Lazy PostHog client (cached). Key/lib missing -> None (no-op)."""
    global _client, _ready
    if _ready:
        return _client
    _ready = True
    if not _key():
        _client = None
        return None
    try:
        from posthog import Posthog  # pip install posthog

        _client = Posthog(project_api_key=_key(), host=_host(), timeout=3, max_retries=1)
    except Exception as e:  # lib missing / init fail -> graceful no-op
        logger.info("[posthog] disabled (%s)", e)
        _client = None
    return _client


def capture(distinct_id: str, event: str, properties: dict | None = None) -> None:
    c = _get()
    if c is None:
        return
    try:
        c.capture(distinct_id=str(distinct_id), event=event, properties=properties or {})
    except Exception:
        pass


def feature_enabled(flag: str, distinct_id: str, default: bool = False) -> bool:
    """Backend feature-flag / A/B gate. Key/flag missing -> `default`."""
    c = _get()
    if c is None:
        return default
    try:
        r = c.feature_enabled(flag, str(distinct_id))
        return default if r is None else bool(r)
    except Exception:
        return default


def flush() -> None:
    c = _get()
    if c is None:
        return
    try:
        c.flush()
    except Exception:
        pass


__all__ = ["enabled", "capture", "feature_enabled", "flush"]
