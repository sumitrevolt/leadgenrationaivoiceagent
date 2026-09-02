from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone


def test_call_recordings_sorted_by_call_time(tmp_path, monkeypatch):
    from app.api import call_recordings as cr

    day = "2026-06-22"
    day_dir = tmp_path / day
    day_dir.mkdir(parents=True)

    old_file = day_dir / "call_old.wav"
    new_file = day_dir / "call_new.wav"
    old_file.write_bytes(b"old")
    new_file.write_bytes(b"new")

    old_ts = datetime(2026, 6, 22, 10, 15, tzinfo=timezone.utc).timestamp()
    new_ts = datetime(2026, 6, 22, 10, 45, tzinfo=timezone.utc).timestamp()
    os.utime(old_file, (old_ts, old_ts))
    os.utime(new_file, (new_ts, new_ts))

    monkeypatch.setattr(cr, "_REC_DIR", lambda: str(tmp_path))

    out = asyncio.run(cr.list_recordings())
    assert out["total_sessions"] == 2
    assert out["dates"][0]["date"] == day
    sessions = out["dates"][0]["sessions"]
    assert sessions[0]["sid"] == "new"
    assert sessions[1]["sid"] == "old"
    assert sessions[0]["time"] == "16:15:00"
    assert sessions[1]["time"] == "15:45:00"
    assert "n" not in sessions[0]
