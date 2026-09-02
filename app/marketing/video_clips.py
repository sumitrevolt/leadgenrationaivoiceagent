"""
video_clips.py — lambi video → short vertical clips (Simplified/Predis parity).
================================================================================

Client ki ek lambi video (shop tour, interview, event) se N evenly-spaced
short clips (default 30s, 9:16 1080x1920 reels-ready) — ffmpeg se. HEAVY:
event loop me KABHI inline nahi (prod-down lesson) — endpoint `start_clip_job`
use karta hai jo BACKGROUND daemon thread me kaam karta hai aur status
`data/clip_jobs.jsonl` me likhta hai (queued → running → done/error).

Public API (sab never-raise):
  - available()                          -> {"ffmpeg","ffprobe","ok"}
  - plan_segments(total_s, n, duration)  -> [(start, dur)] (first/last 5% skip)
  - make_clips(video_path, n=3, duration=30, vertical=True, job_id=None)
        SYNC + HEAVY — sirf background thread/worker se call karo.
  - start_clip_job(video_path, ...)      -> {"ok", "job_id"} (non-blocking)
  - job_status(job_id)                   -> latest status + files

Output: data/clips/<job_id>/clip_1.mp4 ... (serve: /api/contentplus/clip-file).
NOTE: STT/auto-subtitles jaan-bujhke SKIP (Groq whisper optional — alag pass).
Free stack: sirf ffmpeg/ffprobe binaries (VPS pe installed; missing = graceful
error dict, available() short-circuit).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_CLIPS_DIR = os.path.join("data", "clips")
_JOBS_PATH = os.path.join("data", "clip_jobs.jsonl")
_EDGE_SKIP = 0.05  # first/last 5% skip (intro/outro junk)
_FFMPEG_TIMEOUT_S = 240  # per clip hard timeout
_SAFE_JOB_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def available() -> dict[str, Any]:
    """ffmpeg + ffprobe binaries hain ya nahi (short-circuit check)."""
    ff = bool(shutil.which("ffmpeg"))
    fp = bool(shutil.which("ffprobe"))
    return {"ffmpeg": ff, "ffprobe": fp, "ok": ff and fp}


# --------------------------------------------------------------------------- #
# Planning (pure python — testable bina ffmpeg)
# --------------------------------------------------------------------------- #
def plan_segments(total_s: float, n: int = 3, duration: int = 30) -> list[tuple[float, float]]:
    """Evenly-spaced clip windows — first/last 5% skip. Never raises.

    Returns [(start_seconds, duration_seconds)], hamesha video bounds ke andar.
    """
    try:
        total = float(total_s or 0)
        n = max(1, min(int(n or 3), 10))
        dur = max(5, min(int(duration or 30), 120))
        if total <= 0:
            return []
        lo = total * _EDGE_SKIP
        hi = total * (1.0 - _EDGE_SKIP)
        usable = hi - lo
        if usable <= dur:
            # chhoti video — jitna hai utna hi (ek clip)
            return [(max(0.0, lo), max(1.0, min(dur, usable)))]
        out: list[tuple[float, float]] = []
        span = usable - dur  # last start ka headroom
        for i in range(n):
            start = lo + (span * i / max(n - 1, 1)) if n > 1 else lo + span / 2
            out.append((round(start, 2), float(dur)))
        return out
    except Exception as e:
        logger.debug(f"[video_clips] plan failed: {e}")
        return []


def _probe_duration(path: str) -> float | None:
    try:
        res = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return float((res.stdout or "").strip())
    except Exception as e:
        logger.warning(f"[video_clips] ffprobe failed: {e}")
        return None


# --------------------------------------------------------------------------- #
# Heavy worker (SYNC — sirf background thread se)
# --------------------------------------------------------------------------- #
def make_clips(
    video_path: str,
    n: int = 3,
    duration: int = 30,
    vertical: bool = True,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Video → N short clips (9:16 reels-ready agar vertical). SYNC + HEAVY —
    event loop me kabhi inline mat chalao. Never raises (error dicts)."""
    try:
        avail = available()
        if not avail["ok"]:
            return {
                "ok": False,
                "reason": "ffmpeg_missing",
                "available": avail,
                "hint": "VPS pe `apt install ffmpeg` — phir clips ban payenge.",
            }
        path = str(video_path or "").strip()
        if not path or not os.path.isfile(path):
            return {"ok": False, "reason": "file_not_found", "path": path}

        total = _probe_duration(path)
        if not total or total <= 1:
            return {"ok": False, "reason": "probe_failed", "path": path}

        segments = plan_segments(total, n=n, duration=duration)
        if not segments:
            return {"ok": False, "reason": "no_segments"}

        jid = job_id or uuid.uuid4().hex[:12]
        if not _SAFE_JOB_RE.match(jid):
            jid = uuid.uuid4().hex[:12]
        out_dir = os.path.join(_CLIPS_DIR, jid)
        os.makedirs(out_dir, exist_ok=True)

        vf = "crop=ih*9/16:ih,scale=1080:1920" if vertical else "scale=1280:-2"
        files: list[str] = []
        errors: list[str] = []
        for i, (start, dur) in enumerate(segments, start=1):
            out_file = os.path.join(out_dir, f"clip_{i}.mp4")
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                str(start),
                "-i",
                path,
                "-t",
                str(dur),
                "-vf",
                vf,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "26",
                "-c:a",
                "aac",
                "-b:a",
                "96k",
                "-movflags",
                "+faststart",
                out_file,
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=_FFMPEG_TIMEOUT_S)
                if (
                    res.returncode == 0
                    and os.path.isfile(out_file)
                    and os.path.getsize(out_file) > 0
                ):
                    files.append(os.path.basename(out_file))
                else:
                    errors.append((res.stderr or "ffmpeg fail")[:200])
            except Exception as e:
                errors.append(str(e)[:200])

        return {
            "ok": bool(files),
            "job_id": jid,
            "dir": out_dir,
            "files": files,
            "urls": [f"/api/contentplus/clip-file/{jid}/{f}" for f in files],
            "video_duration_s": round(total, 1),
            "errors": errors,
        }
    except Exception as e:  # absolute guard
        logger.warning(f"[video_clips] make_clips failed: {e}")
        return {"ok": False, "reason": "error", "error": str(e)[:200]}


# --------------------------------------------------------------------------- #
# Background job runner (daemon thread + jsonl status — NO Celery edits)
# --------------------------------------------------------------------------- #
def _append_job(job_id: str, status: str, extra: dict[str, Any] | None = None) -> None:
    try:
        os.makedirs(os.path.dirname(_JOBS_PATH) or ".", exist_ok=True)
        rec = {
            "job_id": job_id,
            "status": status,
            "ts": datetime.now(timezone.utc).isoformat(),
            **(extra or {}),
        }
        with open(_JOBS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[video_clips] job log failed: {e}")


def _run_job(job_id: str, video_path: str, n: int, duration: int, vertical: bool) -> None:
    _append_job(job_id, "running", {"path": video_path})
    try:
        res = make_clips(video_path, n=n, duration=duration, vertical=vertical, job_id=job_id)
        if res.get("ok"):
            _append_job(job_id, "done", {"files": res.get("files"), "urls": res.get("urls")})
        else:
            _append_job(job_id, "error", {"reason": res.get("reason"), "errors": res.get("errors")})
    except Exception as e:  # never propagate out of thread
        _append_job(job_id, "error", {"reason": "exception", "error": str(e)[:200]})


def start_clip_job(
    video_path: str, n: int = 3, duration: int = 30, vertical: bool = True
) -> dict[str, Any]:
    """Background daemon thread me clip job shuru karo (NON-blocking).
    Status: job_status(job_id) / data/clip_jobs.jsonl. Never raises."""
    try:
        avail = available()
        if not avail["ok"]:
            return {"ok": False, "reason": "ffmpeg_missing", "available": avail}
        path = str(video_path or "").strip()
        if not path or not os.path.isfile(path):
            return {"ok": False, "reason": "file_not_found", "path": path}
        job_id = uuid.uuid4().hex[:12]
        _append_job(job_id, "queued", {"path": path, "n": int(n), "duration": int(duration)})
        t = threading.Thread(
            target=_run_job,
            args=(job_id, path, int(n), int(duration), bool(vertical)),
            daemon=True,
            name=f"clipjob-{job_id}",
        )
        t.start()
        return {
            "ok": True,
            "job_id": job_id,
            "status": "queued",
            "status_url": f"/api/contentplus/clips/{job_id}",
        }
    except Exception as e:
        logger.warning(f"[video_clips] start_clip_job failed: {e}")
        return {"ok": False, "reason": "error", "error": str(e)[:200]}


def job_status(job_id: str) -> dict[str, Any]:
    """Job ka latest status + bani files. Never raises."""
    jid = str(job_id or "").strip()
    if not _SAFE_JOB_RE.match(jid):
        return {"ok": False, "reason": "bad_job_id"}
    last: dict[str, Any] | None = None
    try:
        if os.path.isfile(_JOBS_PATH):
            with open(_JOBS_PATH, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    if r.get("job_id") == jid:
                        last = r
    except Exception as e:
        logger.warning(f"[video_clips] job_status failed: {e}")
    if not last:
        return {"ok": False, "reason": "not_found", "job_id": jid}
    # disk se files (done ke baad bhi fresh list)
    files: list[str] = []
    try:
        d = os.path.join(_CLIPS_DIR, jid)
        if os.path.isdir(d):
            files = sorted(f for f in os.listdir(d) if f.endswith(".mp4"))
    except Exception:
        pass
    return {
        "ok": True,
        "job_id": jid,
        "status": last.get("status"),
        "files": files,
        "urls": [f"/api/contentplus/clip-file/{jid}/{f}" for f in files],
        "detail": {k: v for k, v in last.items() if k not in {"job_id", "status"}},
    }


__all__ = [
    "available",
    "plan_segments",
    "make_clips",
    "start_clip_job",
    "job_status",
]
