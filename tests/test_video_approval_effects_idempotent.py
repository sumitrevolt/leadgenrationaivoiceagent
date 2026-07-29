"""Final 3A gate — per-effect idempotency.

The previous cut tracked ONE effects marker for both operations, so a retry
after a partial failure re-invoked the already-successful effect and relied on
a local marker that can itself fail after the downstream write.

Each effect now carries its own deterministic key (SHA-256 over transaction id
+ effect name) and its own marker. Crucially the delivery-ledger key is passed
DOWNSTREAM to `log_event(key=...)`, which skips duplicates itself — so the
guarantee survives a marker write that dies after the ledger write.

These tests count DURABLE OUTPUT (ledger rows, queue items), not spy calls.
"""

from __future__ import annotations

import hashlib
import threading

import pytest

from app.marketing.video_production import approval_saga as SAGA

# ruff: noqa: F811
from tests.test_video_preview_identity import preview_client  # noqa: F401


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    from app.marketing import delivery_ledger
    from app.marketing import video_media_paths as vmp

    monkeypatch.setattr(vmp, "approved_media_dir", lambda: tmp_path / "approved")
    ledger_dir = tmp_path / "ledger"
    ledger_dir.mkdir()
    monkeypatch.setattr(delivery_ledger, "_LEDGER_DIR", lambda: str(ledger_dir))
    return ledger_dir


def _rec():
    from app.marketing import video_ad_cycle as V

    return (V._latest() or {}).get("vid-preview-1") or {}


def _approve(c, artifact, rev=0):
    return c.post(
        "/api/customer/videos/vid-preview-1/feedback",
        json={
            "action": "approve",
            "expected_revision": rev,
            "expected_content_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        },
    )


def _ledger_rows(tenant="fixture-tenant-p", event="post_approved"):
    """Real durable rows. No exception swallowing — a broken helper must fail
    loudly rather than silently reporting zero."""
    from app.marketing import delivery_ledger

    rows = delivery_ledger._read_events(tenant) or []
    return [r for r in rows if str(r.get("event") or "") == event]


# --- keys are per-effect, not per-transaction ---------------------------


def test_effect_keys_are_distinct_per_effect():
    a = SAGA.effect_key("txn-1", "enqueue")
    b = SAGA.effect_key("txn-1", "delivery_ledger")
    assert a != b and len(a) == 32


def test_effect_key_is_deterministic_and_txn_scoped():
    assert SAGA.effect_key("t1", "enqueue") == SAGA.effect_key("t1", "enqueue")
    assert SAGA.effect_key("t1", "enqueue") != SAGA.effect_key("t2", "enqueue")


# --- 1-5. marker lost after a successful downstream write ----------------


def test_marker_lost_after_delivery_write_still_yields_one_ledger_event(
    preview_client, monkeypatch
):
    """The hardest case: the ledger write SUCCEEDS, then our marker write dies.

    A local marker alone would be wrong here. The downstream key is what keeps
    the durable output at exactly one.
    """
    c, artifact = preview_client
    from app.marketing import video_ad_cycle as V

    real = V._update
    broken = {"on": True}

    def _drop_delivery_marker(rid, **f):
        if broken["on"] and f.get("approval_effect_delivery_ledger") == SAGA.EFFECTS_EMITTED:
            raise OSError("record store down")
        return real(rid, **f)

    monkeypatch.setattr(V, "_update", _drop_delivery_marker)
    assert _approve(c, artifact).status_code == 200
    assert len(_ledger_rows()) == 1  # written once
    assert _rec().get("approval_effect_delivery_ledger") != SAGA.EFFECTS_EMITTED
    assert _rec()["approval_effect_enqueue"] == SAGA.EFFECTS_EMITTED  # untouched

    broken["on"] = False
    assert SAGA.recover("vid-preview-1")["ok"] is True
    assert len(_ledger_rows()) == 1  # STILL exactly one
    assert _rec()["approval_effect_delivery_ledger"] == SAGA.EFFECTS_EMITTED
    assert _rec()["approval_effects"] == SAGA.EFFECTS_EMITTED


def test_one_failed_effect_does_not_mark_the_other_emitted(preview_client, monkeypatch):
    c, artifact = preview_client
    from app.marketing import delivery_ledger

    broken = {"on": True}
    real_log = delivery_ledger.log_event

    def _flaky(*a, **k):
        if broken["on"]:
            raise OSError("ledger down")
        return real_log(*a, **k)

    monkeypatch.setattr(delivery_ledger, "log_event", _flaky)
    assert _approve(c, artifact).status_code == 200

    rec = _rec()
    assert rec["approval_effect_enqueue"] == SAGA.EFFECTS_EMITTED
    assert rec["approval_effect_delivery_ledger"] == SAGA.EFFECTS_FAILED
    assert rec["approval_effects"] == SAGA.EFFECTS_FAILED
    assert len(_ledger_rows()) == 0

    broken["on"] = False
    assert SAGA.recover("vid-preview-1")["ok"] is True
    assert len(_ledger_rows()) == 1
    assert _rec()["approval_effects"] == SAGA.EFFECTS_EMITTED


def test_already_emitted_effect_is_not_reinvoked_on_retry(preview_client, monkeypatch):
    c, artifact = preview_client
    from app.marketing import auto_content, delivery_ledger

    calls = {"enqueue": 0}
    real_enqueue = auto_content.enqueue_approved
    monkeypatch.setattr(
        auto_content,
        "enqueue_approved",
        lambda *a, **k: (calls.__setitem__("enqueue", calls["enqueue"] + 1), real_enqueue(*a, **k))[
            1
        ],
    )

    broken = {"on": True}
    real_log = delivery_ledger.log_event

    def _flaky(*a, **k):
        if broken["on"]:
            raise OSError("ledger down")
        return real_log(*a, **k)

    monkeypatch.setattr(delivery_ledger, "log_event", _flaky)
    assert _approve(c, artifact).status_code == 200
    assert calls["enqueue"] == 1

    broken["on"] = False
    SAGA.recover("vid-preview-1")
    # The successful effect is NOT re-invoked — its own marker says emitted.
    assert calls["enqueue"] == 1
    assert len(_ledger_rows()) == 1


# --- 7-8. concurrency and provider silence -------------------------------


def test_concurrent_recoveries_produce_one_ledger_event(preview_client, monkeypatch):
    c, artifact = preview_client
    from app.marketing import delivery_ledger

    broken = {"on": True}
    real_log = delivery_ledger.log_event

    def _flaky(*a, **k):
        if broken["on"]:
            raise OSError("ledger down")
        return real_log(*a, **k)

    monkeypatch.setattr(delivery_ledger, "log_event", _flaky)
    assert _approve(c, artifact).status_code == 200
    assert _rec()["approval_effect_delivery_ledger"] == SAGA.EFFECTS_FAILED

    broken["on"] = False
    out = []
    threads = [
        threading.Thread(target=lambda: out.append(SAGA.recover("vid-preview-1"))) for _ in range(5)
    ]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert all(r.get("ok") for r in out)
    assert len(_ledger_rows()) == 1
    assert _rec()["approval_effects"] == SAGA.EFFECTS_EMITTED


def test_no_provider_call_during_any_effect_path(preview_client, monkeypatch):
    c, artifact = preview_client
    from app.marketing import delivery_ledger
    from app.marketing import postiz_publish as pp

    calls = {"provider": 0}

    async def _spy(*a, **k):
        calls["provider"] += 1
        return {"sent": True}

    monkeypatch.setattr(pp, "publish_video", _spy, raising=False)
    broken = {"on": True}
    real_log = delivery_ledger.log_event
    monkeypatch.setattr(
        delivery_ledger,
        "log_event",
        lambda *a, **k: (_ for _ in ()).throw(OSError("x")) if broken["on"] else real_log(*a, **k),
    )

    assert _approve(c, artifact).status_code == 200
    broken["on"] = False
    SAGA.recover("vid-preview-1")
    assert calls == {"provider": 0}


def test_happy_path_emits_each_effect_exactly_once(preview_client):
    c, artifact = preview_client
    assert _approve(c, artifact).status_code == 200
    rec = _rec()
    assert rec["approval_effect_enqueue"] == SAGA.EFFECTS_EMITTED
    assert rec["approval_effect_delivery_ledger"] == SAGA.EFFECTS_EMITTED
    assert rec["approval_effects"] == SAGA.EFFECTS_EMITTED
    assert len(_ledger_rows()) == 1

    SAGA.recover("vid-preview-1")
    assert len(_ledger_rows()) == 1
