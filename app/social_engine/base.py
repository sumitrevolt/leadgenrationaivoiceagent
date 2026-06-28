"""social_engine.base — provider-agnostic interfaces for the native social-posting engine.

SocialProvider = ek platform adapter (telegram/meta(fb+ig)/gbp/linkedin/x/youtube/postiz).
PublishRequest  = ek post ka intent (client + media + caption + target account).
PublishResult   = outcome (ok, platform post-id/url, error).

Rules: har provider gated/inert until creds (NEVER raises). Engine registry se dispatch karta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Supported platforms (registry keys). "meta" ek hi adapter FB Page + Instagram dono.
PLATFORMS = (
    # telegram REMOVED 2026-06-28 (ban-risk; not advertised, not a delivery channel)
    "facebook",
    "instagram",
    "gbp",
    "linkedin",
    "x",
    "youtube",
    "postiz",
)


@dataclass
class PublishRequest:
    client_id: str
    caption: str = ""
    media_path: str = ""  # local file (reel mp4 / image)
    media_url: str = ""  # public URL (Meta/LinkedIn fetch karte — host first)
    media_type: str = "video"  # video | image | text
    platform: str = ""  # target platform key
    account_ref: str = ""  # page-id / ig-user-id / location / org-urn / channel-id
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class PublishResult:
    ok: bool
    platform: str = ""
    post_id: str = ""
    url: str = ""
    error: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class SocialProvider:
    """Base adapter. Subclass har platform ke liye. NEVER raises — error PublishResult."""

    name: str = "base"
    needs_public_url: bool = False  # media public URL chahiye? (Meta/LinkedIn = True)

    def configured(self, account: dict[str, Any] | None = None) -> bool:
        """Token/creds present (env ya per-client account/vault)? Inert if False."""
        return False

    async def publish(self, req: PublishRequest, account: dict[str, Any]) -> PublishResult:
        return PublishResult(ok=False, platform=self.name, error="not implemented")

    def capabilities(self) -> dict[str, Any]:
        return {"name": self.name, "needs_public_url": self.needs_public_url}
