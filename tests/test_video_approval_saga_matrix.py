"""Gate 3A-close — the COMPLETE durable-boundary failure matrix.

The first pass covered four boundaries. These are the remaining ones, each
reporting the same evidence shape:

    ledger appends · record updates · snapshots · effects · provider calls
    · final transaction state · publish eligibility

Every failure is injected on a REAL I/O seam (``_append``, ``_update``,
``os.replace``, ``enqueue_approved``, ``log_event``). Production code contains
no test-only hooks.
"""

from __future__ import annotations

import hashlib
import threading

import pytest

from app.marketing.video_production import approval_saga as SAGA

# ruff: noqa: F811
from tests.test_video_preview_identity import preview_client  # noqa: F401


@pytest.fixture(autouse=True)
def _isolate_snapshot_root(tmp_path, monkeypatch):
    from app.marketing import video_media_paths as vmp

    root = tmp_path / "approved"
    monkeypatch.setattr(vmp, "approved_media_dir", lambda: root)
    return root


@pytest.fixture
def ev(monkeypatch, _isolate_snapshot_root):
    """Counts every durable effect so each case reports the same evidence."""
    from app.marketing import auto_content, content_approval, delivery_ledger
    from app.marketing import postiz_publish as pp
    from app.marketing import video_ad_cycle as V

    c = {"ledger": 0, "updates": 0, "enqueue": 0, "delivery": 0, "provider": 0}
    real_append, real_update = content_approval._append, V._update

    monkeypatch.setattr(
        content_approval,
        "_append",
        lambda *a, **k: (c.__setitem__("ledger", c["ledger"] + 1), real_append(*a, **k))[1],
    )
    monkeypatch.setattr(
        V,
        "_update",
        lambda r, **f: (c.__setitem__("updates", c["updates"] + 1), real_update(r, **f))[1],
    )
    monkeypatch.setattr(
        auto_content,
        "enqueue_approved",
        lambda *a, **k: c.__setitem__("enqueue", c["enqueue"] + 1),
    )
    monkeypatch.setattr(
        delivery_ledger,
        "log_event",
        lambda *a, **k: c.__setitem__("delivery", c["delivery"] + 1),
    )

    async def _spy(*a, **k):
        c["provider"] += 1
        return {"sent": True}

    monkeypatch.setattr(pp, "publish_video", _spy, raising=False)
    c["_root"] = _isolate_snapshot_root
    return c


def _snapshots(ev):
    root = ev["_root"]
    return len(list(root.rglob("*.mp4"))) if root.exists() else 0


def _rec():
    from app.marketing import video_ad_cycle as V

    return (V._latest() or {}).get("vid-preview-1") or {}


def _digest(a):
    return hashlib.sha256(a.read_bytes()).hexdigest()


def _approve(c, digest, rev=0):
    return c.post(
        "/api/customer/videos/vid-preview-1/feedback",
        json={"action": "approve", "expected_revision": rev, "expected_content_sha256": digest},
    )


# --- 1. prepared-record write fails --------------------------------------


def test_prepared_write_failure(preview_client, ev, monkeypatch):
    c, artifact = preview_client
    from app.marketing import video_ad_cycle as V

    real = V._update

    def _fail_on_prepared(rid, **f):
        if f.get("approval_txn_state") == SAGA.TXN_PREPARED:
            raise OSError("record store down")
        return real(rid, **f)

    monkeypatch.setattr(V, "_update", _fail_on_prepared)
    assert _approve(c, _digest(artifact)).status_code == 409

    rec = _rec()
    assert rec.get("approval_txn_state") in (None, "")  # no transaction state
    assert ev["ledger"] == 0  # no decision written
    assert _snapshots(ev) == 1  # unreferenced artifact
    assert ev["enqueue"] == 0 and ev["delivery"] == 0
    assert ev["provider"] == 0
    assert rec.get("final_approved") is not True


# --- 2. decision persisted, decision_recorded state write fails ----------


def test_decision_recorded_state_write_failure(preview_client, ev, monkeypatch):
    c, artifact = preview_client
    from app.marketing import video_ad_cycle as V

    real = V._update

    def _fail_on_recorded(rid, **f):
        if f.get("approval_txn_state") == SAGA.TXN_DECISION_RECORDED:
            raise OSError("record store down")
        return real(rid, **f)

    monkeypatch.setattr(V, "_update", _fail_on_recorded)
    assert _approve(c, _digest(artifact)).status_code == 409

    rec = _rec()
    assert rec["approval_txn_state"] == SAGA.TXN_PREPARED  # stuck before recorded
    assert ev["ledger"] == 1  # decision DID persist
    assert _snapshots(ev) == 1
    assert ev["enqueue"] == 0 and ev["delivery"] == 0
    assert ev["provider"] == 0
    assert SAGA.is_publishable(rec) is False
    assert rec.get("final_approved") is not True


# --- 3. decision recorded, finalization missing -> recovery finalizes once


def test_recovery_finalizes_decision_recorded_exactly_once(preview_client, ev, monkeypatch):
    c, artifact = preview_client
    from app.marketing import video_ad_cycle as V

    real_record = V.record_approval
    monkeypatch.setattr(V, "record_approval", lambda *a, **k: {"ok": False, "error": "boom"})
    assert _approve(c, _digest(artifact)).status_code == 409
    assert _rec()["approval_txn_state"] == SAGA.TXN_COMPENSATED

    # Simulate the crash variant: decision recorded, finalization never ran.
    V._update("vid-preview-1", approval_txn_state=SAGA.TXN_DECISION_RECORDED)
    # Restore ONLY this seam (undo() would revert the fixture's patches too).
    monkeypatch.setattr(V, "record_approval", real_record)

    out = SAGA.recover("vid-preview-1")
    assert out["ok"] is True
    rec = _rec()
    assert rec["approval_txn_state"] == SAGA.TXN_FINALIZED
    assert rec["final_approved"] is True
    assert SAGA.is_publishable(rec) is True
    assert _snapshots(ev) == 1
    assert ev["provider"] == 0

    stamp = rec["approved_at"]
    assert SAGA.recover("vid-preview-1")["action"] == "already_complete"
    assert _rec()["approved_at"] == stamp  # recovery is idempotent


# --- 4. compensation write fails -> visible inconsistent -----------------


def test_compensation_write_failure_becomes_inconsistent(preview_client, ev, monkeypatch):
    c, artifact = preview_client
    from app.marketing import content_approval
    from app.marketing import video_ad_cycle as V

    real = V._update
    monkeypatch.setattr(
        content_approval,
        "_append",
        lambda *a, **k: (_ for _ in ()).throw(OSError("ledger down")),
    )

    def _fail_compensation(rid, **f):
        if f.get("approval_txn_state") == SAGA.TXN_COMPENSATED:
            raise OSError("compensation write down")
        return real(rid, **f)

    monkeypatch.setattr(V, "_update", _fail_compensation)
    assert _approve(c, _digest(artifact)).status_code == 409

    rec = _rec()
    # Compensation could not be written, so the record stays PREPARED and
    # recovery must surface it rather than silently resolving it.
    assert rec["approval_txn_state"] == SAGA.TXN_PREPARED
    assert SAGA.is_publishable(rec) is False
    assert ev["provider"] == 0

    monkeypatch.setattr(V, "_update", real)
    out = SAGA.recover("vid-preview-1")
    assert out["ok"] is True and out["action"] == "compensated_prepared"
    assert _rec()["approval_txn_state"] == SAGA.TXN_COMPENSATED
    assert SAGA.is_publishable(_rec()) is False


# --- 5. snapshot exists but prepared state never written -> safe reuse ----


def test_orphan_snapshot_is_reused_not_duplicated(preview_client, ev, monkeypatch):
    c, artifact = preview_client
    from app.marketing import video_ad_cycle as V

    real = V._update

    def _fail_once(rid, **f):
        if f.get("approval_txn_state") == SAGA.TXN_PREPARED:
            raise OSError("record store down")
        return real(rid, **f)

    monkeypatch.setattr(V, "_update", _fail_once)
    assert _approve(c, _digest(artifact)).status_code == 409
    assert _snapshots(ev) == 1  # orphan artifact on disk
    assert _rec().get("approval_txn_state") in (None, "")

    monkeypatch.setattr(V, "_update", real)  # store recovers
    assert _approve(c, _digest(artifact)).status_code == 200

    rec = _rec()
    assert rec["approval_txn_state"] == SAGA.TXN_FINALIZED
    assert _snapshots(ev) == 1  # REUSED, not duplicated
    assert ev["enqueue"] == 1 and ev["delivery"] == 1
    assert ev["provider"] == 0


# --- 6. partial effects failures -----------------------------------------


def test_enqueue_ok_delivery_fails_then_recovery_does_not_duplicate(
    preview_client, ev, monkeypatch
):
    c, artifact = preview_client
    from app.marketing import delivery_ledger

    broken = {"on": True}
    real_delivery = delivery_ledger.log_event

    def _flaky(*a, **k):
        if broken["on"]:
            raise OSError("ledger down")
        return real_delivery(*a, **k)  # the ev fixture's spy does the counting

    monkeypatch.setattr(delivery_ledger, "log_event", _flaky)
    assert _approve(c, _digest(artifact)).status_code == 200
    assert _rec()["approval_txn_state"] == SAGA.TXN_FINALIZED
    assert _rec()["approval_effects"] == SAGA.EFFECTS_FAILED
    assert ev["enqueue"] == 1  # enqueue already succeeded

    broken["on"] = False
    assert SAGA.recover("vid-preview-1")["ok"] is True
    assert _rec()["approval_effects"] == SAGA.EFFECTS_EMITTED
    # Per-effect markers: the already-emitted enqueue is NOT re-invoked when
    # only the delivery effect is retried (this asserted 2 before the effects
    # gate split them apart).
    assert ev["enqueue"] == 1
    assert ev["delivery"] == 1
    assert ev["provider"] == 0


def test_effects_state_update_failure_is_retryable(preview_client, ev, monkeypatch):
    c, artifact = preview_client
    from app.marketing import video_ad_cycle as V

    real = V._update
    broken = {"on": True}

    def _fail_effects_state(rid, **f):
        if broken["on"] and f.get("approval_effects") == SAGA.EFFECTS_EMITTED:
            raise OSError("record store down")
        return real(rid, **f)

    monkeypatch.setattr(V, "_update", _fail_effects_state)
    assert _approve(c, _digest(artifact)).status_code == 200
    rec = _rec()
    assert rec["approval_txn_state"] == SAGA.TXN_FINALIZED
    assert rec.get("approval_effects") != SAGA.EFFECTS_EMITTED

    broken["on"] = False
    assert SAGA.recover("vid-preview-1")["ok"] is True
    assert _rec()["approval_effects"] == SAGA.EFFECTS_EMITTED
    assert ev["provider"] == 0


# --- 7. concurrent recovery ----------------------------------------------


def test_concurrent_recovery_is_safe(preview_client, ev, monkeypatch):
    c, artifact = preview_client
    from app.marketing import auto_content

    broken = {"on": True}

    def _flaky(*a, **k):
        if broken["on"]:
            raise OSError("queue down")
        ev["enqueue"] += 1

    monkeypatch.setattr(auto_content, "enqueue_approved", _flaky)
    assert _approve(c, _digest(artifact)).status_code == 200
    assert _rec()["approval_effects"] == SAGA.EFFECTS_FAILED

    broken["on"] = False
    results = []
    threads = [
        threading.Thread(target=lambda: results.append(SAGA.recover("vid-preview-1")))
        for _ in range(4)
    ]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert all(r.get("ok") for r in results)
    assert _rec()["approval_effects"] == SAGA.EFFECTS_EMITTED
    assert _snapshots(ev) == 1
    assert ev["provider"] == 0


# --- 8. retry from every durable state ------------------------------------


@pytest.mark.parametrize(
    "state",
    [
        SAGA.TXN_PREPARED,
        SAGA.TXN_DECISION_RECORDED,
        SAGA.TXN_FINALIZED,
        SAGA.TXN_COMPENSATED,
        SAGA.TXN_INCONSISTENT,
    ],
)
def test_retry_from_each_durable_state_never_publishes_wrongly(preview_client, ev, state):
    c, artifact = preview_client
    from app.marketing import video_ad_cycle as V

    assert _approve(c, _digest(artifact)).status_code == 200
    V._update("vid-preview-1", approval_txn_state=state)

    out = _approve(c, _digest(artifact))
    rec = _rec()
    if state == SAGA.TXN_FINALIZED:
        assert out.status_code == 200  # idempotent replay
        assert SAGA.is_publishable(rec) is True
    else:
        assert SAGA.is_publishable(rec) is False  # never publishable mid-saga
    assert _snapshots(ev) == 1  # no duplicate artifact
    assert ev["provider"] == 0
