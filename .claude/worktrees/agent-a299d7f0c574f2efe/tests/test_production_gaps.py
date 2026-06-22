"""
Tests: production gaps — public pay-info endpoint + manager daily digest.
==========================================================================
No SMTP / UPI_VPA / AI keys required — unset-default paths are exercised
(env-gated features must degrade silently, never 500).
"""

import pytest
from fastapi.testclient import TestClient


class TestPayInfo:
    def test_pay_info_disabled_by_default(self, client: TestClient, monkeypatch, tmp_path):
        """UPI_VPA unset + no data file => {"enabled": false}."""
        from app.config import settings
        from app.platform import upi_config as uc

        monkeypatch.setattr(uc, "_STORE", str(tmp_path / "missing_upi.json"))
        monkeypatch.delenv("UPI_VPA", raising=False)
        monkeypatch.setattr(settings, "upi_vpa", "", raising=False)
        res = client.get("/api/public/pay-info")
        assert res.status_code == 200
        data = res.json()
        assert data["enabled"] is False
        assert "vpa" not in data

    def test_pay_info_enabled_with_vpa(self, client: TestClient, monkeypatch):
        """UPI_VPA set => QR + VPA + packages (key/name/price)."""
        from app.platform import upi_config as uc

        monkeypatch.setenv("UPI_VPA", "9876543210@ybl")
        monkeypatch.setattr(uc, "get_vpa", lambda: "9876543210@ybl")
        res = client.get("/api/public/pay-info")
        assert res.status_code == 200
        data = res.json()
        assert data["enabled"] is True
        assert data["vpa"] == "9876543210@ybl"
        assert data["upi_link"].startswith("upi://pay?")
        assert "<svg" in data["qr_svg"]
        keys = {p["key"] for p in data["packages"]}
        assert {"starter", "growth", "advanced"} <= keys
        for p in data["packages"]:
            assert p["name"] and p["price_inr_month"] > 0


class TestDailyDigest:
    @pytest.mark.asyncio
    async def test_run_digest_returns_dict_with_text(self):
        """run_digest kabhi raise nahi karta — Hinglish text + counts deta hai."""
        from app.agents import staff

        result = await staff.run_digest()
        assert isinstance(result, dict)
        assert "error" not in result
        assert "Daily Digest" in (result.get("text") or "")
        assert isinstance(result.get("inquiries_24h"), int)
        assert isinstance(result.get("prospects_ready"), int)

    @pytest.mark.asyncio
    async def test_run_member_dispatches_digest(self):
        """run_member("digest") aur ("manager") dono digest pe route hote hain."""
        from app.agents import staff

        result = await staff.run_member("digest")
        assert isinstance(result, dict)
        assert "text" in result
