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

from app.marketing import content_approval as ca
from app.marketing import delivery_ledger as dl


@pytest.fixture()
def isolated_store(monkeypatch, tmp_path):
    """Redirect approval jsonl + ledger dir to a per-test tmp dir."""
    approvals_file = tmp_path / "content_approvals.jsonl"
    ledger_dir = tmp_path / "delivery_ledger"
    monkeypatch.setattr(ca, "_FILE", lambda: str(approvals_file))
    monkeypatch.setattr(dl, "_LEDGER_DIR", lambda: str(ledger_dir))
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
    # AUDIT-HISTORY PRIVACY (2026-07-11 P0): raw old_url must NOT be retained.
    assert "old_url" not in history[0], "raw old_url must not survive in history"
    assert "old_url_fingerprint" in history[0]
    assert len(history[0]["old_url_fingerprint"]) == 16  # sha256[:16]
    assert "old_url_redacted" in history[0]
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
        f.write(
            json.dumps(
                {
                    "id": aid,
                    "client_id": "cust-a",
                    "token": "t",
                    "status": "pending",
                    "content": {"id": "c1", "client_id": "cust-a"},
                }
            )
            + "\n"
        )

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


# --------------------------------------------------------------------------- #
# Audit-history PRIVACY (2026-07-11 P0 evidence-history redaction loop)
# --------------------------------------------------------------------------- #


def test_history_never_contains_raw_client_id(isolated_store):
    """History must not retain a URL containing `client_id=<tenant>` — even
    though the field is called history, tenant-bearing raw URLs are still PII."""
    aid = _seed_published_record(
        isolated_store,
        evidence_url="https://leadsgenai.in/app/dashboard?client_id=jiya-makeover&item=x",
    )
    r = ca.update_evidence_url(aid, "https://leadsgenai.in/app/dashboard#delivery/x")
    assert r["ok"] is True

    latest = ca._latest_states()[aid]
    blob = str(latest.get("evidence_url_history") or [])
    assert "client_id=jiya-makeover" not in blob, "raw client_id survived in history!"
    assert "jiya-makeover" not in blob, "raw customer slug survived in history!"

    entry = latest["evidence_url_history"][0]
    # Redacted form still preserves scheme/host/path so the operator sees WHERE
    assert entry["old_url_redacted"].startswith("https://leadsgenai.in/")
    assert "[REDACTED]" in entry["old_url_redacted"]
    # Fingerprint is deterministic + non-reversible
    import hashlib

    expected = hashlib.sha256(
        b"https://leadsgenai.in/app/dashboard?client_id=jiya-makeover&item=x"
    ).hexdigest()[:16]
    assert entry["old_url_fingerprint"] == expected


def test_fingerprint_deterministic():
    """Same URL always yields the same fingerprint (forensic comparison)."""
    a = ca._fingerprint_url("https://leadsgenai.in/x?client_id=foo")
    b = ca._fingerprint_url("https://leadsgenai.in/x?client_id=foo")
    assert a == b
    assert len(a) == 16
    # Different URLs → different fingerprints
    c = ca._fingerprint_url("https://leadsgenai.in/x?client_id=bar")
    assert a != c


def test_redact_url_covers_all_sensitive_keys():
    """The redactor must strip common tenant/PII query keys."""
    url = "https://leadsgenai.in/x?client_id=t1&email=a@b.com&token=secret&keep=this"
    redacted = ca._redact_url_for_audit(url)
    for forbidden in ("t1", "a@b.com", "secret"):
        assert forbidden not in redacted
    assert "keep=this" in redacted, "non-sensitive keys must be preserved"


# --------------------------------------------------------------------------- #
# migrate_evidence_urls tests
# --------------------------------------------------------------------------- #


def _seed_multiple_records(tmp_path, records):
    import json

    approvals_file = os.path.join(str(tmp_path), "content_approvals.jsonl")
    os.makedirs(os.path.dirname(approvals_file) or ".", exist_ok=True)
    with open(approvals_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def test_migration_dry_run_reports_counts_without_mutating(isolated_store):
    _seed_multiple_records(
        isolated_store,
        [
            {
                "id": "a1",
                "client_id": "cust-a",
                "token": "t1",
                "status": "published",
                "publish_channel": "customer_dashboard",
                "published_at": "2026-07-11T10:00:00+00:00",
                "evidence_url": "https://leadsgenai.in/x?client_id=cust-a&item=a1",
                "content": {"id": "c1", "client_id": "cust-a"},
            },
            {
                "id": "b1",
                "client_id": "cust-b",
                "token": "t2",
                "status": "published",
                "publish_channel": "customer_dashboard",
                "published_at": "2026-07-11T10:00:00+00:00",
                "evidence_url": "https://leadsgenai.in/app/dashboard#delivery/b1",  # already clean
                "content": {"id": "c2", "client_id": "cust-b"},
            },
        ],
    )

    r = ca.migrate_evidence_urls(dry_run=True)
    assert r["dry_run"] is True
    assert r["records_scanned"] == 2
    assert r["active_urls_matched"] == 1  # only a1
    assert r["already_clean"] == 1  # b1
    assert r["active_urls_rewritten"] == 0, "dry-run must not mutate"

    # Confirm no mutation
    latest = ca._latest_states()
    assert "client_id=cust-a" in latest["a1"]["evidence_url"]


def test_migration_execute_rewrites_and_is_idempotent(isolated_store):
    _seed_multiple_records(
        isolated_store,
        [
            {
                "id": "a1",
                "client_id": "cust-a",
                "token": "t1",
                "status": "published",
                "publish_channel": "customer_dashboard",
                "published_at": "2026-07-11T10:00:00+00:00",
                "evidence_url": "https://leadsgenai.in/x?client_id=cust-a&item=a1",
                "content": {"id": "c1", "client_id": "cust-a"},
            },
        ],
    )

    r = ca.migrate_evidence_urls(dry_run=False)
    assert r["active_urls_rewritten"] == 1
    assert r["failed"] == 0

    # No PII in active URL
    latest = ca._latest_states()
    assert "client_id=" not in latest["a1"]["evidence_url"]
    assert "cust-a" not in latest["a1"]["evidence_url"]
    assert latest["a1"]["status"] == "published", "status must be preserved"
    assert latest["a1"]["published_at"] == "2026-07-11T10:00:00+00:00", (
        "timestamp must be preserved"
    )

    # Idempotent: re-run should produce 0 new rewrites
    r2 = ca.migrate_evidence_urls(dry_run=False)
    assert r2["active_urls_rewritten"] == 0
    assert r2["already_clean"] == 1


def test_migration_scope_by_client_id(isolated_store):
    _seed_multiple_records(
        isolated_store,
        [
            {
                "id": "a1",
                "client_id": "cust-a",
                "token": "t1",
                "status": "published",
                "publish_channel": "customer_dashboard",
                "published_at": "2026-07-11T10:00:00+00:00",
                "evidence_url": "https://leadsgenai.in/x?client_id=cust-a&item=a1",
                "content": {"id": "c1", "client_id": "cust-a"},
            },
            {
                "id": "b1",
                "client_id": "cust-b",
                "token": "t2",
                "status": "published",
                "publish_channel": "customer_dashboard",
                "published_at": "2026-07-11T10:00:00+00:00",
                "evidence_url": "https://leadsgenai.in/x?client_id=cust-b&item=b1",
                "content": {"id": "c2", "client_id": "cust-b"},
            },
        ],
    )

    r = ca.migrate_evidence_urls(dry_run=False, client_id="cust-a")
    assert r["records_scanned"] == 1  # scope filtered to cust-a
    assert r["active_urls_rewritten"] == 1

    latest = ca._latest_states()
    assert "cust-a" not in latest["a1"]["evidence_url"]
    assert "cust-b" in latest["b1"]["evidence_url"], "cust-b unchanged (out of scope)"


def test_migration_migrates_legacy_history_entries(isolated_store):
    """Pre-2026-07-11 history entries had `old_url` field with raw URL. Migrate
    to fingerprint + redacted form."""
    _seed_multiple_records(
        isolated_store,
        [
            {
                "id": "a1",
                "client_id": "cust-a",
                "token": "t1",
                "status": "published",
                "publish_channel": "customer_dashboard",
                "published_at": "2026-07-11T10:00:00+00:00",
                "evidence_url": "https://leadsgenai.in/app/dashboard#delivery/a1",  # active already clean
                "evidence_url_history": [
                    {
                        "old_url": "https://leadsgenai.in/x?client_id=cust-a&item=a1",
                        "changed_at": "2026-07-11T09:00:00+00:00",
                        "actor_id": "admin",
                        "reason": "old",
                    },
                ],
                "content": {"id": "c1", "client_id": "cust-a"},
            },
        ],
    )

    r = ca.migrate_evidence_urls(dry_run=False)
    assert r["history_entries_matched"] == 1
    assert r["history_entries_redacted"] == 1

    latest = ca._latest_states()
    hist = latest["a1"]["evidence_url_history"][0]
    assert "old_url" not in hist, "legacy raw old_url must be removed"
    assert "old_url_fingerprint" in hist
    assert "old_url_redacted" in hist
    assert "client_id=cust-a" not in str(hist), "raw PII must be gone"


def test_migration_publication_counters_unchanged(isolated_store, monkeypatch):
    """Migration must not fire fresh post_published ledger events."""
    _seed_multiple_records(
        isolated_store,
        [
            {
                "id": "a1",
                "client_id": "cust-a",
                "token": "t1",
                "status": "published",
                "publish_channel": "customer_dashboard",
                "published_at": "2026-07-11T10:00:00+00:00",
                "evidence_url": "https://leadsgenai.in/x?client_id=cust-a&item=a1",
                "content": {"id": "c1", "client_id": "cust-a"},
            },
        ],
    )
    events = []
    monkeypatch.setattr(dl, "log_event", lambda cid, event, **kw: events.append(event) or True)

    r = ca.migrate_evidence_urls(dry_run=False)
    assert r["active_urls_rewritten"] == 1
    assert "post_published" not in events, "migration must NOT fire fresh publications"
    # But an evidence_amended audit marker is expected per rewrite
    assert events.count("evidence_amended") == 1


def test_evidence_amended_is_customer_visible_false():
    """The audit event must be admin-only, never shown to customer."""
    label = dl.LABELS.get("evidence_amended")
    assert label is not None, "evidence_amended must be registered in LABELS"
    icon, customer_hi, admin_en, customer_visible = label
    assert customer_visible is False, "evidence_amended must be ops-only"
