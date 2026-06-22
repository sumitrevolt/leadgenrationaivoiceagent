"""LeadGen AI native social-posting engine — apna stack (Redis/Celery queue + Postgres
persistence + worker drain + per-platform provider adapters + Fernet token vault).

Postiz-jaisi external dependency ki jagah khud ka engine. GATED `SOCIAL_ENGINE` (default
OFF — engine inert, video_ad_cycle current telegram+postiz inline path use karta).

Public API:
  enqueue_publish(client_id, caption, media_path/url, platforms, account_refs) -> [job_ids]
  process_queue(limit) -> drain (scheduler/worker)
  enabled() ; registry() ; vault (token store) ; store (job queue)
"""

from __future__ import annotations

from . import store, vault
from .base import PLATFORMS, PublishRequest, PublishResult, SocialProvider
from .engine import enabled, enqueue_publish, process_queue, registry

__all__ = [
    "enqueue_publish",
    "process_queue",
    "enabled",
    "registry",
    "vault",
    "store",
    "PublishRequest",
    "PublishResult",
    "SocialProvider",
    "PLATFORMS",
]
