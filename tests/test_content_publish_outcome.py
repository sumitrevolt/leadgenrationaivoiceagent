"""Publish-outcome truth on content items (CDOS spec: published_at) +
calendar status-color truth.

2026-07-07 audit finding: mark_item sirf status+updated_at set karta tha —
item record kabhi nahi batata tha post KAB publish hua (woh sirf
delivery_ledger event me tha), aur customer calendar ka color-code
"published" pe key karta tha jo queue me kabhi occur hi nahi hota
(asli success-status = "posted") → posted items draft-amber dikhte the.
"""

import json
import os
from pathlib import Path

from app.marketing import auto_content, delivery_ledger

TEMPLATE = Path(__file__).resolve().parents[1] / "frontend" / "customer_dashboard.html"


def _redirect(monkeypatch, tmp_path):
    monkeypatch.setattr(
        auto_content, "_QUEUE_DIR", lambda: os.path.join(str(tmp_path), "content_queue")
    )
    monkeypatch.setattr(
        delivery_ledger, "_LEDGER_DIR", lambda: os.path.join(str(tmp_path), "delivery_ledger")
    )
    monkeypatch.setattr(
        delivery_ledger, "_CONTENT_QUEUE_DIR", lambda: os.path.join(str(tmp_path), "content_queue")
    )


def _seed_item(cid: str, item_id: str = "it1", status: str = "approved"):
    path = auto_content._queue_path(cid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "id": item_id,
                    "client_id": cid,
                    "date": "2026-07-07",
                    "type": "post",
                    "title": "Test Post",
                    "caption": "Ek behtareen offer aaj hi le lo!",
                    "status": status,
                }
            )
            + "\n"
        )


def _read_item(cid: str, item_id: str) -> dict:
    for it in auto_content.list_queue(cid, limit=50):
        if it.get("id") == item_id:
            return it
    return {}


def test_mark_posted_sets_published_at(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    _seed_item("pub-c1")
    assert auto_content.mark_item("pub-c1", "it1", "posted") is True
    rec = _read_item("pub-c1", "it1")
    assert rec["status"] == "posted"
    assert rec.get("published_at"), "posted item pe published_at hona chahiye"
    assert rec["published_at"] == rec["updated_at"]


def test_mark_approved_does_not_set_published_at(monkeypatch, tmp_path):
    _redirect(monkeypatch, tmp_path)
    _seed_item("pub-c2", status="draft")
    assert auto_content.mark_item("pub-c2", "it1", "approved") is True
    rec = _read_item("pub-c2", "it1")
    assert rec["status"] == "approved"
    assert not rec.get("published_at")


def test_repeat_posted_keeps_original_published_at(monkeypatch, tmp_path):
    """Dubara posted mark karne par pehla publish timestamp overwrite na ho."""
    _redirect(monkeypatch, tmp_path)
    _seed_item("pub-c3")
    assert auto_content.mark_item("pub-c3", "it1", "posted") is True
    first = _read_item("pub-c3", "it1")["published_at"]
    assert auto_content.mark_item("pub-c3", "it1", "posted") is True
    assert _read_item("pub-c3", "it1")["published_at"] == first


def test_calendar_colors_cover_real_statuses():
    """Calendar JS asli queue statuses ko color kare — 'posted' success-color me
    (sirf dead 'published' key pe nahi) aur 'skipped' muted me."""
    html = TEMPLATE.read_text(encoding="utf-8")
    assert 'status === "published" || status === "posted"' in html
    assert 'status === "skipped"' in html
