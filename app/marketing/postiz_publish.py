"""postiz_publish.py — Postiz public-API se client ke connected social accounts
(Facebook Page / Instagram / YouTube / LinkedIn / X etc.) pe video+caption AUTO-post.

Kyun Postiz: Meta/Google direct API approval-blocked hain (CLAUDE.md). Postiz =
client ke APNE connected accounts pe legitimate post karta (SMM-standard, ban-safe
kyunki client ka apna account/token). Self-host ya cloud dono.

GATED: `POSTIZ_API_KEY` (Postiz settings → API). Optional `POSTIZ_API_URL`
(default cloud https://api.postiz.com; self-host = https://<your-host>).
Channel ids: client record `postiz_integrations` (list/csv) ya env
`POSTIZ_INTEGRATIONS` (csv) fallback. Key unset = inert ({"sent": False}).
NEVER raises. Heavy upload = worker/scheduler se hi call karo.
"""

from __future__ import annotations

import os
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _key() -> str:
    return (os.getenv("POSTIZ_API_KEY") or "").strip()


def enabled() -> bool:
    return bool(_key())


def _base() -> str:
    return (os.getenv("POSTIZ_API_URL") or "https://api.postiz.com").rstrip("/")


def _headers() -> dict[str, str]:
    # Postiz public API = raw key in Authorization header (Bearer nahi).
    return {"Authorization": _key()}


def _integration_ids(client: dict[str, Any] | None) -> list[str]:
    """Channel ids — client.postiz_integrations (list ya csv) warna env csv."""
    raw: Any = (client or {}).get("postiz_integrations") if client else None
    if not raw:
        raw = os.getenv("POSTIZ_INTEGRATIONS") or ""
    if isinstance(raw, str):
        ids = [x.strip() for x in raw.split(",")]
    elif isinstance(raw, (list, tuple)):
        ids = [str(x).strip() for x in raw]
    else:
        ids = []
    return [x for x in ids if x][:20]


async def upload_media(path: str) -> dict[str, Any] | None:
    """Local file Postiz pe upload (IG/YT/TikTok verified-URL maangte) → media obj."""
    if not enabled() or not path or not os.path.isfile(path):
        return None
    try:
        import httpx

        with open(path, "rb") as fh:
            files = {"file": (os.path.basename(path), fh, "video/mp4")}
            async with httpx.AsyncClient(timeout=120) as cx:
                r = await cx.post(f"{_base()}/public/v1/upload", headers=_headers(), files=files)
        if r.status_code // 100 == 2:
            j = r.json()
            obj = j[0] if isinstance(j, list) and j else j
            if isinstance(obj, dict) and (obj.get("path") or obj.get("id")):
                return {"id": obj.get("id") or "", "path": obj.get("path") or ""}
        logger.warning(f"[postiz] upload {r.status_code}: {r.text[:140]}")
    except Exception as e:
        logger.warning(f"[postiz] upload failed: {e}")
    return None


async def publish_video(
    client: dict[str, Any], caption: str, video_path: str
) -> dict[str, Any]:
    """Video+caption ko client ke configured Postiz channels pe ABHI post karo.
    Inert agar key/integration-ids missing. Returns {sent, channels, reason}."""
    if not enabled():
        return {"sent": False, "reason": "POSTIZ_API_KEY unset"}
    ids = _integration_ids(client)
    if not ids:
        return {"sent": False, "reason": "koi postiz_integrations id nahi (client/env)"}
    media = await upload_media(video_path)
    if media is None:
        return {"sent": False, "reason": "media upload fail (ya file missing)"}
    value = [{"content": (caption or "").strip()[:2000], "image": [media]}]
    body = {
        "type": "now",
        "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "shortLink": False,
        "tags": [],
        "posts": [{"integration": {"id": i}, "value": value, "settings": {}} for i in ids],
    }
    try:
        import httpx

        async with httpx.AsyncClient(timeout=60) as cx:
            r = await cx.post(f"{_base()}/public/v1/posts", headers=_headers(), json=body)
        ok = r.status_code // 100 == 2
        if not ok:
            logger.warning(f"[postiz] create {r.status_code}: {r.text[:160]}")
        return {
            "sent": ok,
            "channels": ids,
            **({} if ok else {"reason": f"{r.status_code}: {r.text[:160]}"}),
        }
    except Exception as e:
        logger.warning(f"[postiz] publish failed: {e}")
        return {"sent": False, "reason": str(e)[:150]}


__all__ = ["enabled", "upload_media", "publish_video"]
