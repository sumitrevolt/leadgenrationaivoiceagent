"""Fail-closed authentication for the Smartflo voice WebSocket."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.api.telephony_smartflo import smartflo_stream_ws


class _FakeWS:
    def __init__(self) -> None:
        self.query_params: dict[str, str] = {}
        self.headers: dict[str, str] = {}
        self.client = SimpleNamespace(host="203.0.113.10")
        self.close_codes: list[int] = []

    async def close(self, code: int) -> None:
        self.close_codes.append(code)


def _unexpected_session(*args: object, **kwargs: object) -> None:
    raise AssertionError("unauthenticated stream reached session")


@pytest.mark.parametrize("secret", [None, "", "   "])
def test_required_secret_missing_closes_before_stream(monkeypatch, secret: str | None) -> None:
    monkeypatch.setenv("SMARTFLO_VOICE_STREAM_ENABLED", "1")
    monkeypatch.setenv("SMARTFLO_WS_REQUIRE_SECRET", "1")
    if secret is None:
        monkeypatch.delenv("SMARTFLO_WS_SECRET", raising=False)
    else:
        monkeypatch.setenv("SMARTFLO_WS_SECRET", secret)
    monkeypatch.delenv("SMARTFLO_WS_ALLOW_IPS", raising=False)
    ws = _FakeWS()
    with patch(
        "app.telephony.smartflo_stream.SmartfloStreamSession", side_effect=_unexpected_session
    ):
        asyncio.run(smartflo_stream_ws(ws))
    assert ws.close_codes == [1008]
