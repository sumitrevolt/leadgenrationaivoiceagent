"""Cross-path telephony lifecycle — Vobiz stream metering + qualified-lead idempotency."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.billing import lead_usage
from app.telephony.post_call_hooks import apply_qualified_downstream, meter_call_completion
from app.telephony.vobiz_stream import VobizStreamSession


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_meter_call_completion_idempotent(monkeypatch):
    """Same call_id twice → record_call_usage runs once."""
    calls: list[tuple] = []

    def _fake_record(**kw):
        calls.append(kw)
        return True

    seen: set[str] = set()

    async def _fake_seen(key: str, ttl_s=None):
        if key in seen:
            return True
        seen.add(key)
        return False

    monkeypatch.setattr("app.billing.usage.record_call_usage", _fake_record)
    with patch("app.billing.idempotency.seen_before", side_effect=_fake_seen):
        assert _run(meter_call_completion("sid-1", client_id="c1", duration_seconds=90)) is True
        assert _run(meter_call_completion("sid-1", client_id="c1", duration_seconds=90)) is False
    assert len(calls) == 1
    assert calls[0]["duration_seconds"] == 90


def test_record_qualified_lead_ref_idempotent(tmp_path, monkeypatch):
    """Same ref twice → one ledger row."""
    store = tmp_path / "lead_usage.jsonl"
    monkeypatch.setattr(lead_usage, "_STORE", store)

    assert lead_usage.record_qualified_lead("client-x", ref="call-abc") is True
    assert lead_usage.record_qualified_lead("client-x", ref="call-abc") is True
    lines = store.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


def test_vobiz_cleanup_meters_once(monkeypatch):
    """VobizStreamSession._cleanup invokes meter_call_completion exactly once."""
    meter = AsyncMock(return_value=True)
    monkeypatch.setattr("app.telephony.post_call_hooks.meter_call_completion", meter)

    sess = VobizStreamSession(MagicMock(), client_id="cid-1", client_name="Test Co")
    sess.stream_sid = "stream-99"
    monkeypatch.setattr(sess, "_auto_qualify", AsyncMock())
    monkeypatch.setattr(sess, "_save_recording", lambda: None)
    monkeypatch.setattr(sess, "_persist_transcript", lambda *a, **k: None)
    _run(sess._cleanup())
    _run(sess._cleanup())  # duplicate disconnect
    assert meter.await_count == 1


def test_apply_qualified_downstream_enrolls_when_flagged(monkeypatch):
    """Qualified verdict fans out to sales pipeline (cadence gated separately)."""
    enrolled: list[dict] = []
    monkeypatch.setattr(
        "app.marketing.sales_pipeline.upsert_deal",
        lambda data, stage="interested": enrolled.append({"data": data, "stage": stage}),
    )
    monkeypatch.setenv("CADENCE_ENGINE", "0")
    q = {"qualified": True, "interest_score": 80, "summary": "hot", "next_action": "call"}
    _run(
        apply_qualified_downstream(
            q,
            client_id="c1",
            phone="+919999999999",
            client_name="Acme",
            call_id="sid-1",
            niche="solar",
        )
    )
    assert len(enrolled) == 1
    assert enrolled[0]["stage"] == "interested"
