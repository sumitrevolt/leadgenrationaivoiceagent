"""Fail-closed contracts for Wave A4 customer-delivery stores.

These are NOT opt-out lists — the contract differs per store:

  * delivery.ledger  — unresolvable authority must REPORT FAILURE (writes
                       return False; reads raise). Empty-history silence is
                       corruption of the customer's SLA timeline.
  * content.approvals — unresolvable authority must NEVER read as approved.
  * content.queue     — degrading is fine; silent pass is not — log at ERROR.

Anti-vacuity tests prove the ordinary paths still work, so the fail-closed
branches are not the only ones exercised.
"""

from __future__ import annotations

import pytest

from app.marketing import auto_content, content_approval, delivery_ledger
from app.platform import runtime_data as rd

CID = "a4-failclosed-client"


def _explode(*_a, **_k):
    raise rd.RuntimeDataError("runtime root is configured but unusable")


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(auto_content, "_QUEUE_DIR", lambda: str(tmp_path / "content_queue"))
    monkeypatch.setattr(content_approval, "_FILE", lambda: str(tmp_path / "approvals.jsonl"))
    monkeypatch.setattr(delivery_ledger, "_LEDGER_DIR", lambda: str(tmp_path / "delivery_ledger"))
    monkeypatch.setattr(
        delivery_ledger, "_CONTENT_QUEUE_DIR", lambda: str(tmp_path / "content_queue")
    )
    yield


# ----------------------------------------------------------- delivery.ledger
def test_delivery_ledger_unresolvable_write_reports_failure(monkeypatch, caplog):
    monkeypatch.setattr(delivery_ledger, "_LEDGER_DIR", _explode)
    with caplog.at_level("ERROR"):
        assert delivery_ledger.log_event(CID, "post_draft_created", detail="x") is False
    assert any("UNRESOLVABLE" in (r.message or r.getMessage()) for r in caplog.records)


def test_delivery_ledger_unresolvable_read_raises(monkeypatch, caplog):
    monkeypatch.setattr(delivery_ledger, "_LEDGER_DIR", _explode)
    with caplog.at_level("ERROR"):
        with pytest.raises(rd.RuntimeDataError):
            delivery_ledger._read_events(CID)
    assert any("UNRESOLVABLE" in (r.message or r.getMessage()) for r in caplog.records)


def test_delivery_ledger_ordinary_path_still_works():
    """Anti-vacuity: fail-closed branches must not be the only ones exercised."""
    assert delivery_ledger.log_event(CID, "post_draft_created", detail="hello") is True
    events = delivery_ledger._read_events(CID)
    assert any(e.get("event") == "post_draft_created" for e in events)


# --------------------------------------------------------- content.approvals
def test_content_approvals_unresolvable_never_reads_as_approved(monkeypatch, caplog):
    monkeypatch.setattr(content_approval, "_FILE", _explode)
    with caplog.at_level("ERROR"):
        assert content_approval.get_by_token("any-token") is None
        assert content_approval.pending(CID) == []
        assert content_approval.list_all(CID) == []
    assert any("UNRESOLVABLE" in (r.message or r.getMessage()) for r in caplog.records)


def test_content_approvals_unresolvable_write_does_not_claim_success(monkeypatch, caplog):
    monkeypatch.setattr(content_approval, "_FILE", _explode)
    with caplog.at_level("ERROR"):
        out = content_approval.submit(CID, {"title": "x", "caption": "y"})
    assert out.get("ok") is False
    assert content_approval.pending(CID) == []
    assert any("UNRESOLVABLE" in (r.message or r.getMessage()) for r in caplog.records)


def test_content_approvals_ordinary_path_still_works():
    """Anti-vacuity."""
    sub = content_approval.submit(CID, {"title": "Approve me", "caption": "body"})
    assert sub.get("ok") is True
    token = str((sub.get("approval") or {}).get("token") or "")
    assert token
    assert content_approval.approve(token)["ok"] is True
    rec = content_approval.get_by_token(token)
    assert rec is not None
    assert rec.get("status") == "approved"


# ------------------------------------------------------------- content.queue
def test_content_queue_unresolvable_logs_error_and_degrades(monkeypatch, caplog):
    monkeypatch.setattr(auto_content, "_QUEUE_DIR", _explode)
    with caplog.at_level("ERROR"):
        assert auto_content.list_queue(CID) == []
        n, rows = auto_content._append_items_detailed(
            CID,
            [
                {
                    "id": "q1",
                    "date": "2099-01-01",
                    "type": "tip",
                    "title": "t",
                    "caption": "a caption long enough",
                    "status": "draft",
                }
            ],
        )
        assert n == 0
        assert rows == []
    assert any("UNRESOLVABLE" in (r.message or r.getMessage()) for r in caplog.records)


def test_content_queue_ordinary_path_still_works():
    """Anti-vacuity."""
    n, rows = auto_content._append_items_detailed(
        CID,
        [
            {
                "id": "q-ok",
                "date": "2099-01-02",
                "type": "tip",
                "title": "ok",
                "caption": "a caption long enough",
                "status": "draft",
            }
        ],
    )
    assert n == 1
    assert len(rows) == 1
    listed = auto_content.list_queue(CID)
    assert any(r.get("id") == "q-ok" for r in listed)
