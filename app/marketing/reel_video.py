"""Faceless reel video gen — PIL frames + EdgeTTS Hinglish voiceover + ffmpeg = MP4.

Predis ka core differentiator (video) free-stack me. Ban-safe: file banta hai,
HUMAN upload karta hai (auto-publish nahi).

⚠️ HEAVY CPU job — web request me lamba chal sakta (3-5 slides ~20-40s). Scheduler me
kabhi UNGATED mat daalo; Celery worker me hi chalana (prod-down qa-job lesson).
Requires: ffmpeg binary + Pillow + edge-tts (sab pehle se stack me). `available()`
se check; missing = error dict, NEVER raises. Output: data/reels/<id>.mp4
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_OUT_DIR = os.path.join("data", "reels")
_W, _H = 720, 1280  # 9:16 reel
_VOICE = "hi-IN-SwaraNeural"


def available() -> dict[str, Any]:
    """Kya-kya मौजूद hai — ffmpeg/Pillow/edge-tts."""
    out = {"ffmpeg": bool(shutil.which("ffmpeg"))}
    try:
        import PIL  # noqa: F401

        out["pillow"] = True
    except Exception:
        out["pillow"] = False
    try:
        import edge_tts  # noqa: F401

        out["edge_tts"] = True
    except Exception:
        out["edge_tts"] = False
    out["ok"] = all(out.values())
    return out


def _default_slides(business_name: str, niche: str, offer: str) -> list[str]:
    return [
        f"{business_name} — aapke area ka bharosemand {niche} expert",
        offer or "Is hafte special offer — abhi inquiry karo!",
        "Call ya WhatsApp karo — turant response milega",
    ]


def _make_frame(text: str, idx: int, brand: dict[str, Any], tmp: str) -> str:
    from PIL import Image, ImageDraw, ImageFont

    def _hex(c: str, d: tuple) -> tuple:
        try:
            c = c.lstrip("#")
            return tuple(int(c[i : i + 2], 16) for i in (0, 2, 4))
        except Exception:
            return d

    primary = (brand.get("colors") or {}).get("primary") or brand.get("primary") or "#2563eb"
    bg = _hex(primary, (37, 99, 235))
    img = Image.new("RGB", (_W, _H), bg)
    dr = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 52)
    except Exception:
        font = ImageFont.load_default()
    # word-wrap ~22 chars/line
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > 22:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    y = _H // 2 - len(lines) * 35
    for ln in lines[:8]:
        bb = dr.textbbox((0, 0), ln, font=font)
        dr.text(((_W - (bb[2] - bb[0])) / 2, y), ln, fill="white", font=font)
        y += 70
    path = os.path.join(tmp, f"frame{idx:02d}.png")
    img.save(path)
    return path


async def _tts(text: str, path: str) -> bool:
    try:
        import edge_tts

        await edge_tts.Communicate(text, _VOICE).save(path)
        return os.path.exists(path) and os.path.getsize(path) > 100
    except Exception as e:
        logger.warning(f"reel tts failed: {e}")
        return False


def _ffmpeg(args: list[str]) -> bool:
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", *args],
            capture_output=True,
            timeout=180,
        )
        return r.returncode == 0
    except Exception as e:
        logger.warning(f"ffmpeg failed: {e}")
        return False


async def build_reel(
    business_name: str,
    niche: str = "general",
    slides: list[str] | None = None,
    offer: str = "",
    client_id: str = "",
) -> dict[str, Any]:
    """3-5 slide faceless reel banao. Returns {path,...} ya {error}."""
    avail = available()
    if not avail["ok"]:
        missing = [k for k, v in avail.items() if k != "ok" and not v]
        return {"error": f"missing deps: {', '.join(missing)}", "available": avail}

    slides = [s.strip() for s in (slides or []) if s and s.strip()][:5]
    if not slides:
        slides = _default_slides(business_name or "Aapka Business", niche, offer)

    brand: dict[str, Any] = {}
    try:
        from app.marketing import brand_kit

        brand = (brand_kit.get_brand(client_id) or {}) if client_id else {}
    except Exception:
        pass

    rid = uuid.uuid4().hex[:10]
    tmp = os.path.join(_OUT_DIR, f"tmp_{rid}")
    os.makedirs(tmp, exist_ok=True)
    out_path = os.path.join(_OUT_DIR, f"reel_{rid}.mp4")
    t0 = time.time()
    try:
        parts = []
        for i, text in enumerate(slides):
            frame = _make_frame(text, i, brand, tmp)
            audio = os.path.join(tmp, f"voice{i:02d}.mp3")
            seg = os.path.join(tmp, f"seg{i:02d}.mp4")
            has_audio = await _tts(text, audio)
            args = ["-loop", "1", "-i", frame]
            if has_audio:
                args += ["-i", audio, "-shortest", "-c:a", "aac"]
            else:
                args += ["-t", "4"]
            args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "24", seg]
            if not _ffmpeg(args):
                return {"error": f"ffmpeg segment {i} failed"}
            parts.append(seg)
        concat = os.path.join(tmp, "list.txt")
        with open(concat, "w") as f:
            for p in parts:
                f.write(f"file '{os.path.abspath(p)}'\n")
        if not _ffmpeg(["-f", "concat", "-safe", "0", "-i", concat, "-c", "copy", out_path]):
            return {"error": "ffmpeg concat failed"}
        size = os.path.getsize(out_path)
        return {
            "path": out_path,
            "slides": slides,
            "size_kb": size // 1024,
            "took_s": round(time.time() - t0, 1),
            "note": "Human upload karo (IG/FB/YT Shorts) — auto-publish nahi.",
        }
    except Exception as e:
        logger.warning(f"build_reel failed: {e}")
        return {"error": str(e)[:200]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
