"""Regression tests for the unified Tata Smartflo calling path."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


class _Handler:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def place_call(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        return {"status_code": 200, "body": {"success": True, "ref_id": "smartflo-ref-1"}}


def _service():
    from app.telephony.telephony_service import TelephonyService

    service = TelephonyService.__new__(TelephonyService)
    service.provider = "tata_smartflo"
    service._handler = None
    return service


@pytest.mark.asyncio
async def test_smartflo_service_constructs_handler_and_preserves_api_key_did(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.telephony import compliance
    from app.telephony.telephony_service import TelephonyService

    handler = _Handler()
    monkeypatch.setenv("TATA_SMARTFLO_DID", "918069879757")
    monkeypatch.setattr(TelephonyService, "_build_handler", lambda self, provider: handler)
    monkeypatch.setattr(
        compliance,
        "get_compliance_gate",
        lambda: SimpleNamespace(check=lambda *_args, **_kwargs: _allow_async()),
    )

    service = TelephonyService(provider="tata_smartflo")
    result = await service.place_call("8459012607", call_type="transactional")

    assert result.status == "initiated"
    assert service._handler is handler
    assert handler.calls[0]["caller_id"] is None


def test_smartflo_validate_config_reports_required_credentials_without_did(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TATA_SMARTFLO_API_TOKEN", "token-test")
    monkeypatch.setenv("TATA_SMARTFLO_API_KEY", "key-test")
    monkeypatch.delenv("TATA_SMARTFLO_DID", raising=False)

    result = _service().validate_config()

    assert result["available_providers"]["tata_smartflo"] is True
    assert result["configured"] is True
    assert result["missing"] == []


def test_smartflo_validate_config_fails_closed_when_key_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TATA_SMARTFLO_API_TOKEN", "token-test")
    monkeypatch.delenv("TATA_SMARTFLO_API_KEY", raising=False)

    result = _service().validate_config()

    assert result["available_providers"]["tata_smartflo"] is False
    assert result["configured"] is False
    assert result["missing"] == ["TATA_SMARTFLO_API_KEY"]


async def _allow_async() -> SimpleNamespace:
    return SimpleNamespace(allowed=True, reasons=[])
