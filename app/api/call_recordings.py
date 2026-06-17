"""
Call Recordings API — Admin
===========================
GET /api/admin/call-recordings              → list recordings grouped by date
GET /api/admin/call-recordings/{date}/{fn}  → stream a WAV file (audio/wav)

Recordings are saved by vobiz_stream.py when VOBIZ_CALL_RECORD=1:
  data/call_recordings/YYYY-MM-DD/call_{sid}_caller.wav   (caller audio)
  data/call_recordings/YYYY-MM-DD/call_{sid}_bot.wav      (Swara TTS audio)

Auth: same pattern as admin_dashboard.py — admin token expected by the
HTML page (abAuthHdr), but no server-side FastAPI Depends (session-cookie
protected by the admin login page). Consistent with existing dashboard APIs.

Import-safe: never raises at import time.
"""

from __future__ import annotations

import os
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.auth_deps import require_admin

router = APIRouter(prefix="/api/admin/call-recordings", tags=["Call Recordings"])

_REC_DIR = os.path.join("data", "call_recordings")

# Strict allow-list patterns to prevent path traversal
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FILE_RE = re.compile(r"^call_[A-Za-z0-9_\-]+_(caller|bot)\.wav$")


def _get_size_kb(path: str) -> int:
    try:
        return os.path.getsize(path) // 1024
    except Exception:
        return 0


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
              "sid": "vb_abc123",
              "caller_wav": "call_vb_abc123_caller.wav",
              "bot_wav": "call_vb_abc123_bot.wav",
              "size_kb": 384
            }, ...
          ]
        }, ...
      ]
    }
    """
    if not os.path.isdir(_REC_DIR):
        return {"total_sessions": 0, "dates": []}

    dates_out: list[dict] = []

    try:
        day_names = sorted(
            (d for d in os.listdir(_REC_DIR) if _DATE_RE.match(d)),
            reverse=True,
        )
    except Exception:
        return {"total_sessions": 0, "dates": []}

    for date in day_names:
        day_dir = os.path.join(_REC_DIR, date)
        if not os.path.isdir(day_dir):
            continue

        sessions: dict[str, dict] = {}
        try:
            files = sorted(os.listdir(day_dir))
        except Exception:
            files = []

        for fname in files:
            if not _FILE_RE.match(fname):
                continue
            m = re.match(r"^call_(.+)_(caller|bot)\.wav$", fname)
            if not m:
                continue
            sid, side = m.group(1), m.group(2)
            if sid not in sessions:
                sessions[sid] = {
                    "sid": sid,
                    "caller_wav": None,
                    "bot_wav": None,
                    "size_kb": 0,
                }
            sessions[sid][f"{side}_wav"] = fname
            sessions[sid]["size_kb"] += _get_size_kb(os.path.join(day_dir, fname))

        if sessions:
            dates_out.append(
                {
                    "date": date,
                    "count": len(sessions),
                    "sessions": list(sessions.values()),
                }
            )

    total = sum(d["count"] for d in dates_out)
    return {"total_sessions": total, "dates": dates_out}


@router.get("/{date}/{filename}", summary="Stream a single WAV recording")
async def serve_recording(date: str, filename: str, _user=Depends(require_admin)):
    """Download / stream a call recording WAV file."""
    if not _DATE_RE.match(date):
        raise HTTPException(status_code=400, detail="Invalid date format (YYYY-MM-DD)")
    if not _FILE_RE.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")

    path = os.path.join(_REC_DIR, date, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Recording not found")

    return FileResponse(
        path=path,
        media_type="audio/wav",
        filename=filename,
        headers={"Accept-Ranges": "bytes"},
    )
