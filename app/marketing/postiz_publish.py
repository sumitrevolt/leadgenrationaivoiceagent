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


def _vault_cfg() -> dict[str, Any]:
    """Global Postiz config from the encrypted social vault (client '_global').

    Env vars still win (below) — this fallback exists so the key can be set at
    RUNTIME via the admin configure endpoint without a container recreate
    (running containers carry docker-cp drift; recreate = hotfix loss).
    Never raises."""
    try:
        from app.social_engine import vault

        rec = vault.get("_global", "postiz") or {}
        meta = rec.get("meta") or {}
        return {
            "api_key": str(rec.get("token") or "").strip(),
            "api_url": str(meta.get("api_url") or "").strip(),
            "integrations": str(meta.get("integrations") or "").strip(),
        }
    except Exception:
        return {}


def _key() -> str:
    return (os.getenv("POSTIZ_API_KEY") or "").strip() or _vault_cfg().get("api_key", "")


def enabled() -> bool:
    return bool(_key())


def _base() -> str:
    url = (os.getenv("POSTIZ_API_URL") or "").strip() or _vault_cfg().get("api_url", "")
    return (url or "https://api.postiz.com").rstrip("/")


def _headers() -> dict[str, str]:
    # Postiz public API = raw key in Authorization header (Bearer nahi).
    return {"Authorization": _key()}


def _integration_ids(client: dict[str, Any] | None) -> list[str]:
    """Channel ids — client.postiz_integrations (list ya csv) warna env csv,
    warna vault global config."""
    raw: Any = (client or {}).get("postiz_integrations") if client else None
    if not raw:
        raw = os.getenv("POSTIZ_INTEGRATIONS") or _vault_cfg().get("integrations", "")
    if isinstance(raw, str):
        ids = [x.strip() for x in raw.split(",")]
    elif isinstance(raw, (list, tuple)):
        ids = [str(x).strip() for x in raw]
    else:
        ids = []
    return [x for x in ids if x][:20]


# Platforms that reject text-only posts (Postiz "Should have at least one
# media" error) — media-required, unlike FB/X/LinkedIn which accept text.
_MEDIA_REQUIRED_PLATFORMS = {"instagram", "tiktok", "pinterest", "youtube"}


async def _fetch_integration_platforms() -> dict[str, str]:
    """id -> identifier (e.g. "instagram") map from Postiz's own integrations
    list. Best-effort, never raises — empty dict on any failure (caller then
    sends to all ids unfiltered, same as before this existed)."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=15) as cx:
            r = await cx.get(f"{_base()}/public/v1/integrations", headers=_headers())
        if r.status_code // 100 == 2:
            data = r.json()
            if isinstance(data, list):
                return {
                    str(it.get("id")): str(it.get("identifier") or "").lower()
                    for it in data
                    if isinstance(it, dict) and it.get("id")
                }
    except Exception as e:
        logger.debug(f"[postiz] fetch integrations skip: {e}")
    return {}


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
    """Video+caption (ya text-only, video_path="" ho to) ko client ke configured
    Postiz channels pe ABHI post karo. Inert agar key/integration-ids missing.
    Returns {sent, channels, post_id, post_ids, post_url, reason}.  Postiz's
    create-post API returns one ``postId`` per integration; preserving those
    ids is mandatory launch evidence (``sent=True`` alone only proves that the
    request was accepted, not which provider records were created).

    2026-07-04 fix: pehle video_path na hone pe hard-fail karta tha ("media
    upload fail") — isliye daily auto_content captions (jo text-only hote,
    koi video file nahi) kabhi publish nahi hote the, sirf video_ad_cycle ke
    actual rendered videos hi jaate. Ab video_path khali ho to text-only post
    (Postiz API "image" field optional hai) bhejta hai."""
    if not enabled():
        return {"sent": False, "reason": "POSTIZ_API_KEY unset"}
    ids = _integration_ids(client)
    if not ids:
        return {"sent": False, "reason": "koi postiz_integrations id nahi (client/env)"}
    # Platform map (id -> identifier e.g. "youtube") — needed both to skip
    # media-required platforms on text-only posts AND to build YouTube's own
    # required settings below. Best-effort; empty dict on failure (fine, just
    # means no per-platform special-casing happens, same as before either fix
    # existed).
    platform_map = await _fetch_integration_platforms()
    media_list: list[dict[str, Any]] = []
    if video_path:
        media = await upload_media(video_path)
        if media is None:
            return {"sent": False, "reason": "media upload fail (ya file missing)"}
        media_list = [media]
    else:
        # 2026-07-04 fix: Postiz batches all ids into ONE API call — if any
        # single platform in that batch requires media (Instagram/TikTok/
        # Pinterest/YouTube all reject text-only posts with "Should have at
        # least one media"), the WHOLE call failed and NOTHING published,
        # even platforms like Facebook/X that would've succeeded on their
        # own. Drop media-required platforms up front for text-only posts
        # instead of letting one bad apple block everyone else.
        if platform_map:
            skipped = [i for i in ids if platform_map.get(i) in _MEDIA_REQUIRED_PLATFORMS]
            ids = [i for i in ids if i not in skipped]
            if skipped:
                logger.info(f"[postiz] text-only post: skipping media-required channels {skipped}")
        if not ids:
            return {"sent": False, "reason": "sirf media-required channels the (text-only post)"}
    caption_clean = (caption or "").strip()
    value = [{"content": caption_clean[:2000], "image": media_list}]
    # 2026-07-04 fix: Postiz public API rejects posts without settings.post_type
    # ("should not be null or undefined") — every platform needs this. X also
    # requires settings.who_can_reply_post; harmless extra field on other
    # platforms (ignored), so send both unconditionally rather than branching
    # per-platform (keeps this additive and simple).
    base_settings = {"post_type": "post", "who_can_reply_post": "everyone"}
    # 2026-07-04 fix: YouTube's own settings DTO additionally REQUIRES
    # "title" (2-100 chars) and "type" (public/private/unlisted) — missing
    # either 400s with "settings.title should not be null or undefined".
    # Derive title from the caption's first line (YouTube video titles are
    # short) rather than making callers pass a separate title everywhere.
    youtube_title = (caption_clean.splitlines()[0] if caption_clean else "").strip()[:100]
    if len(youtube_title) < 2:
        youtube_title = "LeadsGenAI Update"

    def _settings_for(integration_id: str) -> dict[str, Any]:
        # Current Postiz public API requires ``__type`` to identify the
        # provider-specific settings schema.  Keep the older fields too: the
        # self-hosted image validates them for X/Instagram/YouTube.
        provider_type = platform_map.get(integration_id) or ""
        typed = {**base_settings, **({"__type": provider_type} if provider_type else {})}
        if platform_map.get(integration_id) == "youtube":
            return {**typed, "title": youtube_title, "type": "public"}
        return typed

    body = {
        "type": "now",
        "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "shortLink": False,
        "tags": [],
        "posts": [
            {"integration": {"id": i}, "value": value, "settings": _settings_for(i)}
            for i in ids
        ],
    }
    try:
        import httpx

        async with httpx.AsyncClient(timeout=60) as cx:
            r = await cx.post(f"{_base()}/public/v1/posts", headers=_headers(), json=body)
        ok = r.status_code // 100 == 2
        if not ok:
            logger.warning(f"[postiz] create {r.status_code}: {r.text[:160]}")
        payload: Any = None
        if ok:
            try:
                payload = r.json()
            except Exception:
                payload = None
        entries = payload if isinstance(payload, list) else []
        if isinstance(payload, dict):
            nested = payload.get("posts")
            entries = nested if isinstance(nested, list) else [payload]
        post_ids = [
            str(item.get("postId") or item.get("post_id") or item.get("id") or "")
            for item in entries
            if isinstance(item, dict)
            and (item.get("postId") or item.get("post_id") or item.get("id"))
        ]
        post_urls = [
            str(item.get("releaseURL") or item.get("postUrl") or item.get("url") or "")
            for item in entries
            if isinstance(item, dict)
            and (item.get("releaseURL") or item.get("postUrl") or item.get("url"))
        ]
        if ok and not post_ids:
            logger.warning("[postiz] create succeeded but response had no postId evidence")
        return {
            "sent": ok,
            "channels": ids,
            "post_id": post_ids[0] if post_ids else "",
            "post_ids": post_ids,
            "post_url": post_urls[0] if post_urls else "",
            **({} if ok else {"reason": f"{r.status_code}: {r.text[:160]}"}),
        }
    except Exception as e:
        logger.warning(f"[postiz] publish failed: {e}")
        return {"sent": False, "reason": str(e)[:150]}


def effective_integration_ids(client: dict[str, Any] | None = None) -> list[str]:
<<<<<<< HEAD
    """Return the channel ids the real publish path would resolve.

    Resolution order deliberately matches ``_integration_ids``: client record,
    then ``POSTIZ_INTEGRATIONS``, then vault metadata.  Keeping this as a public,
    never-raise diagnostic prevents readiness surfaces from reporting vault-only
    state while publishing is actually configured through the environment.
    """
    try:
        return _integration_ids(client)
    except Exception:  # pragma: no cover - diagnostic must never break admin UI
=======
    """Channel ids `publish_video()` would ACTUALLY use, in its real precedence
    order (client record → env `POSTIZ_INTEGRATIONS` → vault meta).

    Public wrapper so status/diagnostic surfaces report the EFFECTIVE config
    instead of reading ONE source and guessing. `/social/postiz/status` used to
    count only the vault field and reported `integrations_count: 0` while
    publishing was fully wired via env — a status surface that lies sends
    operators chasing a bug that does not exist (ADR-095/096/098 class).
    Never raises."""
    try:
        return _integration_ids(client)
    except Exception:  # pragma: no cover
>>>>>>> 4d3f030 (fix: reconcile workspace + resolve conflicts + finalize ADR-100/103 fixes)
        return []


def integrations_source(client: dict[str, Any] | None = None) -> str:
<<<<<<< HEAD
    """Return ``client`` / ``env`` / ``vault`` / ``none`` for effective ids."""
=======
    """Which source `effective_integration_ids()` resolved from — "client" /
    "env" / "vault" / "none". Operator triage: tells you WHERE to change the
    value, which matters because env silently wins over vault. Never raises."""
>>>>>>> 4d3f030 (fix: reconcile workspace + resolve conflicts + finalize ADR-100/103 fixes)
    try:
        if (client or {}).get("postiz_integrations"):
            return "client"
        if (os.getenv("POSTIZ_INTEGRATIONS") or "").strip():
            return "env"
        if _vault_cfg().get("integrations", ""):
            return "vault"
<<<<<<< HEAD
    except Exception:  # pragma: no cover - diagnostic must never break admin UI
=======
    except Exception:  # pragma: no cover
>>>>>>> 4d3f030 (fix: reconcile workspace + resolve conflicts + finalize ADR-100/103 fixes)
        pass
    return "none"


def api_url() -> str:
<<<<<<< HEAD
    """Return the effective Postiz API base URL without raising."""
=======
    """Effective Postiz base URL (env → vault → cloud default). Never raises."""
>>>>>>> 4d3f030 (fix: reconcile workspace + resolve conflicts + finalize ADR-100/103 fixes)
    try:
        return _base()
    except Exception:  # pragma: no cover
        return ""


__all__ = [
    "enabled",
    "upload_media",
    "publish_video",
    "effective_integration_ids",
    "integrations_source",
    "api_url",
]
