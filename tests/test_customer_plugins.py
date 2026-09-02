"""Tests for customer plugins page and API endpoint.

Covers:
  - Page served correctly
  - API endpoint with customer auth
  - Capability definitions (marketing, voice, combo)
  - Flag-based active/inactive
  - Response model validation
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Page route tests
# ---------------------------------------------------------------------------


class TestCustomerPluginsPage:
    """Static assertions on frontend/customer_plugins.html + route."""

    def test_page_file_exists(self):
        from pathlib import Path

        html = Path("frontend/customer_plugins.html")
        assert html.exists(), "customer_plugins.html not found"

    def test_page_has_required_elements(self):
        from pathlib import Path

        html = Path("frontend/customer_plugins.html").read_text(encoding="utf-8")
        assert "Aapki AI Capabilities" in html
        assert "capabilitiesList" in html
        assert "cap-card" in html
        assert "/api/customer/plugins" in html
        assert "/app/customer" in html

    def test_page_fetches_api(self):
        from pathlib import Path

        html = Path("frontend/customer_plugins.html").read_text(encoding="utf-8")
        assert "fetch('/api/customer/plugins'" in html

    def test_page_is_responsive(self):
        from pathlib import Path

        html = Path("frontend/customer_plugins.html").read_text(encoding="utf-8")
        assert "@media" in html
        assert "max-width" in html

    def test_page_uses_design_system(self):
        from pathlib import Path

        html = Path("frontend/customer_plugins.html").read_text(encoding="utf-8")
        assert "/design-system/styles.css" in html


class TestCustomerPluginsRoute:
    """Route-level test: /app/plugins serves the page."""

    def test_plugins_page_200(self):
        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/app/plugins")
        assert response.status_code == 200
        assert "Aapki AI Capabilities" in response.text


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestCustomerPluginsAPI:
    """GET /api/customer/plugins endpoint tests."""

    def _make_app(self):
        from app.api.customer_plugins import router

        app = FastAPI()
        app.include_router(router)
        return app

    def test_api_requires_customer_auth(self):
        app = self._make_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/customer/plugins")
        # 401 = no token, 403 = invalid token, 422 = missing required dep
        assert response.status_code in (401, 403, 422)

    def test_api_returns_capabilities(self):
        from app.api.customer_plugins import _get_active_capabilities

        caps = _get_active_capabilities("test_client")
        assert len(caps) > 0
        assert all(hasattr(c, "id") for c in caps)
        assert all(hasattr(c, "title") for c in caps)
        assert all(hasattr(c, "active") for c in caps)

    def test_marketing_capabilities_count(self):
        from app.api.customer_plugins import _MARKETING_CAPABILITIES

        assert len(_MARKETING_CAPABILITIES) >= 6
        ids = [c.id for c in _MARKETING_CAPABILITIES]
        assert "content_creation" in ids
        assert "lead_management" in ids
        assert "marketing_calendar" in ids
        assert "ai_assistant" in ids
        assert "analytics" in ids

    def test_voice_capabilities_count(self):
        from app.api.customer_plugins import _VOICE_CAPABILITIES

        assert len(_VOICE_CAPABILITIES) >= 3
        ids = [c.id for c in _VOICE_CAPABILITIES]
        assert "ai_calling" in ids
        assert "call_analytics" in ids

    def test_capability_model_fields(self):
        from app.api.customer_plugins import Capability

        cap = Capability(
            id="test",
            title="Test Capability",
            desc="A test",
            icon="🔧",
            active=True,
            features=["feat1", "feat2"],
        )
        assert cap.id == "test"
        assert cap.active is True
        assert len(cap.features) == 2

    def test_response_model(self):
        from app.api.customer_plugins import Capability, CustomerPluginsResponse

        resp = CustomerPluginsResponse(
            ok=True,
            plan="Starter",
            product="marketing",
            capabilities=[
                Capability(id="c1", title="C1", active=True),
            ],
            timestamp=1234567890.0,
        )
        assert resp.ok is True
        assert resp.plan == "Starter"
        assert len(resp.capabilities) == 1


# ---------------------------------------------------------------------------
# Flag-based activation tests
# ---------------------------------------------------------------------------


class TestFlagBasedActivation:
    """Capabilities should respect feature flags."""

    def test_content_creation_tied_to_auto_content(self):
        import os

        from app.api.customer_plugins import _flag, _get_active_capabilities

        # With AUTO_CONTENT off, content_creation should be inactive
        old = os.environ.pop("AUTO_CONTENT", None)
        os.environ["AUTO_CONTENT"] = "0"
        try:
            caps = _get_active_capabilities("test")
            content = [c for c in caps if c.id == "content_creation"]
            assert len(content) == 1
            assert content[0].active is False
        finally:
            if old is not None:
                os.environ["AUTO_CONTENT"] = old
            else:
                os.environ.pop("AUTO_CONTENT", None)

    def test_lead_management_always_active(self):
        from app.api.customer_plugins import _get_active_capabilities

        caps = _get_active_capabilities("test")
        leads = [c for c in caps if c.id == "lead_management"]
        assert len(leads) == 1
        assert leads[0].active is True

    def test_analytics_always_active(self):
        from app.api.customer_plugins import _get_active_capabilities

        caps = _get_active_capabilities("test")
        analytics = [c for c in caps if c.id == "analytics"]
        assert len(analytics) == 1
        assert analytics[0].active is True


# ---------------------------------------------------------------------------
# Product routing tests
# ---------------------------------------------------------------------------


class TestProductRouting:
    """Different products should show different capabilities."""

    def test_default_is_marketing(self):
        from app.api.customer_plugins import _get_client_product

        product, plan = _get_client_product("nonexistent_client")
        assert product == "marketing"

    def test_marketing_has_content(self):
        from app.api.customer_plugins import _MARKETING_CAPABILITIES

        ids = [c.id for c in _MARKETING_CAPABILITIES]
        assert "content_creation" in ids
        assert "marketing_calendar" in ids

    def test_voice_has_calling(self):
        from app.api.customer_plugins import _VOICE_CAPABILITIES

        ids = [c.id for c in _VOICE_CAPABILITIES]
        assert "ai_calling" in ids
        assert "call_analytics" in ids

    def test_voice_no_content_creation(self):
        from app.api.customer_plugins import _VOICE_CAPABILITIES

        ids = [c.id for c in _VOICE_CAPABILITIES]
        assert "content_creation" not in ids
        assert "marketing_calendar" not in ids
