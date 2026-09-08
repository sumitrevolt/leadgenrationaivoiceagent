"""Cadence run_due must not starve active leads behind leading ``done`` rows."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.marketing import cadence


def test_run_due_skips_leading_done_rows(tmp_path, monkeypatch):
    leads = tmp_path / "leads.jsonl"
    runs = tmp_path / "runs.jsonl"
    monkeypatch.setattr(cadence, "_LEADS", lambda: str(leads))
    monkeypatch.setattr(cadence, "_RUNS", lambda: str(runs))
    monkeypatch.setenv("CADENCE_ENGINE", "1")
    monkeypatch.setattr(
        cadence,
        "_execute_step",
        lambda *_a, **_k: asyncio.sleep(0, result={"ok": True, "channel": "email", "action": "x"}),
    )

    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=30)).isoformat()

    # 5 done rows first (prod shape) then 1 active still mid-sequence
    for i in range(5):
        cadence._append(
            cadence._LEADS(),
            {
                "id": f"done{i}",
                "business_name": f"Done {i}",
                "status": "done",
                "step_idx": 7,
                "enrolled_at": old,
            },
        )
    cadence._append(
        cadence._LEADS(),
        {
            "id": "active1",
            "business_name": "Active Biz",
            "status": "active",
            "step_idx": 2,
            "enrolled_at": old,
        },
    )

    # Bug regression: limit=5 used to only see the 5 done rows → advanced=0
    out = asyncio.run(cadence.run_due(limit=5))
    assert out["ok"] is True
    assert out["advanced"] >= 1
    assert out.get("examined_active", 0) >= 1

    rows = cadence._read(cadence._LEADS())
    active = next(r for r in rows if r["id"] == "active1")
    assert int(active.get("step_idx", 0)) > 2 or active.get("status") == "done"
