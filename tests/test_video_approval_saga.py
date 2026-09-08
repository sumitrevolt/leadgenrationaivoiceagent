"""Stage 3A — coordinator, transaction identity, failure matrix, recovery.

Two JSONL stores cannot be written atomically. What is proven here is a
COMPENSATED RECOVERABLE SAGA: every durable step is recorded, no partial state
is publishable, and a retry resumes rather than duplicating.

Failures are injected by monkeypatching REAL I/O seams — production code
contains no test-only hooks.
"""

from __future__ import annotations

import hashlib

import pytest

from app.marketing.video_production import approval_saga as SAGA

# ruff: noqa: F811
from tests.test_video_preview_identity import preview_client  # noqa: F401


@pytest.fixture(autouse=True)
def _isolate_snapshot_root(tmp_path, monkeypatch):
    """Keep approved snapshots inside tmp — never the repo's real data/ dir."""
    from app.marketing import video_media_paths as vmp

    root = tmp_path / "approved"
    monkeypatch.setattr(vmp, "approved_media_dir", lambda: root)
    return root


BASE = {
    "tenant_id": "jiya-makeover",
    "record_id": "va-1",
    "revision": 0,
    "expected_sha256": "a" * 64,
    "actor_subject": "customer:jiya-makeover",
    "channel": "customer_dashboard",
}


# --- transaction identity ------------------------------------------------


def test_same_canonical_request_same_id():
    assert SAGA.transaction_id(**BASE) == SAGA.transaction_id(**BASE)


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", "other-tenant"),
        ("record_id", "va-2"),
        ("revision", 1),
        ("expected_sha256", "b" * 64),
        ("actor_subject", "admin:root"),
        ("channel", "whatsapp"),
    ],
)
def test_material_difference_changes_id(field, value):
    assert SAGA.transaction_id(**{**BASE, field: value}) != SAGA.transaction_id(**BASE)


def test_delimiter_collision_is_impossible():
    """A pipe-joined identity would collide here; canonical JSON does not."""
    a = SAGA.transaction_id(**{**BASE, "tenant_id": "ab", "record_id": "c"})
    b = SAGA.transaction_id(**{**BASE, "tenant_id": "a", "record_id": "bc"})
    assert a != b
    c = SAGA.transaction_id(**{**BASE, "tenant_id": "a|b", "record_id": "c"})
    d = SAGA.transaction_id(**{**BASE, "tenant_id": "a", "record_id": "b|c"})
    assert c != d


def test_schema_is_versioned_in_the_hashed_payload(monkeypatch):
    first = SAGA.transaction_id(**BASE)
    monkeypatch.setattr(SAGA, "TXN_SCHEMA", SAGA.TXN_SCHEMA + 1)
    assert SAGA.transaction_id(**BASE) != first


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", ""),
        ("record_id", ""),
        ("actor_subject", ""),
        ("channel", ""),
        ("expected_sha256", "short"),
        ("revision", -1),
        ("actor_subject", "someone@example.com"),
        ("actor_subject", "/srv/data/x"),
    ],
)
def test_invalid_identity_fields_refused(field, value):
    with pytest.raises(ValueError):
        SAGA.transaction_id(**{**BASE, field: value})


# --- failure matrix through the real HTTP approve path -------------------


def _approve(c, digest, rev=0):
    return c.post(
        "/api/customer/videos/vid-preview-1/feedback",
        json={
            "action": "approve",
            "expected_revision": rev,
            "expected_content_sha256": digest,
        },
    )


def _rec():
    from app.marketing import video_ad_cycle as V

    return (V._latest() or {}).get("vid-preview-1") or {}


def _digest(artifact):
    return hashlib.sha256(artifact.read_bytes()).hexdigest()


def test_happy_path_reaches_finalized_and_emits_effects_once(preview_client, monkeypatch):
    c, artifact = preview_client
    from app.marketing import auto_content, delivery_ledger

    counts = {"enqueue": 0, "ledger": 0}
    monkeypatch.setattr(
        auto_content,
        "enqueue_approved",
        lambda *a, **k: counts.__setitem__("enqueue", counts["enqueue"] + 1),
    )
    monkeypatch.setattr(
        delivery_ledger,
        "log_event",
        lambda *a, **k: counts.__setitem__("ledger", counts["ledger"] + 1),
    )

    assert _approve(c, _digest(artifact)).status_code == 200
    rec = _rec()
    assert rec["approval_txn_state"] == SAGA.TXN_FINALIZED
    assert rec["approval_effects"] == SAGA.EFFECTS_EMITTED
    assert rec["approval_snapshot_sha256"] == _digest(artifact)
    assert counts == {"enqueue": 1, "ledger": 1}


def test_snapshot_failure_leaves_no_approval(preview_client, monkeypatch):
    c, artifact = preview_client
    import app.marketing.video_production.snapshot as snap_mod

    # Real seam: an unreadable filesystem makes admission fail closed.
    monkeypatch.setattr(snap_mod, "_disk_free_total", lambda p: (-1, -1))

    assert _approve(c, _digest(artifact)).status_code == 409
    rec = _rec()
    assert rec.get("approval_txn_state") in (None, "")
    assert rec.get("final_approved") is not True
    # INVERTED (Stage 3B-close). This asserted "no saga state == legacy path ==
    # publishable", which is precisely the hole the audit found: the publish
    # gate never called this function, so a legacy hash-only record published.
    # An absent transaction is now a refusal, which also matches this test's own
    # name — a failed snapshot must leave nothing publishable.
    assert SAGA.is_publishable(rec) is False


def test_decision_write_failure_compensates_and_is_not_publishable(preview_client, monkeypatch):
    c, artifact = preview_client
    from app.marketing import content_approval

    monkeypatch.setattr(
        content_approval,
        "_append",
        lambda *a, **k: (_ for _ in ()).throw(OSError("ledger down")),
    )
    assert _approve(c, _digest(artifact)).status_code == 409
    rec = _rec()
    assert rec["approval_txn_state"] == SAGA.TXN_COMPENSATED
    assert rec.get("final_approved") is not True
    assert SAGA.is_publishable(rec) is False


def test_finalize_failure_compensates(preview_client, monkeypatch):
    c, artifact = preview_client
    from app.marketing import video_ad_cycle as V

    monkeypatch.setattr(V, "record_approval", lambda *a, **k: {"ok": False, "error": "boom"})
    assert _approve(c, _digest(artifact)).status_code == 409
    rec = _rec()
    assert rec["approval_txn_state"] == SAGA.TXN_COMPENSATED
    assert SAGA.is_publishable(rec) is False


def test_effects_failure_marks_failed_and_retry_emits_exactly_once(preview_client, monkeypatch):
    c, artifact = preview_client
    from app.marketing import auto_content

    counts = {"enqueue": 0}
    boom = {"on": True}

    def _flaky(*a, **k):
        if boom["on"]:
            raise OSError("queue down")
        counts["enqueue"] += 1

    monkeypatch.setattr(auto_content, "enqueue_approved", _flaky)

    assert _approve(c, _digest(artifact)).status_code == 200  # finalized anyway
    rec = _rec()
    assert rec["approval_txn_state"] == SAGA.TXN_FINALIZED
    assert rec["approval_effects"] == SAGA.EFFECTS_FAILED

    boom["on"] = False
    assert SAGA.recover("vid-preview-1")["ok"] is True
    assert counts["enqueue"] == 1
    assert _rec()["approval_effects"] == SAGA.EFFECTS_EMITTED
    assert SAGA.recover("vid-preview-1")["action"] == "already_complete"
    assert counts["enqueue"] == 1  # retry does not re-emit


def test_identical_retry_is_idempotent_and_keeps_original_timestamp(preview_client):
    c, artifact = preview_client
    digest = _digest(artifact)
    assert _approve(c, digest).status_code == 200
    first = _rec()

    again = _approve(c, digest)
    assert again.status_code == 200
    after = _rec()
    assert after["approved_at"] == first["approved_at"]
    assert after["approval_txn"] == first["approval_txn"]


def test_conflicting_transaction_refuses_after_finalization(preview_client):
    c, artifact = preview_client
    assert _approve(c, _digest(artifact)).status_code == 200
    finalized = _rec()

    from app.marketing.video_production import approval_principal as P

    class _U:
        id = "someone-else"
        role = "super_admin"  # holds approve_customer_video_on_behalf

        def can_access_admin(self):
            return True

    out = SAGA.approve(
        record_id="vid-preview-1",
        expected_revision=0,
        expected_sha256=_digest(artifact),
        # A DIFFERENT principal => a different transaction id. Same tenant, so
        # the refusal proves transaction conflict rather than tenant mismatch.
        principal=P.from_admin_user(_U(), tenant_id="fixture-tenant-p"),
    )
    assert out["ok"] is False
    assert out["error"] == "approval_transaction_conflict"
    assert _rec()["approval_txn"] == finalized["approval_txn"]
    assert _rec()["approval_actor"] == finalized["approval_actor"]


def test_recover_prepared_without_decision_compensates(preview_client, monkeypatch):
    c, artifact = preview_client
    from app.marketing import content_approval

    real_append = content_approval._append
    monkeypatch.setattr(
        content_approval,
        "_append",
        lambda *a, **k: (_ for _ in ()).throw(OSError("ledger down")),
    )
    _approve(c, _digest(artifact))
    # Restore ONLY this seam (monkeypatch.undo() would also revert the
    # fixture's own patches, since both share the function-scoped instance).
    monkeypatch.setattr(content_approval, "_append", real_append)

    out = SAGA.recover("vid-preview-1")
    assert out["ok"] is True
    assert _rec()["approval_txn_state"] == SAGA.TXN_COMPENSATED
    assert SAGA.is_publishable(_rec()) is False
    assert SAGA.recover("vid-preview-1")["action"] == "already_compensated"


def test_no_provider_call_on_any_refusal(preview_client, monkeypatch):
    c, artifact = preview_client
    from app.marketing import postiz_publish as pp
    from app.marketing import video_ad_cycle as V

    calls = {"postiz": 0}

    async def _spy(*a, **k):
        calls["postiz"] += 1
        return {"sent": True}

    monkeypatch.setattr(pp, "publish_video", _spy, raising=False)
    monkeypatch.setattr(V, "record_approval", lambda *a, **k: {"ok": False, "error": "boom"})
    assert _approve(c, _digest(artifact)).status_code == 409
    assert calls == {"postiz": 0}
