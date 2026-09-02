"""W2.1 — validate content captions before they enter the draft queue.

`_append_items` wrote every generated item straight to the client's draft queue with
no output check, so a caption carrying a BANNED phrase (brand/compliance risk) or junk
length could reach a human's review queue. Fix: `_caption_ok` (length + `staff.BANNED`
reuse, fail-open) gates the write; failing items are skipped + logged.
"""

from __future__ import annotations

import app.agents.staff as staff
import app.marketing.auto_content as ac


def test_caption_ok_rules(monkeypatch):
    monkeypatch.setattr(staff, "BANNED", ["spammy"])
    assert ac._caption_ok({"caption": "A nice normal caption for a local shop."})[0] is True
    assert ac._caption_ok({"caption": ""})[0] is True  # poster/svg — no caption to check
    assert ac._caption_ok({"caption": "short"})[0] is False  # too short
    assert ac._caption_ok({"caption": "this is spammy stuff indeed"})[0] is False  # banned


def test_append_items_rejects_bad_caption(monkeypatch, tmp_path):
    monkeypatch.setattr(ac, "_QUEUE_DIR", lambda: str(tmp_path))
    monkeypatch.setattr(staff, "BANNED", ["guaranteed results"])
    items = [
        {
            "id": "1",
            "date": "2026-07-06",
            "type": "post",
            "caption": "This gives guaranteed results fast!",
            "status": "draft",
        },
        {"id": "2", "date": "2026-07-06", "type": "poster", "svg": "<svg/>", "status": "draft"},
        {
            "id": "3",
            "date": "2026-07-06",
            "type": "reel",
            "caption": "A perfectly fine caption for a local business today.",
            "status": "draft",
        },
    ]
    added = ac._append_items("client1", items)
    written = (tmp_path / "client1.jsonl").read_text(encoding="utf-8")
    assert added == 2, "banned-phrase item must NOT be queued"
    assert "guaranteed results" not in written
    assert '"id": "3"' in written and '"id": "2"' in written
