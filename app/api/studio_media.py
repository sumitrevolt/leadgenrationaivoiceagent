"""
Customer Studio — Media tools (image generate/transform with secure upload+serve).
==================================================================================
Powers the "Media Studio" tools that produce/consume image FILES (vs the 83
text/SVG Studio tools). Free-stack: PIL (pillow, baked) for gif/sticker/resize;
rembg (optional) for background removal — graceful if absent.

Security model (file uploads on a payments platform — see plan
docs/superpowers/plans/STUDIO_IMAGE_VIDEO_TOOLS_PLAN.md):
  * require_customer on every route; rate-limited.
  * Upload: size cap + content-type allowlist + MAGIC-BYTE sniff (not extension) +
    PIL verify + decompression-bomb pixel bound. Stored under a per-client dir.
  * IDOR-safe BY CONSTRUCTION: every path is data/studio_*/<client_id>/... where
    client_id comes from the JWT — a client can never name another client's file.
  * Opaque hex ids (uuid). Serve validates id is hex (no path traversal) and only
    looks inside the authed client's own dir.
  * Heavy PIL/IO runs in asyncio.to_thread (NEVER block the event loop).
  * Outputs/uploads older than 48h are purged opportunistically (disk hygiene).

Mount: app.include_router(studio_media.router)  (carries its own prefix).
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import shutil
import time
import uuid

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.customer_auth import require_customer
from app.api.customer_dashboard_builders import _client_record
from app.api.ratelimit import rate_limit

logger = logging.getLogger(__name__)


def _safe_cid(cid: str) -> str:
    """Filesystem-safe client id for per-client dirs (no traversal)."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(cid or "anon"))[:64] or "anon"


router = APIRouter(prefix="/api/customer/studio", tags=["Customer Studio Media"])

_UPLOAD_DIR = os.path.join("data", "studio_uploads")
_MEDIA_DIR = os.path.join("data", "studio_media")
_MAX_UPLOAD = 8 * 1024 * 1024  # 8 MB image cap
_MAX_PIXELS = 40_000_000  # ~6300x6300 — decompression-bomb guard
_TTL_SECONDS = 48 * 3600
_HEXID = re.compile(r"^[a-f0-9]{32}$")
_GEN = rate_limit("cust_studio_media", 30, 60)
_UPLOAD_RL = rate_limit("cust_studio_upload", 15, 60)

# magic-byte → extension (content sniff, NOT the client-sent filename/type)
_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
)
_EXT_CT = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
    "mp4": "video/mp4",
}
_JOB_DIR = os.path.join("data", "studio_jobs")
_VIDEO_RL = rate_limit("cust_studio_video", 4, 300)  # video is CPU-heavy: 4 / 5min / IP


def _sniff_ext(data: bytes) -> str | None:
    for sig, ext in _MAGIC:
        if data.startswith(sig):
            return ext
    if len(data) >= 12 and data[0:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _purge_old() -> None:
    """Best-effort TTL cleanup of uploads/outputs (never raises)."""
    cutoff = time.time() - _TTL_SECONDS
    for base in (_UPLOAD_DIR, _MEDIA_DIR):
        try:
            for cid in os.listdir(base):
                d = os.path.join(base, cid)
                if not os.path.isdir(d):
                    continue
                for fn in os.listdir(d):
                    fp = os.path.join(d, fn)
                    try:
                        if os.path.getmtime(fp) < cutoff:
                            os.remove(fp)
                    except OSError:
                        pass
        except OSError:
            pass


def _client_dir(base: str, client_id: str) -> str:
    d = os.path.join(base, _safe_cid(client_id))
    os.makedirs(d, exist_ok=True)
    return d


def _resolve_upload(client_id: str, upload_id: str) -> str | None:
    """Resolve an upload_id to a path INSIDE the authed client's own dir (IDOR-safe)."""
    if not _HEXID.match(upload_id or ""):
        return None
    d = _client_dir(_UPLOAD_DIR, client_id)
    for fn in os.listdir(d):
        if fn.startswith(upload_id + "."):
            return os.path.join(d, fn)
    return None


def _store_output(
    client_id: str, *, src_path: str | None = None, data: bytes | None = None, ext: str = "png"
) -> str:
    d = _client_dir(_MEDIA_DIR, client_id)
    mid = uuid.uuid4().hex
    dst = os.path.join(d, f"{mid}.{ext}")
    if data is not None:
        with open(dst, "wb") as f:
            f.write(data)
    elif src_path and os.path.isfile(src_path):
        shutil.copyfile(src_path, dst)
    else:
        raise ValueError("no output source")
    return mid


def _media_item(client_id: str, mid: str, ext: str, label: str = "") -> dict:
    return {"media_id": mid, "ext": ext, "label": label, "url": f"/api/customer/studio/media/{mid}"}


def _validate_image(data: bytes) -> str:
    """Return sniffed ext or raise HTTPException. Verifies via PIL + pixel bound."""
    ext = _sniff_ext(data)
    if ext not in ("png", "jpg", "webp"):
        raise HTTPException(status_code=415, detail="Sirf PNG / JPG / WEBP image allowed.")
    try:
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = _MAX_PIXELS
        im = Image.open(io.BytesIO(data))
        im.verify()  # raises on corrupt / bomb
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=415, detail="Image corrupt ya unsupported hai.")
    return ext


# --------------------------------------------------------------------------- #
# Upload + serve
# --------------------------------------------------------------------------- #
@router.post("/upload", dependencies=[Depends(_UPLOAD_RL)])
async def studio_upload(
    file: UploadFile = File(...), client_id: str = Depends(require_customer)
) -> dict:
    """Upload an image (PNG/JPG/WEBP ≤8MB). Returns an opaque upload_id (client-scoped)."""
    data = await file.read(_MAX_UPLOAD + 1)
    if len(data) > _MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="File 8MB se badi hai.")
    if not data:
        raise HTTPException(status_code=400, detail="Khali file.")
    ext = await asyncio.to_thread(_validate_image, data)
    _purge_old()
    uid = uuid.uuid4().hex
    d = _client_dir(_UPLOAD_DIR, client_id)
    with open(os.path.join(d, f"{uid}.{ext}"), "wb") as f:
        f.write(data)
    return {"ok": True, "upload_id": uid, "ext": ext}


@router.get("/media/{media_id}")
def studio_serve_media(media_id: str, client_id: str = Depends(require_customer)):
    """Serve a generated file — ONLY from the authed client's own media dir."""
    if not _HEXID.match(media_id or ""):
        raise HTTPException(status_code=404, detail="Not found")
    d = os.path.join(_MEDIA_DIR, _safe_cid(client_id))
    if os.path.isdir(d):
        for fn in os.listdir(d):
            if fn.startswith(media_id + "."):
                ext = fn.rsplit(".", 1)[-1].lower()
                return FileResponse(
                    os.path.join(d, fn),
                    media_type=_EXT_CT.get(ext, "application/octet-stream"),
                    filename=f"leadsgenai_{media_id[:8]}.{ext}",
                )
    raise HTTPException(status_code=404, detail="Not found")


# --------------------------------------------------------------------------- #
# Image tools
# --------------------------------------------------------------------------- #
class GifReq(BaseModel):
    text: str = Field("", max_length=40)
    style: str = Field("pulse", max_length=12)


class ResizeReq(BaseModel):
    upload_id: str = Field(..., max_length=40)
    sizes: list[str] | None = Field(None)


class BgReq(BaseModel):
    upload_id: str = Field(..., max_length=40)


def _slug_of(client_id: str) -> str:
    rec = _client_record(client_id) or {}
    return str(rec.get("slug") or rec.get("id") or client_id)


@router.post("/img-gif", dependencies=[Depends(_GEN)])
async def studio_img_gif(
    req: GifReq = Body(default=GifReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Animated text GIF (512², brand colors) for WhatsApp status / story."""
    try:
        from app.marketing import gif_maker

        out = await asyncio.to_thread(gif_maker.make_gif, req.text, _slug_of(client_id), req.style)
    except Exception as e:
        logger.error("img-gif failed: %s", e)
        raise HTTPException(status_code=503, detail="GIF abhi nahi bana — baad me try karo.")
    if not out.get("ok") or not out.get("path"):
        return {
            "ok": False,
            "tool": "img-gif",
            "note": out.get("hint") or "GIF abhi available nahi.",
        }
    mid = _store_output(client_id, src_path=out["path"], ext="gif")
    return {
        "ok": True,
        "tool": "img-gif",
        "media": [_media_item(client_id, mid, "gif")],
        "text": out.get("text", ""),
    }


@router.post("/img-sticker", dependencies=[Depends(_GEN)])
async def studio_img_sticker(client_id: str = Depends(require_customer)) -> dict:
    """6 branded WhatsApp stickers (512² transparent PNG)."""
    rec = _client_record(client_id) or {}
    try:
        from app.marketing import sticker_pack

        out = await asyncio.to_thread(
            sticker_pack.generate_stickers,
            _slug_of(client_id),
            str(rec.get("business_name") or ""),
            str(rec.get("niche") or ""),
        )
    except Exception as e:
        logger.error("img-sticker failed: %s", e)
        raise HTTPException(status_code=503, detail="Stickers abhi nahi bane.")
    if not out.get("ok"):
        return {"ok": False, "tool": "img-sticker", "note": "Stickers abhi available nahi."}
    media = [
        _media_item(
            client_id, _store_output(client_id, src_path=p, ext="png"), "png", f"Sticker {i + 1}"
        )
        for i, p in enumerate(out.get("files", []))
    ]
    return {"ok": True, "tool": "img-sticker", "media": media, "note": out.get("note", "")}


@router.post("/img-resize", dependencies=[Depends(_GEN)])
async def studio_img_resize(req: ResizeReq, client_id: str = Depends(require_customer)) -> dict:
    """Uploaded image → all social sizes (square / story / banner / WhatsApp status)."""
    path = _resolve_upload(client_id, req.upload_id)
    if not path:
        raise HTTPException(status_code=404, detail="Upload nahi mila — phir se upload karo.")
    try:
        from app.marketing import magic_resize

        out = await asyncio.to_thread(
            magic_resize.resize_pack, path, None, req.sizes, _slug_of(client_id)
        )
    except Exception as e:
        logger.error("img-resize failed: %s", e)
        raise HTTPException(status_code=503, detail="Resize abhi nahi hua.")
    if not out.get("ok"):
        return {"ok": False, "tool": "img-resize", "note": out.get("error") or "Resize fail."}
    media = [
        _media_item(client_id, _store_output(client_id, src_path=p, ext="png"), "png", size)
        for size, p in (out.get("files") or {}).items()
    ]
    return {"ok": True, "tool": "img-resize", "media": media, "note": out.get("note", "")}


@router.post("/img-bgremove", dependencies=[Depends(_GEN)])
async def studio_img_bgremove(req: BgReq, client_id: str = Depends(require_customer)) -> dict:
    """Uploaded image → transparent background (needs rembg; graceful if absent)."""
    try:
        from app.marketing import bg_remove

        if not bg_remove.available():
            return {
                "ok": False,
                "tool": "img-bgremove",
                "note": "Background removal abhi server pe enable nahi (rembg). Jald aayega.",
            }
    except Exception:
        return {
            "ok": False,
            "tool": "img-bgremove",
            "note": "Background removal abhi available nahi.",
        }
    path = _resolve_upload(client_id, req.upload_id)
    if not path:
        raise HTTPException(status_code=404, detail="Upload nahi mila — phir se upload karo.")
    try:
        with open(path, "rb") as f:
            data = f.read()
        res = await asyncio.to_thread(bg_remove.remove_bg, data)
    except Exception as e:
        logger.error("img-bgremove failed: %s", e)
        raise HTTPException(status_code=503, detail="Background remove abhi nahi hua.")
    if isinstance(res, dict):
        return {"ok": False, "tool": "img-bgremove", "note": res.get("error") or "Nahi hua."}
    mid = _store_output(client_id, data=res, ext="png")
    return {"ok": True, "tool": "img-bgremove", "media": [_media_item(client_id, mid, "png")]}


_MEDIA_TOOLS = [
    {
        "key": "img-gif",
        "icon": "🎞️",
        "title": "Animated GIF",
        "desc": "Text → WhatsApp status GIF",
        "upload": False,
    },
    {
        "key": "img-sticker",
        "icon": "🩷",
        "title": "WhatsApp Stickers",
        "desc": "6 branded stickers",
        "upload": False,
    },
    {
        "key": "img-resize",
        "icon": "🔁",
        "title": "Magic Resize",
        "desc": "Photo → sab social sizes",
        "upload": True,
    },
    {
        "key": "img-bgremove",
        "icon": "✂️",
        "title": "Background Remove",
        "desc": "Photo ka background hatao",
        "upload": True,
    },
    {
        "key": "video-reel",
        "icon": "🎬",
        "title": "Faceless Reel",
        "desc": "Text → short video reel",
        "upload": False,
        "job": True,
    },
]


@router.get("/media-tools")
def studio_media_tools(client_id: str = Depends(require_customer)) -> dict:
    """List of media tools (drives the Media Studio UI)."""
    return {"ok": True, "count": len(_MEDIA_TOOLS), "tools": _MEDIA_TOOLS}


# --------------------------------------------------------------------------- #
# Video reel — CPU-heavy (ffmpeg). Background-thread JOB pattern (file-based
# status so any uvicorn worker can poll). Submit → poll → serve media.
# --------------------------------------------------------------------------- #
import json as _json
import threading as _threading


class ReelReq(BaseModel):
    slides: list[str] | None = Field(None, description="3-5 short lines (blank = auto)")
    offer: str = Field("", max_length=160)


def _job_path(client_id: str, job_id: str) -> str:
    return os.path.join(_client_dir(_JOB_DIR, client_id), f"{job_id}.json")


def _write_job(client_id: str, job_id: str, data: dict) -> None:
    try:
        with open(_job_path(client_id, job_id), "w", encoding="utf-8") as f:
            _json.dump(data, f)
    except OSError:
        pass


def _reel_worker(client_id: str, job_id: str, slides, offer: str) -> None:
    """Runs build_reel (async) in a thread; writes status + stores mp4 as media."""
    try:
        from app.marketing import reel_video

        rec = _client_record(client_id) or {}
        out = asyncio.run(
            reel_video.build_reel(
                business_name=str(rec.get("business_name") or "Aapka Business"),
                niche=str(rec.get("niche") or "general"),
                slides=slides,
                offer=offer,
                client_id=str(rec.get("id") or client_id),
            )
        )
        if isinstance(out, dict) and out.get("path") and os.path.isfile(out["path"]):
            mid = _store_output(client_id, src_path=out["path"], ext="mp4")
            _write_job(
                client_id,
                job_id,
                {"status": "done", "media": [_media_item(client_id, mid, "mp4", "Reel")]},
            )
        else:
            _write_job(
                client_id,
                job_id,
                {
                    "status": "error",
                    "note": (
                        (out or {}).get("error", "Reel nahi bana.")
                        if isinstance(out, dict)
                        else "Reel nahi bana."
                    ),
                },
            )
    except Exception as e:
        logger.error("reel worker failed: %s", e)
        _write_job(
            client_id, job_id, {"status": "error", "note": "Reel render fail — baad me try karo."}
        )


@router.post("/video-reel", dependencies=[Depends(_VIDEO_RL)])
def studio_video_reel(
    req: ReelReq = Body(default=ReelReq()), client_id: str = Depends(require_customer)
) -> dict:
    """Submit a faceless reel render (background). Returns job_id; poll /video-status/{id}."""
    try:
        from app.marketing import reel_video

        if not reel_video.available().get("ok"):
            return {
                "ok": False,
                "tool": "video-reel",
                "note": "Video render abhi server pe enable nahi.",
            }
    except Exception:
        return {"ok": False, "tool": "video-reel", "note": "Video render abhi available nahi."}
    _purge_old()
    job_id = uuid.uuid4().hex
    _write_job(client_id, job_id, {"status": "processing"})
    slides = [s for s in (req.slides or []) if str(s).strip()][:5] or None
    _threading.Thread(
        target=_reel_worker, args=(client_id, job_id, slides, req.offer), daemon=True
    ).start()
    return {
        "ok": True,
        "tool": "video-reel",
        "job_id": job_id,
        "status": "processing",
        "note": "Reel ban raha hai — 30-60 sec lagte. Status check karo.",
    }


@router.get("/video-status/{job_id}")
def studio_video_status(job_id: str, client_id: str = Depends(require_customer)) -> dict:
    """Poll a reel render job (owner-scoped)."""
    if not _HEXID.match(job_id or ""):
        raise HTTPException(status_code=404, detail="Not found")
    fp = _job_path(client_id, job_id)
    if not os.path.isfile(fp):
        raise HTTPException(status_code=404, detail="Job nahi mila")
    try:
        with open(fp, encoding="utf-8") as f:
            data = _json.load(f)
    except Exception:
        data = {"status": "error", "note": "Status read fail."}
    return {"ok": True, **data}
