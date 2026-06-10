"""
minisite_builder.py — Mini-site BUILDER API (per-client /b/{slug} customization).
==================================================================================

Free, local-only "site builder" surface on top of the existing per-client
mini-site (`app/marketing/mini_site.py`, served at /b/{slug} in main.py). Adds:

  * Customization store  — color palette + layout + logo per slug
                           (data/mini_site_config.jsonl). NEVER raises; sane defaults.
  * Logo upload          — accept png/jpg/webp <=2MB, store under data/logos/,
                           serve back via GET /api/minisite/logo/{file} (FileResponse).
  * Reviews feed         — public (rate-limited) submit + admin moderation; per-client
                           store data/reviews/<slug>.jsonl. Approved reviews render on
                           the mini-site.
  * Widget snippet       — surface embed_widget snippet/urls for a slug (admin copy).
  * Live preview         — admin endpoint returns the freshly-rendered mini-site HTML.

Storage helpers (get_config/set_config, add_review/list_reviews, PALETTES, LAYOUTS,
validate_logo) are module-level and import-safe so `mini_site.render_site()` can
lazily read them at render time without a circular-import problem.

Routes (mounted under /api → /api/minisite/*):
  POST /api/minisite/config            (admin)  set palette/layout/logo for a slug
  GET  /api/minisite/config            (admin)  read merged config for a slug
  GET  /api/minisite/palettes          (admin)  list named palettes + layouts
  POST /api/minisite/logo              (admin)  multipart logo upload → served URL
  POST /api/minisite/logo-url          (admin)  accept + validate an external logo URL
  GET  /api/minisite/logo/{filename}   (public) serve a stored logo file
  GET  /api/minisite/snippet           (admin)  embed widget snippet + widget/embed URLs
  GET  /api/minisite/reviews           (admin)  list ALL reviews (incl. pending) for a slug
  POST /api/minisite/reviews/moderate  (admin)  approve / reject a review
  POST /api/minisite/reviews/submit    (public) submit a review (rate-limited)
  GET  /api/minisite/reviews/public    (public) approved reviews for a slug (mini-site feed)
  GET  /api/minisite/builder-page      (public) serve the admin builder HTML page

Pure stdlib persistence (jsonl), defensive everywhere.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.models.user import User
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/minisite", tags=["Mini-site Builder"])

# --------------------------------------------------------------------------- #
# Paths (module-level consts so tests can monkeypatch to a tmp dir)
# --------------------------------------------------------------------------- #
_DATA_DIR = "data"
_CONFIG_FILE = os.path.join(_DATA_DIR, "mini_site_config.jsonl")
_REVIEWS_DIR = os.path.join(_DATA_DIR, "reviews")
_LOGOS_DIR = os.path.join(_DATA_DIR, "logos")

_FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

# --------------------------------------------------------------------------- #
# Named palettes (CSS-variable sets) + layouts — the "builder" choices
# --------------------------------------------------------------------------- #
# Each palette: primary + accent (validated hex). Mini-site CSS uses --p / --a.
PALETTES: dict[str, dict[str, str]] = {
    "violet": {"primary": "#6d28d9", "accent": "#f59e0b", "label": "Violet & Amber"},
    "ocean": {"primary": "#0369a1", "accent": "#06b6d4", "label": "Ocean Blue"},
    "forest": {"primary": "#15803d", "accent": "#84cc16", "label": "Forest Green"},
    "sunset": {"primary": "#dc2626", "accent": "#f97316", "label": "Sunset Red"},
    "royal": {"primary": "#1e3a8a", "accent": "#d4af37", "label": "Royal Navy & Gold"},
}
DEFAULT_PALETTE = "violet"

# 3 visually-distinct layout templates (render logic in mini_site.py).
LAYOUTS: dict[str, str] = {
    "classic": "Classic — gradient hero, centered (default)",
    "bold": "Bold — large solid hero band, big type, dark sections",
    "minimal": "Minimal — clean white hero, thin accents, lots of space",
}
DEFAULT_LAYOUT = "classic"

_ALLOWED_LOGO_EXT = {"png", "jpg", "jpeg", "webp"}
_MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB
# Magic-byte signatures for the formats we accept (defence-in-depth vs ext spoof).
_LOGO_MAGIC: dict[str, list[bytes]] = {
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "webp": [b"RIFF"],  # RIFF....WEBP
}

_SLUG_RE = re.compile(r"[^a-z0-9-]+")


# --------------------------------------------------------------------------- #
# Small utils
# --------------------------------------------------------------------------- #
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_slug(slug: Any) -> str:
    """Normalise a slug to the kebab charset (path-safe, store-safe)."""
    s = _SLUG_RE.sub("", str(slug or "").strip().lower())
    return s[:64]


_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _clean_hex(value: Any, fallback: str) -> str:
    c = str(value or "").strip()
    return c if _HEX_RE.match(c) else fallback


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    """Parse-safe jsonl read (corrupt lines skipped). Never raises."""
    rows: list[dict[str, Any]] = []
    try:
        if not os.path.isfile(path):
            return rows
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if isinstance(rec, dict):
                        rows.append(rec)
                except Exception:
                    continue
    except Exception as e:  # pragma: no cover
        logger.warning(f"[minisite_builder] read failed {path}: {e}")
    return rows


def _append_jsonl(path: str, rec: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _rewrite_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


# --------------------------------------------------------------------------- #
# A) CONFIG store — palette / layout / logo per slug
# --------------------------------------------------------------------------- #
def _default_config(slug: str) -> dict[str, Any]:
    # NOTE: primary/accent EMPTY by default (na ki resolved palette hex) —
    # warna render_site me client ka brand.primary KABHI nahi lagta (cfg
    # hamesha jeet jata tha). Saved config (palette/custom colors) pe hi
    # concrete hex resolve hota hai (get_config me).
    return {
        "slug": slug,
        "palette": DEFAULT_PALETTE,
        "layout": DEFAULT_LAYOUT,
        "logo_url": "",
        "primary": "",
        "accent": "",
    }


def get_config(slug: str) -> dict[str, Any]:
    """Merged mini-site config for a slug. ALWAYS returns a dict (defaults when
    unset). Never raises — `mini_site.render_site()` relies on this.

    Latest line wins (config file is append-on-update). Resolves the chosen
    palette into concrete primary/accent hex so the renderer can use them
    directly.
    """
    slug = _safe_slug(slug)
    cfg = _default_config(slug)
    try:
        latest: dict[str, Any] | None = None
        for rec in _read_jsonl(_CONFIG_FILE):
            if _safe_slug(rec.get("slug")) == slug:
                latest = rec  # keep walking → last occurrence wins
        if latest:
            pal_key = str(latest.get("palette") or "").strip().lower()
            if pal_key in PALETTES:
                cfg["palette"] = pal_key
                cfg["primary"] = PALETTES[pal_key]["primary"]
                cfg["accent"] = PALETTES[pal_key]["accent"]
            # explicit custom colors (override palette) if provided + valid
            cfg["primary"] = _clean_hex(latest.get("primary"), cfg["primary"])
            cfg["accent"] = _clean_hex(latest.get("accent"), cfg["accent"])
            lay = str(latest.get("layout") or "").strip().lower()
            if lay in LAYOUTS:
                cfg["layout"] = lay
            logo = str(latest.get("logo_url") or "").strip()
            if logo:
                cfg["logo_url"] = logo[:500]
    except Exception as e:  # pragma: no cover
        logger.warning(f"[minisite_builder] get_config failed for {slug!r}: {e}")
    return cfg


def set_config(
    slug: str,
    palette: str | None = None,
    layout: str | None = None,
    logo_url: str | None = None,
    primary: str | None = None,
    accent: str | None = None,
) -> dict[str, Any]:
    """Persist a config update for a slug (append). Returns merged config.
    Only validated fields are written; unknown palette/layout fall back to
    current/defaults. Never raises."""
    slug = _safe_slug(slug)
    if not slug:
        return _default_config("")
    current = get_config(slug)
    rec: dict[str, Any] = {"slug": slug, "updated_at": _now()}

    pal_key = str(palette or "").strip().lower()
    rec["palette"] = pal_key if pal_key in PALETTES else current["palette"]

    lay = str(layout or "").strip().lower()
    rec["layout"] = lay if lay in LAYOUTS else current["layout"]

    # logo_url: only accept our own /api/minisite/logo/... path or an http(s) URL
    if logo_url is not None:
        lu = str(logo_url or "").strip()
        rec["logo_url"] = lu[:500] if (lu == "" or _valid_logo_url(lu)) else current["logo_url"]
    else:
        rec["logo_url"] = current["logo_url"]

    # optional explicit overrides (validated hex; else drop → palette wins)
    ph = _clean_hex(primary, "")
    ah = _clean_hex(accent, "")
    if ph:
        rec["primary"] = ph
    if ah:
        rec["accent"] = ah

    try:
        _append_jsonl(_CONFIG_FILE, rec)
    except Exception as e:  # pragma: no cover
        logger.warning(f"[minisite_builder] set_config write failed: {e}")
    return get_config(slug)


# --------------------------------------------------------------------------- #
# B) LOGO validation + storage
# --------------------------------------------------------------------------- #
def _ext_of(filename: str) -> str:
    return (os.path.splitext(str(filename or ""))[1] or "").lstrip(".").lower()


def _valid_logo_url(url: str) -> bool:
    """Accept an external logo URL only if http(s) + an allowed image extension,
    OR one of our own served logo paths."""
    u = str(url or "").strip()
    if u.startswith("/api/minisite/logo/"):
        return True
    if not (u.startswith("http://") or u.startswith("https://")):
        return False
    path = u.split("?", 1)[0].split("#", 1)[0]
    return _ext_of(path) in _ALLOWED_LOGO_EXT


def validate_logo(filename: str, data: bytes) -> tuple[bool, str, str]:
    """Validate an uploaded logo. Returns (ok, normalized_ext, error).

    Checks: extension allow-list, size <= 2MB, non-empty, and magic-byte sniff
    matching the declared type (defence vs extension spoofing). Never raises.
    """
    try:
        ext = _ext_of(filename)
        if ext not in _ALLOWED_LOGO_EXT:
            return False, "", f"Unsupported type '.{ext}'. Allowed: png, jpg, jpeg, webp."
        if not data:
            return False, "", "Empty file."
        if len(data) > _MAX_LOGO_BYTES:
            return False, "", f"Too large ({len(data)} bytes). Max 2MB."
        sigs = _LOGO_MAGIC.get(ext, [])
        if sigs and not any(data.startswith(s) for s in sigs):
            # webp also needs WEBP at offset 8
            if ext == "webp" and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
                pass
            else:
                return False, "", "File content does not match its extension."
        norm = "jpg" if ext == "jpeg" else ext
        return True, norm, ""
    except Exception as e:  # pragma: no cover
        return False, "", f"Validation error: {e}"


def save_logo(slug: str, filename: str, data: bytes) -> tuple[bool, str, str]:
    """Validate + store a logo under data/logos/. Returns (ok, served_url, error).
    Served URL = /api/minisite/logo/<slug>-<rand>.<ext>. Never raises."""
    slug = _safe_slug(slug) or "logo"
    ok, ext, err = validate_logo(filename, data)
    if not ok:
        return False, "", err
    try:
        os.makedirs(_LOGOS_DIR, exist_ok=True)
        fname = f"{slug}-{uuid.uuid4().hex[:8]}.{ext}"
        with open(os.path.join(_LOGOS_DIR, fname), "wb") as f:
            f.write(data)
        return True, f"/api/minisite/logo/{fname}", ""
    except Exception as e:  # pragma: no cover
        logger.warning(f"[minisite_builder] save_logo failed: {e}")
        return False, "", f"Save failed: {e}"


# --------------------------------------------------------------------------- #
# C) REVIEWS store — per-client jsonl, moderation, public submit
# --------------------------------------------------------------------------- #
def _reviews_path(slug: str) -> str:
    return os.path.join(_REVIEWS_DIR, f"{_safe_slug(slug) or 'business'}.jsonl")


def add_review(
    slug: str,
    name: str,
    rating: Any,
    text: str,
    approved: bool = False,
) -> dict[str, Any]:
    """Add a review (pending by default). Returns the stored record. Never raises.
    Text/name are escaped at render time, but we also clamp lengths here."""
    slug = _safe_slug(slug)
    try:
        try:
            r = int(rating)
        except Exception:
            r = 5
        r = max(1, min(5, r))
        rec = {
            "id": uuid.uuid4().hex[:12],
            "slug": slug,
            "name": str(name or "Anonymous").strip()[:80] or "Anonymous",
            "rating": r,
            "text": str(text or "").strip()[:600],
            "approved": bool(approved),
            "created_at": _now(),
        }
        _append_jsonl(_reviews_path(slug), rec)
        return rec
    except Exception as e:  # pragma: no cover
        logger.warning(f"[minisite_builder] add_review failed: {e}")
        return {"error": str(e)}


def list_reviews(slug: str, approved_only: bool = True, limit: int = 50) -> list[dict[str, Any]]:
    """Reviews for a slug, newest first. approved_only filters to approved.
    Never raises (used by the public mini-site feed)."""
    slug = _safe_slug(slug)
    try:
        rows = _read_jsonl(_reviews_path(slug))
        if approved_only:
            rows = [r for r in rows if r.get("approved")]
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return rows[: max(1, min(int(limit or 50), 200))]
    except Exception as e:  # pragma: no cover
        logger.warning(f"[minisite_builder] list_reviews failed: {e}")
        return []


def moderate_review(slug: str, review_id: str, approved: bool) -> bool:
    """Set approved flag on a review (or delete when approved is None-like via
    a separate path). Returns True if a record changed. Never raises."""
    slug = _safe_slug(slug)
    try:
        path = _reviews_path(slug)
        rows = _read_jsonl(path)
        changed = False
        for r in rows:
            if str(r.get("id")) == str(review_id):
                r["approved"] = bool(approved)
                r["moderated_at"] = _now()
                changed = True
        if changed:
            _rewrite_jsonl(path, rows)
        return changed
    except Exception as e:  # pragma: no cover
        logger.warning(f"[minisite_builder] moderate_review failed: {e}")
        return False


# --- simple in-memory rate limiter for public review submit (per-IP) --- #
_RL_WINDOW_SEC = 3600
_RL_MAX = 5
_rl_hits: dict[str, list[float]] = {}


def _rate_ok(key: str) -> bool:
    """True if `key` (IP) is under the submit cap in the rolling window."""
    now = time.time()
    hits = [t for t in _rl_hits.get(key, []) if now - t < _RL_WINDOW_SEC]
    if len(hits) >= _RL_MAX:
        _rl_hits[key] = hits
        return False
    hits.append(now)
    _rl_hits[key] = hits
    return True


# --------------------------------------------------------------------------- #
# Pydantic request models
# --------------------------------------------------------------------------- #
class ConfigIn(BaseModel):
    slug: str = Field(..., min_length=1, max_length=64)
    palette: str | None = Field(None, max_length=32)
    layout: str | None = Field(None, max_length=32)
    logo_url: str | None = Field(None, max_length=500)
    primary: str | None = Field(None, max_length=9)
    accent: str | None = Field(None, max_length=9)


class LogoUrlIn(BaseModel):
    slug: str = Field(..., min_length=1, max_length=64)
    logo_url: str = Field(..., min_length=4, max_length=500)


class ReviewSubmitIn(BaseModel):
    slug: str = Field(..., min_length=1, max_length=64)
    name: str = Field("Anonymous", max_length=80)
    rating: int = Field(5, ge=1, le=5)
    text: str = Field("", max_length=600)
    website: str = Field("", max_length=200)  # honeypot


class ModerateIn(BaseModel):
    slug: str = Field(..., min_length=1, max_length=64)
    review_id: str = Field(..., min_length=1, max_length=40)
    approved: bool = True


# --------------------------------------------------------------------------- #
# ADMIN routes — config + palettes
# --------------------------------------------------------------------------- #
@router.get("/palettes")
async def get_palettes(current_user: User = Depends(require_admin)):
    """All named palettes + layouts (for the builder UI)."""
    return {
        "palettes": PALETTES,
        "default_palette": DEFAULT_PALETTE,
        "layouts": LAYOUTS,
        "default_layout": DEFAULT_LAYOUT,
    }


@router.get("/config")
async def read_config(
    slug: str = Query(..., min_length=1, max_length=64),
    current_user: User = Depends(require_admin),
):
    """Merged config for a slug (defaults when unset)."""
    return get_config(slug)


@router.post("/config")
async def write_config(req: ConfigIn, current_user: User = Depends(require_admin)):
    """Set palette / layout / logo for a slug."""
    cfg = set_config(
        req.slug,
        palette=req.palette,
        layout=req.layout,
        logo_url=req.logo_url,
        primary=req.primary,
        accent=req.accent,
    )
    return {"ok": True, "config": cfg}


# --------------------------------------------------------------------------- #
# ADMIN routes — logo upload / url
# --------------------------------------------------------------------------- #
@router.post("/logo")
async def upload_logo(
    slug: str = Query(..., min_length=1, max_length=64),
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
):
    """Upload a logo (png/jpg/webp <=2MB). Stores locally, sets config.logo_url,
    returns the served URL."""
    try:
        data = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Read failed: {e}")
    ok, url, err = save_logo(slug, file.filename or "logo", data)
    if not ok:
        raise HTTPException(status_code=400, detail=err)
    set_config(slug, logo_url=url)
    return {"ok": True, "logo_url": url}


@router.post("/logo-url")
async def set_logo_url(req: LogoUrlIn, current_user: User = Depends(require_admin)):
    """Accept + validate an external logo URL (extension allow-list)."""
    if not _valid_logo_url(req.logo_url):
        raise HTTPException(
            status_code=400,
            detail="URL must be http(s) and end in .png/.jpg/.jpeg/.webp",
        )
    cfg = set_config(req.slug, logo_url=req.logo_url)
    return {"ok": True, "config": cfg}


@router.get("/logo/{filename}")
async def serve_logo(filename: str):
    """Serve a stored logo file (public). Path-traversal-safe."""
    safe = os.path.basename(str(filename or ""))
    if not safe or _ext_of(safe) not in _ALLOWED_LOGO_EXT:
        raise HTTPException(status_code=404, detail="Not found")
    full = os.path.join(_LOGOS_DIR, safe)
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="Not found")
    media = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
    }.get(_ext_of(safe), "application/octet-stream")
    return FileResponse(full, media_type=media)


# --------------------------------------------------------------------------- #
# ADMIN routes — widget snippet
# --------------------------------------------------------------------------- #
@router.get("/snippet")
async def get_widget_snippet(
    slug: str = Query(..., min_length=1, max_length=64),
    current_user: User = Depends(require_admin),
):
    """Surface the embeddable lead-capture widget snippet + URLs for a slug."""
    s = _safe_slug(slug)
    try:
        from app.marketing import embed_widget

        base = embed_widget.site_base()
        return {
            "slug": s,
            "snippet": embed_widget.snippet(s),
            "widget_url": f"{base}/b/{s}/widget.js",
            "embed_url": f"{base}/b/{s}/embed",
            "site_url": f"{base}/b/{s}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"snippet failed: {e}")


# --------------------------------------------------------------------------- #
# ADMIN routes — reviews moderation
# --------------------------------------------------------------------------- #
@router.get("/reviews")
async def admin_list_reviews(
    slug: str = Query(..., min_length=1, max_length=64),
    current_user: User = Depends(require_admin),
):
    """All reviews (incl. pending) for a slug — moderation view."""
    rows = list_reviews(slug, approved_only=False, limit=200)
    return {"slug": _safe_slug(slug), "reviews": rows, "count": len(rows)}


@router.post("/reviews/moderate")
async def admin_moderate_review(req: ModerateIn, current_user: User = Depends(require_admin)):
    """Approve / reject a review."""
    ok = moderate_review(req.slug, req.review_id, req.approved)
    return {"ok": ok, "approved": req.approved}


# --------------------------------------------------------------------------- #
# PUBLIC routes — review submit + approved feed
# --------------------------------------------------------------------------- #
@router.post("/reviews/submit")
async def public_submit_review(req: ReviewSubmitIn, request: Request):
    """Public review submit (rate-limited per IP). Stored as PENDING (approved
    by admin before it shows). Honeypot 'website' must stay empty."""
    if (req.website or "").strip():
        # bot — silently accept, store nothing
        return {"ok": True, "message": "Dhanyawad!"}
    ip = "anon"
    try:
        ip = request.client.host if request.client else "anon"
    except Exception:
        ip = "anon"
    if not _rate_ok(f"rev:{ip}"):
        raise HTTPException(status_code=429, detail="Bahut requests — thodi der baad try karein.")
    if not _safe_slug(req.slug):
        raise HTTPException(status_code=400, detail="Invalid business.")
    rec = add_review(req.slug, req.name, req.rating, req.text, approved=False)
    if rec.get("error"):
        raise HTTPException(status_code=500, detail="Save failed.")
    return {
        "ok": True,
        "message": "Shukriya! Aapka review review ke baad dikhega.",
        "id": rec.get("id"),
    }


@router.get("/reviews/public")
async def public_reviews(slug: str = Query(..., min_length=1, max_length=64)):
    """Approved reviews for a slug (mini-site feed; no auth)."""
    rows = list_reviews(slug, approved_only=True, limit=50)
    # strip internal fields for the public payload
    out = [
        {
            "name": r.get("name"),
            "rating": r.get("rating"),
            "text": r.get("text"),
            "created_at": r.get("created_at"),
        }
        for r in rows
    ]
    avg = round(sum(r.get("rating", 0) for r in rows) / len(rows), 1) if rows else 0
    return {"slug": _safe_slug(slug), "reviews": out, "count": len(out), "avg_rating": avg}


# --------------------------------------------------------------------------- #
# ADMIN — live preview + builder page
# --------------------------------------------------------------------------- #
@router.get("/preview")
async def preview_site(
    slug: str = Query(..., min_length=1, max_length=64),
    current_user: User = Depends(require_admin),
):
    """Render the live mini-site HTML for a slug (admin preview). The renderer
    reads the just-saved config, so this reflects unsaved-but-posted changes."""
    try:
        from app.marketing.clients_store import get_by_slug
        from app.marketing.mini_site import render_site

        client = get_by_slug(_safe_slug(slug))
        if not client:
            # render a minimal placeholder client so preview still works pre-onboard
            client = {"business_name": "Preview Business", "slug": _safe_slug(slug)}
        return HTMLResponse(content=render_site(client))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"preview failed: {e}")


@router.get("/builder-page", include_in_schema=False)
async def builder_page():
    """Serve the admin mini-site builder HTML page (auth handled client-side via
    localStorage accessToken, same pattern as /app/analytics)."""
    page = _FRONTEND_DIR / "minisite_builder.html"
    if not page.is_file():
        return JSONResponse({"error": "builder page missing"}, status_code=404)
    return FileResponse(str(page))


__all__ = [
    "router",
    "get_config",
    "set_config",
    "add_review",
    "list_reviews",
    "moderate_review",
    "validate_logo",
    "save_logo",
    "PALETTES",
    "LAYOUTS",
    "DEFAULT_PALETTE",
    "DEFAULT_LAYOUT",
]
