"""Loop-social-6 (2026-07-11): canonical social delivery-ledger event enum.

Contract:
- 11 new event types are registered in delivery_ledger.LABELS + EVENT_TYPES:
  social_account_connected, social_account_disconnected,
  social_account_connection_failed, token_refreshed, token_expired,
  post_scheduled, post_publish_started, post_partially_published,
  post_retry_scheduled, post_cancelled, customer_action_required.
- process_queue emits post_publish_started on each dispatch, and
  post_retry_scheduled on the retry branch, and customer_action_required on
  the inert (unconfigured) branch.
- Existing labels (post_approved/post_published/post_failed etc) untouched.
"""

from __future__ import annotations

import asyncio

import pytest

from app.marketing import delivery_ledger


NEW_EVENTS = (
    "social_account_connected",
    "social_account_disconnected",
    "social_account_connection_failed",
    "token_refreshed",
    "token_expired",
    "post_scheduled",
    "post_publish_started",
    "post_partially_published",
    "post_retry_scheduled",
    "post_cancelled",
    "customer_action_required",
)


# --------------------------------------------------------------------------- #
# Enum registration                                                            #
# --------------------------------------------------------------------------- #
def test_all_new_event_types_registered():
    """Every canonical Phase-9 event type must be in LABELS + EVENT_TYPES."""
    for ev in NEW_EVENTS:
        assert ev in delivery_ledger.LABELS, f"{ev} missing from LABELS"
        assert ev in delivery_ledger.EVENT_TYPES, f"{ev} missing from EVENT_TYPES"
        icon, hi, en, visible = delivery_ledger.LABELS[ev]
        assert icon, f"{ev} needs an icon"
        assert en, f"{ev} needs an admin/technical label"
        assert isinstance(visible, bool), f"{ev} customer_visible must be bool"


def test_customer_visible_flags_reasonable():
    """Ops-only events must be customer_visible=False (avoid timeline noise);
    customer-relevant events must be True."""
    # These are ops-only churn — the shop owner should not see raw retry pings.
    ops_only = {"token_refreshed", "post_publish_started", "post_retry_scheduled"}
    for ev in ops_only:
        assert delivery_ledger.LABELS[ev][3] is False, f"{ev} should be ops-only"
    # Customer sees the outcome-shaped events.
    customer_visible = {
        "social_account_connected",
        "social_account_disconnected",
        "social_account_connection_failed",
        "token_expired",
        "post_scheduled",
        "post_partially_published",
        "post_cancelled",
        "customer_action_required",
    }
    for ev in customer_visible:
        assert delivery_ledger.LABELS[ev][3] is True, f"{ev} should be customer-visible"


def test_pre_existing_labels_untouched():
    """Loop-social-6 must NOT rewrite existing labels — purely additive."""
    assert "post_published" in delivery_ledger.LABELS
    assert "post_failed" in delivery_ledger.LABELS
    assert "post_approved" in delivery_ledger.LABELS
    assert "social_setup_completed" in delivery_ledger.LABELS
    # Sanity spot-check icon (regression guard for accidental value edits).
    assert delivery_ledger.LABELS["post_published"][0] == "📢"


# --------------------------------------------------------------------------- #
# Engine wiring: process_queue emits the new events                            #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def engine_iso(monkeypatch, tmp_path):
    """Isolate the engine's queue/vault + capture every log_event."""
    from app.social_engine import engine, store, vault
    from app.social_engine.base import PublishResult, SocialProvider

    monkeypatch.setattr(store, "_PATH", str(tmp_path / "jobs.jsonl"))
    monkeypatch.setattr(vault, "_PATH", str(tmp_path / "tokens.jsonl"))
    monkeypatch.setattr(store, "_mirror", lambda job: None)
    monkeypatch.setenv("SOCIAL_ENGINE", "1")
    monkeypatch.delenv("SOCIAL_DRY_RUN", raising=False)
    monkeypatch.delenv("SOCIAL_TOKEN_KEY", raising=False)

    class _Failing(SocialProvider):
        name = "failing"

        def configured(self, account=None):
            return True

        async def publish(self, req, account):
            return PublishResult(ok=False, platform="failing", error="rate_limit")

    class _Inert(SocialProvider):
        name = "inert"

        def configured(self, account=None):
            return False

        async def publish(self, req, account):
            return PublishResult(ok=False, platform="inert", error="unused")

    monkeypatch.setattr(engine, "_REGISTRY", {"failing": _Failing(), "inert": _Inert()})

    captured: list[tuple[str, str, str]] = []

    def _capture(cid, ev, detail=""):
        captured.append((cid, ev, detail))

    monkeypatch.setattr(delivery_ledger, "log_event", _capture)
    return {"engine": engine, "store": store, "captured": captured}


def test_process_queue_emits_publish_started(engine_iso):
    """Every dispatch begins with post_publish_started."""
    engine_iso["engine"].enqueue_publish("c1", caption="hi", platforms=["failing"])
    asyncio.run(engine_iso["engine"].process_queue())
    events = [ev for _, ev, _ in engine_iso["captured"]]
    assert "post_publish_started" in events


def test_process_queue_emits_retry_scheduled_on_transient_failure(engine_iso):
    """A single failed dispatch (attempts<max) → post_retry_scheduled logged."""
    engine_iso["engine"].enqueue_publish("c1", caption="hi", platforms=["failing"])
    out = asyncio.run(engine_iso["engine"].process_queue())
    assert out["retried"] == 1
    retry_events = [
        (cid, det) for cid, ev, det in engine_iso["captured"] if ev == "post_retry_scheduled"
    ]
    assert len(retry_events) >= 1
    cid, detail = retry_events[0]
    assert cid == "c1"
    assert "attempt" in detail  # "attempt 1/4 — rate_limit"


def test_process_queue_emits_customer_action_on_inert_provider(engine_iso):
    """Unconfigured provider → skipped + customer_action_required emitted."""
    engine_iso["engine"].enqueue_publish("c1", caption="hi", platforms=["inert"])
    out = asyncio.run(engine_iso["engine"].process_queue())
    assert out["skipped"] == 1
    cact = [ev for _, ev, _ in engine_iso["captured"] if ev == "customer_action_required"]
    assert len(cact) >= 1


def test_process_queue_emits_post_failed_on_terminal_failure(engine_iso):
    """After max_attempts the drain marks dead + emits post_failed (existing)."""
    from app.social_engine import store as _store

    # Pre-load a job with attempts already at max-1 so the next failure lands it in DEAD.
    jid = _store.enqueue({"client_id": "c1", "platform": "failing", "caption": "hi"})
    _store.mark(jid, "queued", attempts=_store.max_attempts() - 1)
    asyncio.run(engine_iso["engine"].process_queue())
    events = [ev for _, ev, _ in engine_iso["captured"]]
    assert "post_failed" in events
