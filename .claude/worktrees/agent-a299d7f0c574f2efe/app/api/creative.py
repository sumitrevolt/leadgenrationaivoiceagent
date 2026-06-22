"""Creative API — jingles + background removal (AdBanao-parity creative tools).

- POST /api/creative/jingle (admin) → 15-20s Hinglish radio-ad mp3 (free-LLM + EdgeTTS)
- GET  /api/creative/jingle-file/{name} (public, rate-limited, regex-locked serve)
- POST /api/creative/bg-remove (admin, multipart) → transparent PNG cutout (rembg lazy)
- GET  /api/creative/status (admin) → deps availability + supported langs

Sab additive + free-stack + never-raise (modules error dict dete). Mount:
`app.include_router(creative_router, prefix="/api")` (growth.py pattern).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/creative", tags=["Creative"])


# ------------------------------ Jingles (F1) ------------------------------ #
class JingleIn(BaseModel):
    business_name: str
    niche: str | None = "general"
    offer: str | None = ""
    lang: str | None = "hinglish"
    voice: str | None = None


@router.post("/jingle", dependencies=[Depends(rate_limit("jingle", 10, 60))])
async def create_jingle(body: JingleIn, _user=Depends(require_admin)):
    """Audio jingle banao — script (free-LLM) + EdgeTTS mp3. HEAVY-ish (~10-25s)."""
    from app.marketing import jingle

    res = await jingle.generate_jingle(
        body.niche or "general",
        body.business_name,
        offer=body.offer or "",
        lang=(body.lang or "hinglish"),
        voice=body.voice,
    )
    if res.get("ok") and res.get("name"):
        res["url"] = f"/api/creative/jingle-file/{res['name']}"
    return res


@router.get("/jingle-file/{name}", dependencies=[Depends(rate_limit("jinglef", 60, 60))])
async def jingle_file(name: str):
    """Jingle mp3 serve (public, filename regex-locked — ai-img-file pattern)."""
    from fastapi.responses import FileResponse as _FR

    from app.marketing import jingle

    p = jingle.safe_file_path(name)
    if not p:
        raise HTTPException(status_code=404, detail="not found")
    return _FR(p, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=604800"})


# -------------------------- Background removal (F2) ------------------------ #
@router.post("/bg-remove", dependencies=[Depends(rate_limit("bgrm", 10, 60))])
async def bg_remove_endpoint(file: UploadFile = File(...), _user=Depends(require_admin)):
    """Photo → transparent PNG cutout (1-click bg remove). rembg na ho to
    graceful JSON error (install = user decision, heavy dep)."""
    from fastapi.responses import JSONResponse, Response

    from app.marketing import bg_remove

    try:
        data = await file.read()
    except Exception:
        data = b""
    if not data:
        return JSONResponse(
            {"ok": False, "error": "photo missing — file choose karo."}, status_code=400
        )

    out = bg_remove.remove_bg(data)
    if isinstance(out, dict):
        return JSONResponse(out, status_code=200)
    return Response(
        content=out,
        media_type="image/png",
        headers={"Content-Disposition": 'inline; filename="cutout.png"'},
    )


# ------------------------------- Status ----------------------------------- #
@router.get("/status")
async def creative_status(_user=Depends(require_admin)):
    """Creative deps ka health — jingle/bg-remove availability + multilang langs."""
    out: dict = {}
    try:
        from app.marketing import jingle

        out["jingle"] = jingle.available()
    except Exception as e:
        out["jingle"] = {"ok": False, "error": str(e)[:120]}
    try:
        from app.marketing import bg_remove

        out["bg_remove"] = {"ok": bg_remove.available()}
    except Exception as e:
        out["bg_remove"] = {"ok": False, "error": str(e)[:120]}
    try:
        from app.marketing import multilang_post

        out["multilang_langs"] = multilang_post.supported_langs()
    except Exception:
        out["multilang_langs"] = []
    return out
