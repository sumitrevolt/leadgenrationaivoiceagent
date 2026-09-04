"""Postiz integration client and publishing adapter."""

from __future__ import annotations

import asyncio
from typing import Any

from app.integrations.base import BaseIntegrationClient
from app.marketing.postiz_publish import (
    effective_integration_ids,
    enabled,
    integrations_source,
    plan_publish_channels,
)
from app.marketing.postiz_publish import (
    publish_video as _async_publish_video,
)


class PublishResult(dict):
    """A dictionary result that is also awaitable if caller awaits it."""

    def __await__(self):
        async def _coro():
            return self

        return _coro().__await__()


class PostizClient(BaseIntegrationClient):
    """Client for interacting with Postiz social media scheduling."""

    def auto_post(self) -> None:
        content = self._fetch_content()
        post = self._generate_post(content)
        self._publish_post(post)

    def queue_creative(
        self,
        media_dir: str,
        title: str,
        caption: str,
        aspects: list[str] | None = None,
        **kwargs: Any,
    ) -> str | None:
        """Queue creative asset in Postiz or return None if not configured."""
        return None

    def _fetch_content(self) -> Any:
        return None

    def _generate_post(self, content: Any) -> Any:
        return None

    def _publish_post(self, post: Any) -> Any:
        return None


def publish_video(
    client: dict[str, Any],
    caption: str,
    video_path: str = "",
    *,
    video_file: Any | None = None,
    filename: str = "video.mp4",
    idempotency_key: str | None = None,
) -> Any:
    """Publish video to Postiz.

    Supports both `await publish_video(...)` (in running event loop)
    and synchronous `publish_video(...)` (in Celery worker threads).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        return _async_publish_video(
            client=client,
            caption=caption,
            video_path=video_path,
            video_file=video_file,
            filename=filename,
            idempotency_key=idempotency_key,
        )

    res = asyncio.run(
        _async_publish_video(
            client=client,
            caption=caption,
            video_path=video_path,
            video_file=video_file,
            filename=filename,
            idempotency_key=idempotency_key,
        )
    )
    return PublishResult(res)


__all__ = [
    "BaseIntegrationClient",
    "PostizClient",
    "PublishResult",
    "effective_integration_ids",
    "enabled",
    "integrations_source",
    "plan_publish_channels",
    "publish_video",
]
