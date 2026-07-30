"""ContentPlus API — content/outreach plus batch (agent E).

  POST /api/contentplus/service-cycle        (admin)  repeat-service cycle add
  GET  /api/contentplus/service-due          (admin)  due reminders (?days_ahead=3)
  POST /api/contentplus/service-run          (admin)  due → WA reminder DRAFTS (1-click, no auto-send)
  POST /api/contentplus/clips                (admin)  long video → short clips (BACKGROUND job; multipart: file|path)
  GET  /api/contentplus/clips/{job_id}       (admin)  clip job status + files
  GET  /api/contentplus/clip-file/{job}/{name}   (public, rate-limited, regex-locked) mp4 serve
  POST /api/contentplus/gif                  (admin)  animated text GIF (PIL, to_thread)
  GET  /api/contentplus/gif-file/{slug}/{name}   (public, rate-limited, regex-locked) gif serve
  POST /api/contentplus/avatar-video         (admin)  AI avatar video post (Pollinations video_url REUSE)
  GET  /api/contentplus/outreach-variants    (admin)  cold-email A/B stats (Laplace winner)
  POST /api/contentplus/outreach-variants/reply  (admin)  variant pe reply mila — record

Mount (main.py):
    from app.api.contentplus import router as contentplus_router
    app.include_router(contentplus_router, prefix="/api")   # /api/contentplus/*

PROD-DOWN LESSONS baked in: ffmpeg = background daemon thread + jsonl status
(KABHI inline nahi); PIL = asyncio.to_thread + wait_for; LLM = wait_for.
Sab modules never-raise (error dicts). Free stack.
"""

from __future__ import annotations

import asyncio
import os
import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(
    prefix="/contentplus",
    tags=["ContentPlus"],
    dependencies=[Depends(rate_limit("contentplus", 60, 60))],
)

_SAFE_SEG_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CLIP_NAME_RE = re.compile(r"^clip_\d{1,2}\.mp4$")
_GIF_NAME_RE = re.compile(r"^[a-f0-9]{10}\.gif$")
_UPLOAD_DIR = os.path.join("data", "clips", "uploads")


# Canonical media ceiling lives in app/marketing/media_limits.py so the upload
# path and the approved-snapshot path cannot drift. Read at call time via
# _upload_max_bytes(); the module-level name is kept as a compatibility alias
# for existing readers and reflects the default when no override is set.
def _upload_max_bytes() -> int:
    from app.marketing.media_limits import max_upload_bytes

    return max_upload_bytes()


_UPLOAD_MAX_BYTES = _upload_max_bytes()  # compat alias (default-config value)
_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


# ------------------- F3: repeat-service reminders (NiceJob) ------------------ #
class ServiceCycleIn(BaseModel):
    client_id: str
    customer: dict[str, Any]  # {name, phone}
    service: str
    interval_days: int
    last_service_date: str | None = ""


@router.post("/service-cycle")
async def add_service_cycle(body: ServiceCycleIn, _user=Depends(require_admin)):
    """End-customer ka repeat-service cycle set karo (AC/RO/car service...)."""
    from app.platform import service_reminders

    return service_reminders.set_cycle(
        body.client_id,
        body.customer,
        body.service,
        body.interval_days,
        last_service_date=body.last_service_date or "",
    )


@router.get("/service-due")
async def service_due(
    days_ahead: int = Query(3, ge=0, le=60),
    client_id: str = Query("", max_length=64),
    _user=Depends(require_admin),
):
    """Due/jaldi-due service cycles (+ saved cycles list)."""
    from app.platform import service_reminders

    return {
        "ok": True,
        "due": service_reminders.due(days_ahead=days_ahead),
        "cycles": service_reminders.list_cycles(client_id or None),
    }


@router.post("/service-run")
async def service_run(days_ahead: int = Query(3, ge=0, le=60), _user=Depends(require_admin)):
    """Due cycles → Hinglish WA reminder DRAFTS (1-click wa.me; auto-send KABHI nahi)."""
    from app.platform import service_reminders

    return await asyncio.to_thread(service_reminders.run_due, days_ahead)


# ----------------- F4: long video → short clips (HEAVY, bg job) -------------- #
@router.post("/clips")
async def start_clips(
    file: UploadFile | None = File(None),
    path: str = Form(""),
    n: int = Form(3),
    duration: int = Form(30),
    vertical: bool = Form(True),
    _user=Depends(require_admin),
):
    """Lambi video → N short 9:16 clips. BACKGROUND daemon thread (kabhi inline
    nahi) — turant job_id milta hai, status GET /clips/{job_id}."""
    from app.marketing import video_clips

    avail = video_clips.available()
    if not avail.get("ok"):
        return {
            "ok": False,
            "reason": "ffmpeg_missing",
            "available": avail,
            "hint": "Server pe ffmpeg/ffprobe install karo.",
        }

    video_path = (path or "").strip()
    if file is not None and getattr(file, "filename", ""):
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in _VIDEO_EXTS:
            ext = ".mp4"
        os.makedirs(_UPLOAD_DIR, exist_ok=True)
        video_path = os.path.join(_UPLOAD_DIR, uuid.uuid4().hex[:12] + ext)
        size = 0
        try:
            # Resolved per request from the shared authority; invalid
            # configuration raises and is handled below as upload_failed
            # (fail closed - never fall back to a wider limit).
            cap = _upload_max_bytes()
            with open(video_path, "wb") as out:
                while True:
                    chunk = await file.read(1 << 20)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > cap:
                        raise ValueError(f"upload too large ({cap // (1024 * 1024)}MB cap)")
                    await asyncio.to_thread(out.write, chunk)
        except Exception as e:
            try:
                os.remove(video_path)
            except Exception:
                pass
            return {"ok": False, "reason": "upload_failed", "error": str(e)[:200]}

    if not video_path:
        return {"ok": False, "reason": "no_input", "error": "file upload karo ya path do"}

    return video_clips.start_clip_job(
        video_path, n=int(n), duration=int(duration), vertical=bool(vertical)
    )


@router.get("/clips/{job_id}")
async def clips_status(job_id: str, _user=Depends(require_admin)):
    """Clip job ka status (queued/running/done/error) + files."""
    from app.marketing import video_clips

    return video_clips.job_status(job_id)


@router.get("/clip-file/{job}/{name}", dependencies=[Depends(rate_limit("clipf", 60, 60))])
async def clip_file(job: str, name: str):
    """Bani clip serve (regex-locked — path traversal impossible)."""
    if not _SAFE_SEG_RE.match(job or "") or not _CLIP_NAME_RE.match(name or ""):
        raise HTTPException(status_code=404, detail="not found")
    path = os.path.join("data", "clips", job, name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(path, media_type="video/mp4", filename=name)


# ------------------------- F5: animated text GIF ----------------------------- #
class GifIn(BaseModel):
    text: str = ""
    slug: str = "default"
    style: str = "pulse"  # pulse | pop | blink


@router.post("/gif")
async def make_gif(body: GifIn, _user=Depends(require_admin)):
    """Brand-color animated text GIF (PIL) — to_thread + timeout (loop-safe)."""
    from app.marketing import gif_maker

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(gif_maker.make_gif, body.text, body.slug, body.style),
            timeout=25,
        )
    except asyncio.TimeoutError:
        return {"ok": False, "reason": "timeout"}


@router.get("/gif-presets")
async def gif_presets(_user=Depends(require_admin)):
    """Ready Hinglish GIF texts + styles."""
    from app.marketing import gif_maker

    return {"ok": True, "presets": gif_maker.PRESETS, "styles": ["pulse", "pop", "blink"]}


@router.get("/gif-file/{slug}/{name}", dependencies=[Depends(rate_limit("giff", 60, 60))])
async def gif_file(slug: str, name: str):
    """Bana GIF serve (regex-locked)."""
    if not _SAFE_SEG_RE.match(slug or "") or not _GIF_NAME_RE.match(name or ""):
        raise HTTPException(status_code=404, detail="not found")
    path = os.path.join("data", "gifs", slug, name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(path, media_type="image/gif", filename=name)


# ----------------------- F6: AI avatar video post ---------------------------- #
class AvatarVideoIn(BaseModel):
    topic: str
    niche: str = "general"
    slug: str = ""


@router.post("/avatar-video")
async def avatar_video(body: AvatarVideoIn, _user=Depends(require_admin)):
    """AI avatar/spokesperson video post — script + video URL + caption+tags
    (Pollinations video_url + post_generator REUSE). Key absent = graceful."""
    from app.marketing import avatar_video as av

    try:
        return await asyncio.wait_for(
            av.avatar_post(body.topic, niche=body.niche, slug=body.slug), timeout=45
        )
    except asyncio.TimeoutError:
        return {"ok": False, "reason": "timeout"}


# -------------------- F1: cold-email A/B variant stats ----------------------- #
@router.get("/outreach-variants")
async def outreach_variant_stats(_user=Depends(require_admin)):
    """Per-variant sends/replies/reply-rate + Laplace winner."""
    from app.marketing import outreach_variants

    return {"ok": True, **outreach_variants.stats()}


class VariantReplyIn(BaseModel):
    variant_id: str


@router.post("/outreach-variants/reply")
async def outreach_variant_reply(body: VariantReplyIn, _user=Depends(require_admin)):
    """Kisi variant pe reply aaya — record karo (winner stats sharpen)."""
    from app.marketing import outreach_variants

    outreach_variants.record_reply(body.variant_id)
    return {"ok": True, **outreach_variants.stats()}
