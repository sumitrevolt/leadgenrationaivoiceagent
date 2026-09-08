"""Public email open + click tracking endpoints (listmonk parity).

Mounted with NO prefix (root-level), same as the /r/{code} redirect router:

    GET /t/o/{token}          -> open pixel  (also accepts /t/o/{token}.gif)
    GET /t/c/{token}          -> click redirect (302 to decoded real URL)
    GET /api/admin/email-tracking/stats  -> admin-only aggregate stats

Design rules (match project conventions):
  - **PUBLIC** (no auth) for /t/o and /t/c — these are hit by email clients.
  - **NEVER raise / never 500** on the pixel: a broken token must STILL return
    the 1x1 GIF (a broken image in an inbox looks like spam-bait).
  - **Open-redirect / SSRF safe**: /t/c only redirects to http/https URLs decoded
    from the HMAC-signed token (verify_click_token validates scheme); invalid
    token → safe fallback to the public base URL.
  - **Rate-limited** via the project's per-IP ``rate_limit`` dependency.
  - Flag-gated upstream (EMAIL_TRACKING): when OFF nothing emits these tokens, so
    these routes simply never get hit — they stay mounted but inert.
  - Lazy app.* imports inside handlers (import-safe boot).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.models.user import User
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(tags=["Email Tracking"])

# 1x1 transparent GIF (43 bytes). Returned ALWAYS by the open pixel.
_PIXEL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00"
    b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01"
    b"\x00\x00\x02\x02D\x01\x00;"
)
_PIXEL_HEADERS = {"Cache-Control": "no-store, no-cache, must-revalidate, private"}

# Safe fallback when a click token is invalid (never reflect attacker input).
_FALLBACK_URL = "https://leadsgenai.in"


def _pixel_response() -> Response:
    return Response(content=_PIXEL_GIF, media_type="image/gif", headers=_PIXEL_HEADERS)


@router.get("/t/o/{token}", dependencies=[Depends(rate_limit("email_track_open", 120, 60))])
async def track_open(token: str, request: Request) -> Response:
    """Open pixel. Accepts trailing ``.gif``. ALWAYS returns a 1x1 GIF, never 500."""
    try:
        from app.marketing import email_tracking

        tok = token[:-4] if token.lower().endswith(".gif") else token
        email_tracking.record_open(tok)
    except Exception as ex:  # never-raise — broken pixel must still render
        logger.debug("[email_track] open record failed: %s", ex)
    return _pixel_response()


@router.get("/t/c/{token}", dependencies=[Depends(rate_limit("email_track_click", 120, 60))])
async def track_click(token: str, request: Request) -> RedirectResponse:
    """Click tracker → 302 redirect to the decoded real URL.

    Invalid/forged token → safe fallback to public base URL. Never raises.
    """
    target = _FALLBACK_URL
    try:
        from app.marketing import email_tracking

        url = email_tracking.record_click(token)
        # record_click already validated http/https scheme via verify_click_token.
        if url:
            target = url
    except Exception as ex:  # never-raise
        logger.debug("[email_track] click record failed: %s", ex)
    return RedirectResponse(url=target, status_code=302)


@router.get("/api/admin/email-tracking/stats")
async def email_tracking_stats(
    campaign: str | None = None,
    current_user: User = Depends(require_admin),
) -> dict:
    """Admin-only aggregate open/click stats (optional ?campaign= filter)."""
    try:
        from app.marketing import email_tracking

        return {"ok": True, "stats": email_tracking.stats(campaign)}
    except Exception as ex:  # pragma: no cover - never-raise
        logger.debug("[email_track] stats failed: %s", ex)
        return {"ok": False, "stats": {}}
