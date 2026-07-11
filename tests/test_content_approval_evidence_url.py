"""P0 evidence-hygiene tests for content_approval.update_evidence_url.

Ensures the narrow amendment method:
  - only runs on published records
  - preserves status / published_at / publish_channel / publication counters
  - is idempotent (same URL twice = no_change)
  - rejects blank / non-http(s) / oversized values
  - captures the previous URL in evidence_url_history for audit
  - emits an `evidence_amended` audit event (NOT a fresh `post_published`)
"""
from __future__ import annotations

import os
import tempfile

import pytest

from app.marketing import content_approval as ca, delivery_ledger as dl


@pytest.fixture()
def isolated_store(monkeypatch, tmp_path):
    """Redirect approval jsonl + ledger dir to a per-test tmp dir."""
    approvals_file = tmp_path / "content_approvals.jsonl"
    ledger_dir = tmp_path / "delivery_ledger"
    monkeypatch.setattr(ca, "_FILE", str(approvals_file))
    monkeypatch.setattr(dl, "_LEDGER_DIR", str(ledger_dir))
    yield tmp_path


def _seed_published_record(tmp_path, *, evidence_url="https://leadsgenai.in/x") -> str:
    """Write one published approval directly to the jsonl store."""
    import json
    approvals_file = os.path.join(str(tmp_path), "content_approvals.jsonl")
    aid = "test-aid-001"
    rec = {
        "id": aid,
        "client_id": "cust-a",
        "token": "tok-xyz",
        "status": "published",
        "publish_channel": "customer_dashboard",
        "published_at": "2026-07-11T10:00:00+00:00",
        "decided_at": "2026-07-11T09:59:00+00:00",
        "evidence_url": evidence_url,
        "content": {"id": "c1", "client_id": "cust-a", "type": "post", "title": "T"},
    }
    os.makedirs(os.path.dirname(approvals_file) or ".", exist_ok=True)
    with open(approvals_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return aid


def test_update_evidence_url_happy_path(isolated_store):
    aid = _seed_published_record(isolated_store)
    r = ca.update_evidence_url(
        aid,
        "https://leadsgenai.in/app/dashboard#delivery/opaque123",
        actor_id="admin",
        reason="pii_cleanup",
    )
    assert r["ok"] is True
    assert r["evidence_url"] == "https://leadsgenai.in/app/dashboard#delivery/opaque123"
    assert r["previous_evidence_url_captured_in_history"] is True

    latest = ca._latest_states()[aid]
    assert latest["status"] == "published", "status must be preserved"
    assert latest["published_at"] == "2026-07-11T10:00:00+00:00", "published_at must be preserved"
    assert latest["publish_channel"] == "customer_dashboard", "publish_channel must be preserved"
    assert latest["evidence_url"] == "https://leadsgenai.in/app/dashboard#delivery/opaque123"
    history = latest.get("evidence_url_history") or []
    assert len(history) == 1
    assert history[0]["old_url"] == "https://leadsgenai.in/x"
    assert history[0]["reason"] == "pii_cleanup"
    assert history[0]["actor_id"] == "admin"


def test_idempotent_same_url_returns_no_change(isolated_store):
    aid = _seed_published_record(isolated_store, evidence_url="https://leadsgenai.in/keep")
    r1 = ca.update_evidence_url(aid, "https://leadsgenai.in/keep")
    assert r1["ok"] is True
    assert r1.get("no_change") is True


def test_rejects_blank_url(isolated_store):
    aid = _seed_published_record(isolated_store)
    r = ca.update_evidence_url(aid, "")
    assert r["ok"] is False
    assert "blank" in r["error"].lower() or "required" in r["error"].lower()


def test_rejects_non_http(isolated_store):
    aid = _seed_published_record(isolated_store)
    r = ca.update_evidence_url(aid, "file:///etc/passwd")
    assert r["ok"] is False


def test_rejects_oversized_url(isolated_store):
    aid = _seed_published_record(isolated_store)
    big = "https://leadsgenai.in/" + "x" * 600
    r = ca.update_evidence_url(aid, big)
    assert r["ok"] is False


def test_refuses_on_non_published(isolated_store):
    """Only `published` records can have evidence_url amended."""
    import json
    aid = "pending-aid"
    approvals_file = os.path.join(str(isolated_store), "content_approvals.jsonl")
    with open(approvals_file, "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "id": aid, "client_id": "cust-a", "token": "t", "status": "pending",
            "content": {"id": "c1", "client_id": "cust-a"},
        }) + "\n")

    r = ca.update_evidence_url(aid, "https://leadsgenai.in/x")
    assert r["ok"] is False
    assert "published" in r["error"].lower()


def test_refuses_unknown_approval(isolated_store):
    r = ca.update_evidence_url("does-not-exist", "https://leadsgenai.in/x")
    assert r["ok"] is False


def test_no_publication_side_effects_fired(isolated_store, monkeypatch):
    """Rewrite must NOT call automation_log 'approval_published' nor emit a
    fresh `post_published` ledger event. Only an `evidence_amended` marker."""
    aid = _seed_published_record(isolated_store)
    ledger_calls = []

    def _spy_log_event(client_id, event, **kwargs):
        ledger_calls.append({"event": event, "client_id": client_id, **kwargs})
        return True

    monkeypatch.setattr(dl, "log_event", _spy_log_event)

    r = ca.update_evidence_url(aid, "https://leadsgenai.in/new")
    assert r["ok"] is True

    events = [c["event"] for c in ledger_calls]
    assert "post_published" not in events, "must NOT fire a fresh publication event"
    assert "evidence_amended" in events, "must emit audit marker"


def test_history_capped_at_5(isolated_store):
    aid = _seed_published_record(isolated_store)
    for i in range(8):
        r = ca.update_evidence_url(aid, f"https://leadsgenai.in/url-{i}", reason=f"r{i}")
        assert r["ok"] is True
    latest = ca._latest_states()[aid]
    history = latest.get("evidence_url_history") or []
    assert len(history) == 5, f"history should cap at 5, got {len(history)}"
    # newest entries retained
    assert history[-1]["reason"] == "r7"


def test_evidence_amended_is_customer_visible_false():
    """The audit event must be admin-only, never shown to customer."""
    label = dl.LABELS.get("evidence_amended")
    assert label is not None, "evidence_amended must be registered in LABELS"
    icon, customer_hi, admin_en, customer_visible = label
    assert customer_visible is False, "evidence_amended must be ops-only"
