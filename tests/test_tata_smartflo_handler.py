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
    get_status = 200

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

    async def get(
        self, url: str, *, params: dict[str, str], headers: dict[str, str]
    ) -> _Response:
        response = _Response()
        response.status_code = self.__class__.get_status
        return response


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
    _AsyncClient.payload = None  # reset before test

    result = await TataSmartfloClient().place_call("+91 84590 12607", skip_compliance=True)

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
    _AsyncClient.payload = None  # reset before test

    await TataSmartfloClient().place_call(
        "8459012607", caller_id="+91 80694 12345", skip_compliance=True
    )

    assert _AsyncClient.payload is not None
    # _clean_caller_id preserves country code (91 prefix) for Smartflo C2C API
    assert _AsyncClient.payload["caller_id"] == "918069412345"


@pytest.mark.asyncio
async def test_auth_probe_accepts_valid_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    from app.telephony.tata_smartflo_handler import TataSmartfloClient

    monkeypatch.setenv("TATA_SMARTFLO_API_TOKEN", "token-test")
    monkeypatch.setenv("TATA_SMARTFLO_API_KEY", "key-test")
    monkeypatch.setattr(httpx, "AsyncClient", _AsyncClient)
    _AsyncClient.get_status = 200

    result = await TataSmartfloClient().auth_probe()

    assert result == {"ok": True, "status_code": 200, "reason": ""}


@pytest.mark.asyncio
async def test_auth_probe_marks_revoked_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    from app.telephony.tata_smartflo_handler import TataSmartfloClient

    monkeypatch.setenv("TATA_SMARTFLO_API_TOKEN", "revoked-token")
    monkeypatch.setenv("TATA_SMARTFLO_API_KEY", "key-test")
    monkeypatch.setattr(httpx, "AsyncClient", _AsyncClient)
    _AsyncClient.get_status = 401

    result = await TataSmartfloClient().auth_probe()

    assert result["ok"] is False
    assert result["status_code"] == 401
    assert result["reason"] == "smartflo_auth_rejected"
