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
        """UPI_VPA set => QR + VPA + public packages (key/name/price).

        Note on packages (ADR-009, 2026-06-11 product split + 2026-06-15
        package-trim): the public pricing endpoint deliberately exposes only
        the 2 public plans (Main = "starter", Advanced = "advanced"). The
        legacy internal "growth" plan is hidden behind `public:False` and
        surfaced ONLY via `get_packages()` for backward-compat consumers —
        NEVER on the public pricing surface. This test enforces that:
        adding a new public plan needs an explicit product decision, and
        no plan key silently reappears in the customer's pay-info view.
        """
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
        # Exactly the 2 public plans — neither less, neither more without ADR.
        assert {"starter", "advanced"} <= keys, (
            f"public pay-info must show exactly the public pricing plans; got {keys}"
        )
        assert "growth" not in keys, (
            "legacy 'growth' plan must NOT appear on public pricing — ADR-009/2026-06-11"
        )
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
