"""W1.4 — follow-up outreach must batch its store writes (no per-send full rewrite).

Bug: `run_email_followups` marked each successful follow-up with
`prospector.set_prospect_fields(pid, …)` — a full-file JSONL rewrite PER SEND. On a
7.6k-row store × up-to-25 sends that's the O(N²)/OOM pattern the initial
`run_email_outreach` path already fixed with `set_prospect_fields_bulk` + a pending
buffer (flush every 10 + once at the end).

Fix: follow-ups use the same bulk-mark buffer. A multi-send run must call
`set_prospect_fields_bulk` (batched) and NOT the per-send `set_prospect_fields`.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta


def _run(coro):
    return asyncio.run(coro)


def test_followups_write_via_bulk_not_per_send(monkeypatch):
    import app.platform.auto_outreach as ao
    from app.config import settings
    from app.platform import email_warmup, prospector

    old = (datetime.utcnow() - timedelta(days=5)).isoformat() + "Z"  # due for followup #1
    rows = [
        {
            "id": f"p{i}",
            "email": f"biz{i}@example.com",
            "business_name": f"Biz{i}",
            "status": "ready",
            "emailed_at": old,
            "followup_count": 0,
        }
        for i in range(3)
    ]

    calls = {"bulk": 0, "per_send": 0, "bulk_pids": []}

    def _bulk(marks):
        calls["bulk"] += 1
        calls["bulk_pids"].extend(marks.keys())

    def _single(pid, fields):
        calls["per_send"] += 1

    class _Sender:
        async def send_email(self, *a, **k):
            return True

    monkeypatch.setattr(ao, "_valid_email", lambda addr, **k: True)  # skip live MX lookup
    monkeypatch.setattr(prospector, "_read_all", lambda: [dict(r) for r in rows])
    monkeypatch.setattr(prospector, "set_prospect_fields_bulk", _bulk)
    monkeypatch.setattr(prospector, "set_prospect_fields", _single)
    monkeypatch.setattr(ao, "_followup_subject_body", lambda p, step: ("S", "t", "<p>h</p>"))
    monkeypatch.setattr(email_warmup, "effective_cap", lambda c: c)
    monkeypatch.setattr("app.integrations.email_api.api_available", lambda: True, raising=False)
    monkeypatch.setattr("app.integrations.email_sender.EmailSender", _Sender)
    monkeypatch.setattr(settings, "auto_email_outreach", True, raising=False)
    monkeypatch.setattr(ao, "_SLEEP_MIN_S", 0)  # no inter-send throttle in test
    monkeypatch.setattr(ao, "_SLEEP_MAX_S", 0)

    res = _run(ao.run_email_followups())

    assert res.get("sent") == 3, f"expected 3 followups sent, got {res}"
    assert calls["bulk"] >= 1, "followups must persist via set_prospect_fields_bulk (batched)"
    assert calls["per_send"] == 0, "followups must NOT do a per-send full-file rewrite"
    assert set(calls["bulk_pids"]) == {"p0", "p1", "p2"}
