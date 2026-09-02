"""
Call Recordings API — Admin
===========================
GET /api/admin/call-recordings              → list recordings grouped by date
GET /api/admin/call-recordings/{date}/{fn}  → stream a WAV file (audio/wav)

Recordings are saved by vobiz_stream.py when VOBIZ_CALL_RECORD=1:
  data/call_recordings/YYYY-MM-DD/call_{sid}.wav   (mixed conversation)

Legacy (pre-merge): call_{sid}_caller.wav + call_{sid}_bot.wav still listed.

Import-safe: never raises at import time.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.auth_deps import require_admin

router = APIRouter(prefix="/api/admin/call-recordings", tags=["Call Recordings"])

_IST = timezone(timedelta(hours=5, minutes=30))


def _REC_DIR() -> str:
    """Call recordings root — resolved per call, never frozen at import."""
    from app.platform.runtime_recording_paths import call_recordings_dir

    return str(call_recordings_dir())


def _mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except Exception:
        return 0.0


def _fmt_ist(epoch: float) -> str:
    """File mtime (call end time) → HH:MM:SS IST. '' if unknown."""
    if not epoch:
        return ""
    try:
        return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(_IST).strftime("%H:%M:%S")
    except Exception:
        return ""


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Mixed conversation (primary)
_MERGED_RE = re.compile(r"^call_[A-Za-z0-9_\-]+\.wav$")
# Legacy split tracks
_LEGACY_RE = re.compile(r"^call_[A-Za-z0-9_\-]+_(caller|bot)\.wav$")
# Web test-call recordings (mixed mic+bot, browser MediaRecorder) served by the
# combined _SERVE_RE below — webm/mp4/ogg/wav. (Listed via the Web Test Calls
# admin view's recording_url, not double-counted in the phone "Call Recordings" tab.)
_SERVE_RE = re.compile(
    r"^(?:call_[A-Za-z0-9_\-]+(?:_(?:caller|bot))?\.wav|webcall_[A-Za-z0-9_\-]+\.(?:webm|mp4|ogg|wav))$"
)
_MEDIA_BY_EXT = {
    "wav": "audio/wav",
    "webm": "audio/webm",
    "mp4": "audio/mp4",
    "ogg": "audio/ogg",
}


def _get_size_kb(path: str) -> int:
    try:
        return os.path.getsize(path) // 1024
    except Exception:
        return 0


def _sid_from_merged(fname: str) -> str | None:
    m = re.match(r"^call_(.+)\.wav$", fname)
    if not m:
        return None
    sid = m.group(1)
    if sid.endswith("_caller") or sid.endswith("_bot"):
        return None
    return sid


@router.get("", summary="List call recordings grouped by date")
async def list_recordings(_user=Depends(require_admin)) -> dict:
    """
    Returns recording sessions grouped by date (newest first).

    Shape:
    {
      "total_sessions": 42,
      "dates": [
        {
          "date": "2026-06-17",
          "count": 5,
          "sessions": [
            {
              "sid": "cd512ca0-...",
              "wav": "call_cd512ca0-....wav",
              "caller_wav": null,
              "bot_wav": null,
              "size_kb": 384,
              "legacy_split": false
            }, ...
          ]
        }, ...
      ]
    }
    """
    if not os.path.isdir(_REC_DIR()):
        return {"total_sessions": 0, "dates": []}

    dates_out: list[dict] = []

    try:
        day_names = sorted(
            (d for d in os.listdir(_REC_DIR()) if _DATE_RE.match(d)),
            reverse=True,
        )
    except Exception:
        return {"total_sessions": 0, "dates": []}

    for date in day_names:
        day_dir = os.path.join(_REC_DIR(), date)
        if not os.path.isdir(day_dir):
            continue

        sessions: dict[str, dict] = {}
        try:
            # Chronological (call end time) — so the dashboard lists calls
            # serial-wise, not by random UUID filename.
            files = sorted(
                os.listdir(day_dir),
                key=lambda fn: _mtime(os.path.join(day_dir, fn)),
            )
        except Exception:
            files = []

        for fname in files:
            if _MERGED_RE.match(fname):
                sid = _sid_from_merged(fname)
                if not sid:
                    continue
                _mt = _mtime(os.path.join(day_dir, fname))
                if sid not in sessions:
                    sessions[sid] = {
                        "sid": sid,
                        "wav": fname,
                        "caller_wav": None,
                        "bot_wav": None,
                        "size_kb": 0,
                        "legacy_split": False,
                        "_mtime": _mt,
                        "time": _fmt_ist(_mt),
                    }
                sessions[sid]["wav"] = fname
                sessions[sid]["size_kb"] += _get_size_kb(os.path.join(day_dir, fname))
                continue

            if not _LEGACY_RE.match(fname):
                continue
            m = re.match(r"^call_(.+)_(caller|bot)\.wav$", fname)
            if not m:
                continue
            sid, side = m.group(1), m.group(2)
            _mt = _mtime(os.path.join(day_dir, fname))
            if sid not in sessions:
                sessions[sid] = {
                    "sid": sid,
                    "wav": None,
                    "caller_wav": None,
                    "bot_wav": None,
                    "size_kb": 0,
                    "legacy_split": True,
                    "_mtime": _mt,
                    "time": _fmt_ist(_mt),
                }
            sessions[sid][f"{side}_wav"] = fname
            sessions[sid]["legacy_split"] = sessions[sid].get("wav") is None
            sessions[sid]["size_kb"] += _get_size_kb(os.path.join(day_dir, fname))

        if sessions:
            # Newest call first so the dashboard reads by call time, not filename.
            ordered = sorted(
                sessions.values(),
                key=lambda s: (s.get("_mtime") or 0.0, s.get("sid") or ""),
                reverse=True,
            )
            for s in ordered:
                s.pop("_mtime", None)
            dates_out.append(
                {
                    "date": date,
                    "count": len(ordered),
                    "sessions": ordered,
                }
            )

    total = sum(d["count"] for d in dates_out)
    return {"total_sessions": total, "dates": dates_out}


@router.get("/{date}/{filename}", summary="Stream a single WAV recording")
async def serve_recording(date: str, filename: str, _user=Depends(require_admin)):
    """Download / stream a call recording WAV file."""
    if not _DATE_RE.match(date):
        raise HTTPException(status_code=400, detail="Invalid date format (YYYY-MM-DD)")
    if not _SERVE_RE.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")

    path = os.path.join(_REC_DIR(), date, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Recording not found")

    ext = filename.rsplit(".", 1)[-1].lower()
    return FileResponse(
        path=path,
        media_type=_MEDIA_BY_EXT.get(ext, "audio/wav"),
        filename=filename,
        headers={"Accept-Ranges": "bytes"},
    )
