"""Contract tests for Smartflo Click-to-Call Support payloads."""

from __future__ import annotations

import pytest


class _Response:
    status_code = 200
    text = ""

    @staticmethod
    def json() -> dict[str, object]:
        return {"success": True, "ref_id": "ref-contract-1"}


class _AsyncClient:
    payload: dict[str, object] | None = None

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    async def __aenter__(self) -> _AsyncClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(
        self, url: str, *, json: dict[str, object], headers: dict[str, str]
    ) -> _Response:
        self.__class__.payload = json
        return _Response()


@pytest.mark.asyncio
async def test_c2c_support_uses_api_key_did_when_no_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    from app.telephony.tata_smartflo_handler import TataSmartfloClient

    monkeypatch.setenv("TATA_SMARTFLO_API_TOKEN", "token-test")
    monkeypatch.setenv("TATA_SMARTFLO_API_KEY", "key-test")
    monkeypatch.setenv("TATA_SMARTFLO_DID", "918069879757")
    monkeypatch.setattr(httpx, "AsyncClient", _AsyncClient)

    result = await TataSmartfloClient().place_call("+91 84590 12607")

    assert result["status_code"] == 200
    assert _AsyncClient.payload is not None
    assert _AsyncClient.payload["customer_number"] == "8459012607"
    assert "caller_id" not in _AsyncClient.payload


@pytest.mark.asyncio
async def test_c2c_support_sends_only_explicit_caller_id_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    from app.telephony.tata_smartflo_handler import TataSmartfloClient

    monkeypatch.setenv("TATA_SMARTFLO_API_TOKEN", "token-test")
    monkeypatch.setenv("TATA_SMARTFLO_API_KEY", "key-test")
    monkeypatch.setenv("TATA_SMARTFLO_DID", "918069879757")
    monkeypatch.setattr(httpx, "AsyncClient", _AsyncClient)

    await TataSmartfloClient().place_call("8459012607", caller_id="+91 80694 12345")

    assert _AsyncClient.payload is not None
    assert _AsyncClient.payload["caller_id"] == "8069412345"
