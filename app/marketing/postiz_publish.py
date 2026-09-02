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


_OWN_BRAND_IDS = frozenset({"leadgenai-self", "leadgen-ai"})


def _is_own_brand(client: dict[str, Any] | None) -> bool:
    """True when publish context is LeadGen own-brand (or admin/global, no client).

    Customer records MUST NOT inherit ``POSTIZ_INTEGRATIONS`` / vault globals —
    that posted customer copy onto corporate FB/IG (audit 2026-07-17).

    NOTE: an empty/falsy client legitimately means "own-brand, no client
    context" at this boundary (see tests/test_postiz_config.py publish_video
    calls). Callers that resolved a REAL customer id and got nothing back must
    therefore refuse BEFORE reaching here — see
    ``video_ad_cycle._resolve_publish_client``.
    """
    if not client:
        return True
    cid = str(client.get("id") or "").strip().lower()
    if cid in _OWN_BRAND_IDS:
        return True
    name = str(client.get("business_name") or "").strip().lower()
    niche = str(client.get("niche") or "").strip().lower()
    return niche == "ai_marketing" or name in ("leadgen ai", "leadsgenai", "leadsgen ai")


def _parse_integration_ids(raw: Any) -> list[str]:
    """Parse CSV/list integration ids — empty rejected, order preserved, deduped."""
    if isinstance(raw, str):
        ids = [x.strip() for x in raw.split(",")]
    elif isinstance(raw, list | tuple):
        ids = [str(x).strip() for x in raw]
    else:
        ids = []
    out: list[str] = []
    seen: set[str] = set()
    for x in ids:
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
        if len(out) >= 20:
            break
    return out


def _social_config_integrations(client_id: str) -> list[str]:
    """Wizard writes postiz_integrations to social_config.jsonl — merge for publish."""
    cid = str(client_id or "").strip()
    if not cid:
        return []
    try:
        from app.social_engine import client_config

        cfg = client_config.get(cid) or {}
        return _parse_integration_ids(cfg.get("postiz_integrations"))
    except Exception:
        return []


def _integration_ids(client: dict[str, Any] | None) -> list[str]:
    """Channel ids for a publish.

    Precedence: client record → social_config wizard → (own-brand/global only)
    env ``POSTIZ_INTEGRATIONS`` → vault. Customers without their own IDs get [].
    """
    raw: Any = (client or {}).get("postiz_integrations") if client else None
    ids = _parse_integration_ids(raw)
    if not ids and client:
        ids = _social_config_integrations(str(client.get("id") or ""))
    if ids:
        return ids
    if _is_own_brand(client):
        raw = os.getenv("POSTIZ_INTEGRATIONS") or _vault_cfg().get("integrations", "")
        return _parse_integration_ids(raw)
    return []


# Platforms that reject text-only posts (Postiz "Should have at least one
# media" error) — media-required, unlike FB/X/LinkedIn which accept text.
_MEDIA_REQUIRED_PLATFORMS = frozenset({"instagram", "tiktok", "pinterest", "youtube"})

# Platforms that 400 the WHOLE multi-channel create-post batch unless
# provider-specific settings are present. Skip them unless configured —
# one bad channel must not block Facebook/IG/X (Stage 2 canary lesson).
_BOARD_REQUIRED_PLATFORMS = frozenset({"pinterest"})

# Hard ceiling for POSTIZ_PUBLISH_MAX_CHANNELS (matches parse cap).
_PUBLISH_MAX_CHANNELS_CEILING = 20

# Per-platform caption character limits (X is the tight one). Conservative
# values; a platform-map miss falls back to the global 2000 cap (old behaviour).
_CAPTION_LIMITS: dict[str, int] = {
    "x": 280,
    "twitter": 280,
    "instagram": 2200,
    "linkedin": 3000,
    "facebook": 5000,
    "youtube": 5000,
    "pinterest": 500,
}
_DEFAULT_CAPTION_LIMIT = 2000


def _caption_limit(provider_type: str) -> int:
    """Max caption chars for a Postiz provider identifier (best-effort)."""
    return _CAPTION_LIMITS.get((provider_type or "").strip().lower(), _DEFAULT_CAPTION_LIMIT)


def _pinterest_board() -> str:
    """Optional Postiz Pinterest board id/name. Unset/whitespace = skip Pinterest."""
    return (os.getenv("POSTIZ_PINTEREST_BOARD") or "").strip()


def _skip_platforms() -> set[str]:
    """Operator skip-list (e.g. ``POSTIZ_SKIP_PLATFORMS=x`` when X API credits=0).

    CSV of Postiz ``identifier`` values (facebook/instagram/x/youtube/…).
    Empty = skip none. Never raises.
    """
    raw = (os.getenv("POSTIZ_SKIP_PLATFORMS") or "").strip()
    if not raw:
        return set()
    return {x.strip().lower() for x in raw.split(",") if x.strip()}


def _publish_max_channels() -> int | None:
    """Channel cap for one create-post call.

    Semantics:
    - unset → ``None`` (no cap; legacy multi-channel fan-out)
    - ``0`` / negative → ``0`` (zero targets; publish blocked, no API call)
    - invalid string → ``None`` with warning (preserve prior uncapped behavior)
    - ``N`` > ceiling → clamped to ``_PUBLISH_MAX_CHANNELS_CEILING``
    """
    raw = (os.getenv("POSTIZ_PUBLISH_MAX_CHANNELS") or "").strip()
    if not raw:
        return None
    try:
        n = int(raw)
    except ValueError:
        logger.warning("[postiz] POSTIZ_PUBLISH_MAX_CHANNELS invalid; treating as unset (uncapped)")
        return None
    if n <= 0:
        return 0
    if n > _PUBLISH_MAX_CHANNELS_CEILING:
        logger.warning(
            f"[postiz] POSTIZ_PUBLISH_MAX_CHANNELS={n} clamped to {_PUBLISH_MAX_CHANNELS_CEILING}"
        )
        return _PUBLISH_MAX_CHANNELS_CEILING
    return n


def select_publish_channels(
    ids: list[str],
    platform_map: dict[str, str],
    *,
    has_media: bool,
    board: str | None = None,
    max_channels: int | None = None,
) -> dict[str, Any]:
    """Deterministic channel filter before Postiz create-post.

    Ordering = caller list order (config CSV / client list), after dedupe.
    Never raises. Returns ``{ok, channels, skipped, reason}``.
    """
    board_val = (board if board is not None else _pinterest_board()).strip()
    max_ch = max_channels if max_channels is not None else _publish_max_channels()
    raw_ids = _parse_integration_ids(ids)
    skipped: list[dict[str, str]] = []
    eligible: list[str] = []

    skip_plats = _skip_platforms()
    for iid in raw_ids:
        plat = (platform_map.get(iid) or "").lower() if platform_map else ""
        if plat and plat in skip_plats:
            skipped.append({"id": iid, "platform": plat, "reason": "POSTIZ_SKIP_PLATFORMS"})
            continue
        if not has_media and plat in _MEDIA_REQUIRED_PLATFORMS:
            skipped.append({"id": iid, "platform": plat or "unknown", "reason": "media_required"})
            continue
        if plat in _BOARD_REQUIRED_PLATFORMS and not board_val:
            skipped.append({"id": iid, "platform": plat, "reason": "POSTIZ_PINTEREST_BOARD_unset"})
            continue
        eligible.append(iid)

    if max_ch is not None and max_ch <= 0:
        return {
            "ok": False,
            "channels": [],
            "skipped": skipped
            + [
                {
                    "id": i,
                    "platform": (platform_map.get(i) or "unknown"),
                    "reason": "POSTIZ_PUBLISH_MAX_CHANNELS_zero",
                }
                for i in eligible
            ],
            "reason": "POSTIZ_PUBLISH_MAX_CHANNELS=0 (publish blocked)",
        }

    selected = eligible
    if max_ch is not None and len(selected) > max_ch:
        for i in selected[max_ch:]:
            skipped.append(
                {
                    "id": i,
                    "platform": (platform_map.get(i) or "unknown"),
                    "reason": "max_channels_cap",
                }
            )
        selected = selected[:max_ch]
        logger.info(
            f"[postiz] POSTIZ_PUBLISH_MAX_CHANNELS={max_ch}: selected={len(selected)} skipped_cap={len(eligible) - max_ch}"
        )

    if not selected:
        reason = "no_eligible_channels"
        if skipped and all(s.get("reason") == "media_required" for s in skipped):
            reason = "sirf media-required channels the (text-only post)"
        elif skipped and all(s.get("reason") == "POSTIZ_PINTEREST_BOARD_unset" for s in skipped):
            reason = "sirf Board-required channels the (POSTIZ_PINTEREST_BOARD unset)"
        elif any(s.get("reason") == "POSTIZ_PUBLISH_MAX_CHANNELS_zero" for s in skipped):
            reason = "POSTIZ_PUBLISH_MAX_CHANNELS=0 (publish blocked)"
        return {"ok": False, "channels": [], "skipped": skipped, "reason": reason}

    board_skips = [s for s in skipped if s.get("reason") == "POSTIZ_PINTEREST_BOARD_unset"]
    if board_skips:
        logger.info(
            f"[postiz] skipping Board-required channels count={len(board_skips)} reason=POSTIZ_PINTEREST_BOARD_unset"
        )

    return {"ok": True, "channels": selected, "skipped": skipped, "reason": "ok"}


def plan_publish_channels(
    client: dict[str, Any] | None = None,
    *,
    has_media: bool = True,
    platform_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Read-only channel plan (no Postiz upload/create). Safe for prod dry-run."""
    ids = _integration_ids(client)
    return {
        "configured": ids,
        "source": integrations_source(client),
        "selection": select_publish_channels(ids, platform_map or {}, has_media=has_media),
        "pinterest_board_set": bool(_pinterest_board()),
        "max_channels": _publish_max_channels(),
    }


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


async def live_integrations_summary() -> dict[str, Any]:
    """Best-effort Postiz channel list for admin honesty (refresh flags, ids).

    Never raises. Empty when key unset or API unreachable.
    """
    if not enabled():
        return {"ok": False, "channels": [], "youtube_refresh_needed": False}
    try:
        import httpx

        async with httpx.AsyncClient(timeout=15) as cx:
            r = await cx.get(f"{_base()}/public/v1/integrations", headers=_headers())
        if r.status_code // 100 != 2:
            return {"ok": False, "channels": [], "youtube_refresh_needed": False}
        data = r.json()
        if not isinstance(data, list):
            return {"ok": False, "channels": [], "youtube_refresh_needed": False}
        channels: list[dict[str, Any]] = []
        youtube_refresh = False
        for it in data:
            if not isinstance(it, dict) or not it.get("id"):
                continue
            ident = str(it.get("identifier") or it.get("providerIdentifier") or "").lower()
            refresh = bool(it.get("refreshNeeded") or it.get("refresh_needed"))
            if ident == "youtube" and refresh:
                youtube_refresh = True
            channels.append(
                {
                    "id": str(it.get("id")),
                    "identifier": ident,
                    "refresh_needed": refresh,
                    "name": str(it.get("name") or it.get("providerIdentifier") or "")[:80],
                }
            )
        return {"ok": True, "channels": channels[:30], "youtube_refresh_needed": youtube_refresh}
    except Exception as e:
        logger.debug(f"[postiz] live_integrations_summary skip: {e}")
        return {"ok": False, "channels": [], "youtube_refresh_needed": False}


async def upload_media(
    path: str = "",
    *,
    fileobj: Any | None = None,
    filename: str = "video.mp4",
) -> dict[str, Any] | None:
    """Upload bytes to Postiz.

    Prefer an already-open ``fileobj`` (Stage 3C verified descriptor). Path-based
    open remains for legacy callers (text/image flows) but the video-ad publish
    path MUST pass ``fileobj`` so the snapshot is never re-opened.
    """
    if not enabled():
        return None
    fh = fileobj
    owns_fh = False
    try:
        import httpx

        if fh is None:
            if not path or not os.path.isfile(path):
                return None
            fh = open(path, "rb")
            owns_fh = True
            name = os.path.basename(path) or filename
        else:
            name = filename or (os.path.basename(path) if path else "video.mp4")
            try:
                fh.seek(0)
            except (OSError, AttributeError):
                pass
        files = {"file": (name, fh, "video/mp4")}
        async with httpx.AsyncClient(timeout=120) as cx:
            r = await cx.post(f"{_base()}/public/v1/upload", headers=_headers(), files=files)
        if r.status_code // 100 == 2:
            j = r.json()
            obj = j[0] if isinstance(j, list) and j else j
            if isinstance(obj, dict) and (obj.get("path") or obj.get("id")):
                return {"id": obj.get("id") or "", "path": obj.get("path") or ""}
        # 5xx: remote may have stored the object — surface as ambiguous to caller.
        if int(r.status_code) >= 500:
            raise RuntimeError(f"postiz_upload_ambiguous:{r.status_code}")
        logger.warning(f"[postiz] upload {r.status_code}: {r.text[:140]}")
    except RuntimeError:
        raise
    except Exception as e:
        # Transport drop after the upload request left this process is ambiguous.
        logger.warning(f"[postiz] upload failed: {e}")
        raise RuntimeError(f"postiz_upload_ambiguous:{e}") from e
    finally:
        if owns_fh and fh is not None:
            try:
                fh.close()
            except Exception:
                pass
    return None


async def publish_video(
    client: dict[str, Any],
    caption: str,
    video_path: str = "",
    *,
    video_file: Any | None = None,
    filename: str = "video.mp4",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Video+caption (ya text-only, video_path="" ho to) ko client ke configured
    Postiz channels pe ABHI post karo. Inert agar key/integration-ids missing.
    Returns {sent, channels, post_id, post_ids, post_url, reason}.  Postiz's
    create-post API returns one ``postId`` per integration; preserving those
    ids is mandatory launch evidence (``sent=True`` alone only proves that the
    request was accepted, not which provider records were created).

    Stage 3C: pass ``video_file`` (verified descriptor). The adapter must not
    reopen ``video_path`` when ``video_file`` is supplied.

    Idempotency: Postiz public API does not document an idempotency-key
    contract. ``idempotency_key`` is accepted for forward compatibility and
    recorded in the return meta, but is NOT sent as a provider guarantee and
    does NOT make external publication exactly-once.
    """
    if not enabled():
        return {
            "sent": False,
            "outcome": "failed",
            "reason": "POSTIZ_API_KEY unset",
            "provider_idempotency": False,
        }
    ids = _integration_ids(client)
    if not ids:
        return {
            "sent": False,
            "outcome": "failed",
            "reason": "koi postiz_integrations id nahi (client/env)",
            "provider_idempotency": False,
        }
    # Platform map (id -> identifier e.g. "youtube") — needed both to skip
    # media-required platforms on text-only posts AND to build YouTube's own
    # required settings below. Best-effort; empty dict on failure (fine, just
    # means no per-platform special-casing happens, same as before either fix
    # existed).
    platform_map = await _fetch_integration_platforms()
    has_media = bool(video_file is not None or video_path)
    board = _pinterest_board()
    selection = select_publish_channels(ids, platform_map, has_media=has_media, board=board)
    if not selection.get("ok"):
        return {
            "sent": False,
            "outcome": "failed",
            "channels": [],
            "skipped": selection.get("skipped") or [],
            "reason": str(selection.get("reason") or "no_eligible_channels"),
            "provider_idempotency": False,
        }
    ids = list(selection.get("channels") or [])
    media_list: list[dict[str, Any]] = []
    if video_file is not None or video_path:
        try:
            media = await upload_media(
                video_path if video_file is None else "",
                fileobj=video_file,
                filename=filename or (os.path.basename(video_path) if video_path else "video.mp4"),
            )
        except RuntimeError as e:
            # Ambiguous upload transport/5xx — do not classify as retryable failed.
            return {
                "sent": False,
                "outcome": "unknown",
                "reason": str(e)[:150],
                "provider_idempotency": False,
            }
        if media is None:
            # No create-post was attempted. Missing/unreadable media is a
            # definitive local failure (retryable after the file exists).
            return {
                "sent": False,
                "outcome": "failed",
                "reason": "media upload fail (ya file missing)",
                "provider_idempotency": False,
            }
        media_list = [media]
    caption_clean = (caption or "").strip()

    def _value_for(integration_id: str) -> list[dict[str, Any]]:
        # Per-platform caption truncation: X (280) vs Instagram/LinkedIn/etc.
        provider_type = platform_map.get(integration_id) or ""
        limit = _caption_limit(provider_type)
        return [{"content": caption_clean[:limit], "image": media_list}]

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
        if provider_type == "youtube":
            return {**typed, "title": youtube_title, "type": "public"}
        if provider_type == "pinterest" and board:
            return {**typed, "Board": board}
        return typed

    body = {
        "type": "now",
        "date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "shortLink": False,
        "tags": [],
        "posts": [
            {"integration": {"id": i}, "value": _value_for(i), "settings": _settings_for(i)}
            for i in ids
        ],
    }
    # Note: idempotency_key is intentionally NOT forwarded — Postiz docs do not
    # accept/enforce it. Local reservation is the only exactly-once guarantee.
    _ = idempotency_key
    try:
        import httpx

        async with httpx.AsyncClient(timeout=60) as cx:
            r = await cx.post(f"{_base()}/public/v1/posts", headers=_headers(), json=body)
        code = int(r.status_code)
        ok = code // 100 == 2
        if not ok:
            logger.warning(f"[postiz] create {code}: {r.text[:160]}")
        # 5xx after the request left this process: remote may have accepted.
        if code >= 500:
            return {
                "sent": False,
                "outcome": "unknown",
                "channels": ids,
                "reason": f"{code}: {r.text[:160]}",
                "provider_idempotency": False,
            }
        # Definitive client refusal — safe to classify as failed (retryable).
        if code // 100 == 4:
            return {
                "sent": False,
                "outcome": "failed",
                "channels": ids,
                "reason": f"{code}: {r.text[:160]}",
                "provider_idempotency": False,
            }
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
            "sent": bool(ok),
            "outcome": "published" if ok else "failed",
            "channels": ids,
            "post_id": post_ids[0] if post_ids else "",
            "post_ids": post_ids,
            "post_url": post_urls[0] if post_urls else "",
            "provider_idempotency": False,
            **({} if ok else {"reason": f"{code}: {r.text[:160]}"}),
        }
    except Exception as e:
        # Timeout / disconnect after the request may already have been accepted.
        logger.warning(f"[postiz] publish ambiguous: {e}")
        return {
            "sent": False,
            "outcome": "unknown",
            "reason": str(e)[:150],
            "provider_idempotency": False,
        }


def effective_integration_ids(client: dict[str, Any] | None = None) -> list[str]:
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
        return []


def integrations_source(client: dict[str, Any] | None = None) -> str:
    """Which source `effective_integration_ids()` resolved from — "client" /
    "social_config" / "env" / "vault" / "none". Operator triage: tells you WHERE
    to change the value. Customers never report env/vault unless own-brand.
    Never raises."""
    try:
        if _parse_integration_ids((client or {}).get("postiz_integrations")):
            return "client"
        if client and _social_config_integrations(str(client.get("id") or "")):
            return "social_config"
        if _is_own_brand(client):
            if (os.getenv("POSTIZ_INTEGRATIONS") or "").strip():
                return "env"
            if _vault_cfg().get("integrations", ""):
                return "vault"
    except Exception:  # pragma: no cover
        pass
    return "none"


def api_url() -> str:
    """Effective Postiz base URL (env → vault → cloud default). Never raises."""
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
    "select_publish_channels",
    "plan_publish_channels",
]
