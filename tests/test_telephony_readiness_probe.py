"""Contract and unit tests for telephony readiness probe (outbound DID ownership probe)."""

import asyncio
import os
from unittest.mock import AsyncMock, patch

from app.telephony.telephony_readiness_probe import verify_outbound_connectivity


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_probe_skipped_when_env_unset(monkeypatch):
    monkeypatch.delenv("VOBIZ_VERIFY_CALLER_ID_OUTBOUND", raising=False)
    res = _run(verify_outbound_connectivity())
    assert res.get("ok") is True
    assert "skipped" in res.get("why", "")


def test_probe_success_when_vobiz_accepts(monkeypatch):
    monkeypatch.setenv("VOBIZ_VERIFY_CALLER_ID_OUTBOUND", "1")
    monkeypatch.setenv("VOBIZ_CALLER_ID", "+911171366938")

    fake_client = AsyncMock()
    fake_client.create_call.return_value = {"status": "success", "call_id": "c123"}

    with patch("app.telephony.vobiz_handler.VobizClient", return_value=fake_client):
        res = _run(verify_outbound_connectivity())
        assert res.get("ok") is True
        assert "verified" in res.get("why", "")


def test_probe_fails_when_vobiz_rejects(monkeypatch):
    monkeypatch.setenv("VOBIZ_VERIFY_CALLER_ID_OUTBOUND", "1")
    monkeypatch.setenv("VOBIZ_CALLER_ID", "+911171366938")

    fake_client = AsyncMock()
    fake_client.create_call.return_value = {
        "status": "failed",
        "error": "The from number 911171366938 is not owned by this account",
    }

    with patch("app.telephony.vobiz_handler.VobizClient", return_value=fake_client):
        res = _run(verify_outbound_connectivity())
        assert res.get("ok") is False
        assert "not owned" in res.get("why", "")


def test_probe_handles_exception_safely(monkeypatch):
    monkeypatch.setenv("VOBIZ_VERIFY_CALLER_ID_OUTBOUND", "1")

    with patch("app.telephony.vobiz_handler.VobizClient", side_effect=Exception("network timeout")):
        res = _run(verify_outbound_connectivity())
        assert res.get("ok") is False
        assert "outbound probe error" in res.get("why", "")
