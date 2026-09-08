"""UPI config — env + admin data-file fallback."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get_vpa_env_wins(tmp_path, monkeypatch):
    from app.platform import upi_config as uc

    store = tmp_path / "platform_upi.json"
    store.write_text(json.dumps({"vpa": "file@ybl"}), encoding="utf-8")
    monkeypatch.setattr(uc, "_STORE", lambda: str(store))
    monkeypatch.setenv("UPI_VPA", "env@okhdfcbank")
    assert uc.get_vpa() == "env@okhdfcbank"
    assert uc.source() == "env"


def test_get_vpa_file_fallback(tmp_path, monkeypatch):
    from app.platform import upi_config as uc

    store = tmp_path / "platform_upi.json"
    store.write_text(json.dumps({"vpa": "shop@ybl"}), encoding="utf-8")
    monkeypatch.setattr(uc, "_STORE", lambda: str(store))
    monkeypatch.delenv("UPI_VPA", raising=False)
    monkeypatch.setattr("app.config.settings.upi_vpa", "", raising=False)
    assert uc.get_vpa() == "shop@ybl"
    assert uc.is_armed() is True


def test_set_vpa_rejects_invalid(tmp_path, monkeypatch):
    from app.platform import upi_config as uc

    monkeypatch.setattr(uc, "_STORE", lambda: str(tmp_path / "platform_upi.json"))
    out = uc.set_vpa("not-a-vpa")
    assert out["ok"] is False


def test_configure_endpoint_with_admin_override(tmp_path, monkeypatch):
    from app.api.admin import require_admin
    from app.platform import upi_config as uc

    monkeypatch.setattr(uc, "_STORE", lambda: str(tmp_path / "platform_upi.json"))
    monkeypatch.delenv("UPI_VPA", raising=False)
    monkeypatch.setattr("app.config.settings.upi_vpa", "", raising=False)
    app.dependency_overrides[require_admin] = lambda: {"username": "test"}
    try:
        r = client.post("/api/admin/upi/configure", json={"vpa": "shop@ybl"})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["upi"]["enabled"] is True
        assert data["upi"]["vpa"] == "shop@ybl"
    finally:
        app.dependency_overrides.pop(require_admin, None)


def test_pay_info_uses_file_vpa(tmp_path, monkeypatch):
    from app.platform import upi_config as uc

    store = tmp_path / "platform_upi.json"
    store.write_text(json.dumps({"vpa": "9876543210@ybl"}), encoding="utf-8")
    monkeypatch.setattr(uc, "_STORE", lambda: str(store))
    monkeypatch.delenv("UPI_VPA", raising=False)
    monkeypatch.setattr("app.config.settings.upi_vpa", "", raising=False)
    r = client.get("/api/public/pay-info")
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is True
    assert data["vpa"] == "9876543210@ybl"


def test_payments_ready_false_without_vpa(monkeypatch):
    from app.api import activation as ax

    monkeypatch.delenv("UPI_VPA", raising=False)
    monkeypatch.setattr(ax, "_payments_ready", lambda: False)
    assert ax._payments_ready() is False
