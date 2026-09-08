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

        monkeypatch.setattr(uc, "_STORE", lambda: str(tmp_path / "missing_upi.json"))
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
        assert {
            "starter",
            "advanced",
        } <= keys, f"public pay-info must show exactly the public pricing plans; got {keys}"
        assert "growth" not in keys, (
            "legacy 'growth' plan must NOT appear on public pricing — ADR-009/2026-06-11"
        )
        for p in data["packages"]:
            assert p["name"] and p["price_inr_month"] > 0


class TestPublicPricingSurfaces:
    """Phase-1 hardening (2026-07-01): public pricing endpoints + frontend must
    NEVER expose the hidden legacy 'growth' plan (ADR-009/2026-06-11)."""

    def test_marketing_packages_endpoint_only_public_keys(self, client: TestClient):
        res = client.get("/api/marketing/packages")
        assert res.status_code == 200
        keys = {p["key"] for p in res.json()["packages"]}
        assert keys == {"starter", "advanced"}
        assert "growth" not in keys

    def test_billing_plans_endpoint_only_public_keys(self, client: TestClient):
        res = client.get("/api/billing/plans")
        assert res.status_code == 200
        keys = {p["id"] for p in res.json()}
        assert keys == {"starter", "advanced"}
        assert "growth" not in keys

    def test_index_html_has_no_dead_growth_handling(self):
        """Regression guard: index.html used to carry dead client-side logic that
        specifically named/rendered a 'growth' plan (has-growth 3-col CSS, hasGrowth
        JS branch, pkgNames map). Removed 2026-07-01 — the public API is the only
        gate now (already covered above); this just stops the dead code creeping
        back in a future edit."""
        import pathlib

        html = pathlib.Path("frontend/website/index.html").read_text(encoding="utf-8")
        assert "has-growth" not in html
        assert "hasGrowth" not in html
        assert "growth: 'Growth'" not in html


class TestUpiSelfServeWiring:
    """Phase-2 (2026-07-01): public pay modal ref-submit + admin self-serve queue
    panel. Backend (/api/upi/submit, /api/upi/pending, decide()) already has full
    behavioural coverage in tests/test_upi_payments.py — this just guards the
    frontend wiring onto those existing endpoints stays present."""

    def test_public_pay_modal_submits_to_upi_endpoint(self):
        import pathlib

        html = pathlib.Path("frontend/website/index.html").read_text(encoding="utf-8")
        assert "/api/upi/submit" in html
        assert 'id="payRefForm"' in html
        assert 'data-plan-key="starter"' in html
        assert 'data-plan-key="advanced"' in html

    def test_admin_dashboard_has_self_serve_queue_panel(self):
        import pathlib

        html = pathlib.Path("frontend/admin_dashboard.html").read_text(encoding="utf-8")
        assert "loadUpiSelfServe" in html
        assert "/api/upi/pending" in html
        assert "upiSelfServeDecide" in html

    def test_admin_dashboard_has_bind_action_for_unbound_guest(self):
        """#304: the operator bind queue action is wired into the admin panel."""
        import pathlib

        html = pathlib.Path("frontend/admin_dashboard.html").read_text(encoding="utf-8")
        assert "upiSelfServeBind" in html
        assert "'/bind'" in html  # POST /api/upi/pending/{pid}/bind
        assert "Payment approved, plan NOT activated" in html


class TestCustomerOfficeSummaryWiring:
    """Phase-4 (2026-07-01): the /api/customer/office 'summary' payload existed
    server-side but was never rendered — customer_office.js only drew tasks +
    activity. Guards the top-of-page proof-of-work stat strip stays wired."""

    def test_customer_office_js_renders_summary_stats(self):
        import pathlib

        js = pathlib.Path("frontend/design-system/customer_office.js").read_text(encoding="utf-8")
        assert "statsHtml" in js
        assert "calls_completed" in js
        assert "bookings" in js
        assert "posts_ready" in js


class TestMcpStatusWiring:
    """P2-2 (2026-07-02): /api/admin/mcp/health + /health/run already existed
    (app/api/mcp_product.py) and were fully unit-tested (tests/test_mcp_engineer.py)
    but had ZERO admin UI — the secure-off refusal (app/main.py) was log-only.
    Guards the admin dashboard card stays wired onto those existing endpoints."""

    def test_admin_dashboard_has_mcp_status_card(self):
        import pathlib

        html = pathlib.Path("frontend/admin_dashboard.html").read_text(encoding="utf-8")
        assert "loadMcpStatus" in html
        assert "mcpHealthRun" in html
        assert "/api/admin/mcp/health" in html
        assert "/api/admin/mcp/health/run" in html

    def test_mcp_status_card_never_renders_raw_secrets(self):
        """renderMcpStatus() must only read booleans/counts from health_score()
        (token_configured/ip_allowlist_set/score/actions) — never a raw secret
        VALUE field (health_score() itself never returns one; this just guards
        the renderer doesn't grow a `d.token`/`d.secret` field access)."""
        import pathlib
        import re

        html = pathlib.Path("frontend/admin_dashboard.html").read_text(encoding="utf-8")
        m = re.search(r"function renderMcpStatus\(d\)\{.*?\n\}", html, re.S)
        assert m, "renderMcpStatus function not found"
        body = m.group(0)
        assert "token_configured" in body
        assert "ip_allowlist_set" in body
        assert not re.search(r"d\.(token|secret|key)\b", body)


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
