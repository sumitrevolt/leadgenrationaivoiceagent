"""ADR-104 — niche-catalog readiness via BARE, metadata-only Qdrant access.

WHY THIS MODULE EXISTS (measured, not assumed — ADR-104 addendum #6/#7):
`_get_qdrant_client()` calls `_get_qdrant_embedder()` BEFORE it touches Qdrant, so
it force-loads FastEmbed. Measured in production: bare `QdrantClient` ctor = **13.6ms**
vs `_get_qdrant_client()` = **>239s (never returned)**. A `count()` needs no embeddings
at all. So readiness MUST use a bare client — routing it through `_get_qdrant_client()`
would drag the whole 39-niche embed path onto the live voice turn, i.e. recreate the
exact incident this module exists to prevent.

Measured warm latency of the readiness count: **~6-8ms median** (voice budget ~1500ms).
First call costs ~0.5-1.5s (connection warm-up) -> keep the client a process singleton
and warm it off the spoken hot path.

READINESS FILTER (proven — addendum #7):
    namespace == <niche>  AND  source == "niche:<niche>"
Namespace-only counting FALSE-READIES: `insurance` ns-only=3970 vs ns+source=1674,
because a namespace holds points from other sources too.

HARD RULES for this module:
  * never import/call `_get_qdrant_client`, `_get_qdrant_embedder`, `_get_kb`,
    `bootstrap_default_kb`
  * never create/delete/migrate a collection, never dimension-check
  * never load vectors or payload text into process memory
  * log only niche key / count / duration / error class — never URL, api key, text
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Readiness states (ADR-104). Dispatch != ready. Lock != ready. Seed-return != ready.
STATE_READY = "ready"
STATE_NOT_READY = "not_ready"
STATE_UNSUPPORTED = "unsupported_niche"
STATE_ERROR = "readiness_error"

_COUNT_TIMEOUT_S = float(os.getenv("KB_READINESS_TIMEOUT_S", "2.0") or 2.0)

_CLIENT: Any = None
_CLIENT_FAILED = False


@dataclass(frozen=True)
class NicheReadiness:
    """Safe, redacted readiness result. No document text / payload / credentials."""

    niche: str
    supported: bool
    state: str
    count: int
    duration_ms: float
    error_class: str | None = None

    @property
    def is_ready(self) -> bool:
        return self.state == STATE_READY


def catalog_niches() -> set[str]:
    """Authoritative catalog keys (39). Import is cheap and loads no models."""
    try:
        from app.niches import NICHES

        return set((NICHES or {}).keys())
    except Exception as e:  # pragma: no cover
        logger.debug("[kb-readiness] NICHES import failed: %s", type(e).__name__)
        return set()


def is_supported_niche(niche: str) -> bool:
    """`real_estate` is a Voice QA target but NOT a catalog key -> unsupported.

    It must degrade, never raise, never seed, never enqueue an impossible refresh.
    """
    return bool(niche) and niche in catalog_niches()


def _bare_client():
    """Process-singleton BARE QdrantClient. NEVER touches the embedder.

    Returns None (never raises) if Qdrant is unconfigured/unreachable, so the voice
    path can degrade instead of breaking.
    """
    global _CLIENT, _CLIENT_FAILED
    if _CLIENT is not None:
        return _CLIENT
    if _CLIENT_FAILED:
        return None
    try:
        # NOTE: only URL/const helpers — these do NOT load the embedder.
        from app.voice_agent.knowledge_base import _get_qdrant_url

        url = _get_qdrant_url()
        if not url:
            _CLIENT_FAILED = True
            return None
        from qdrant_client import QdrantClient

        _CLIENT = QdrantClient(
            url=url,
            api_key=os.getenv("QDRANT_API_KEY") or None,
            timeout=_COUNT_TIMEOUT_S,
        )
        return _CLIENT
    except Exception as e:
        _CLIENT_FAILED = True
        logger.warning("[kb-readiness] bare client unavailable: %s", type(e).__name__)
        return None


def reset_client_cache() -> None:
    """Test/ops hook — drop the singleton so the next call reconstructs it."""
    global _CLIENT, _CLIENT_FAILED
    _CLIENT = None
    _CLIENT_FAILED = False


def _niche_filter(niche: str):
    from qdrant_client import models as qm

    return qm.Filter(
        must=[
            qm.FieldCondition(key="namespace", match=qm.MatchValue(value=niche)),
            qm.FieldCondition(key="source", match=qm.MatchValue(value=f"niche:{niche}")),
        ]
    )


def count_niche_catalog_points(niche: str, client: Any | None = None) -> NicheReadiness:
    """Authoritative cross-worker evidence: does THIS niche's catalog content exist?

    `client` is injectable for tests (must expose `.count(collection_name, count_filter, exact)`).
    Never raises. ~6-8ms warm.
    """
    t0 = time.monotonic()

    def _ms() -> float:
        return round((time.monotonic() - t0) * 1000, 2)

    if not is_supported_niche(niche):
        return NicheReadiness(niche, False, STATE_UNSUPPORTED, 0, _ms())

    c = client if client is not None else _bare_client()
    if c is None:
        return NicheReadiness(niche, True, STATE_ERROR, 0, _ms(), "NoClient")

    try:
        from app.voice_agent.knowledge_base import _QDRANT_COLLECTION

        res = c.count(
            collection_name=_QDRANT_COLLECTION,
            count_filter=_niche_filter(niche),
            exact=True,
        )
        n = int(getattr(res, "count", 0) or 0)
        state = STATE_READY if n > 0 else STATE_NOT_READY
        return NicheReadiness(niche, True, state, n, _ms())
    except Exception as e:
        # error_class only — messages can carry infra detail.
        return NicheReadiness(niche, True, STATE_ERROR, 0, _ms(), type(e).__name__)


def is_niche_ready(niche: str, client: Any | None = None) -> bool:
    """Convenience gate. Unsupported / cold / error all => not ready (fail-safe)."""
    return count_niche_catalog_points(niche, client=client).is_ready


__all__ = [
    "NicheReadiness",
    "count_niche_catalog_points",
    "is_niche_ready",
    "is_supported_niche",
    "catalog_niches",
    "reset_client_cache",
    "STATE_READY",
    "STATE_NOT_READY",
    "STATE_UNSUPPORTED",
    "STATE_ERROR",
]
