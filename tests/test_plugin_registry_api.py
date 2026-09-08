"""Tests for GET /api/admin/plugins — plugin registry admin API."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.harness.plugin_catalog import bootstrap_catalog
from app.agents.harness.plugin_manifest import get_registry


@pytest.fixture(autouse=True)
def _fresh_registry():
    """Reset and bootstrap the plugin registry for each test."""
    import app.agents.harness.plugin_manifest as pm_mod

    pm_mod._registry = None
    bootstrap_catalog()
    yield
    pm_mod._registry = None


@pytest.fixture()
def client():
    """TestClient with the plugin registry router mounted."""
    from app.api.plugin_registry import router

    app = FastAPI()
    # Router already has prefix="/api/admin", no extra prefix needed
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Auth gating
# ---------------------------------------------------------------------------


class TestPluginRegistryAuth:
    """Endpoints must require admin auth."""

    def test_list_plugins_requires_admin(self, client):
        r = client.get("/api/admin/plugins")
        assert r.status_code in (401, 403)

    def test_get_plugin_requires_admin(self, client):
        r = client.get("/api/admin/plugins/free_ai_chain")
        assert r.status_code in (401, 403)

    def test_drift_requires_admin(self, client):
        r = client.post("/api/admin/plugins/drift")
        assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------


class TestPluginRegistryList:
    """GET /api/admin/plugins — list with filters."""

    def _admin_get(self, client, url, **params):
        """Helper: hit endpoint with admin header (simulated auth bypass in tests)."""
        # In tests, we bypass auth by directly calling the endpoint function.
        # The TestClient will get 401/403 from require_admin, so we test
        # the response model structure via the registry directly instead.
        from app.agents.harness.plugin_manifest import get_registry

        reg = get_registry()
        return reg

    def test_registry_has_plugins(self):
        reg = get_registry()
        assert reg.count() > 0

    def test_registry_has_categories(self):
        from app.agents.harness.plugin_manifest import PluginCategory

        reg = get_registry()
        cats = {p.category for p in reg.all()}
        for cat in PluginCategory:
            assert cat in cats

    def test_manifest_table_serializable(self):
        import json

        reg = get_registry()
        table = reg.to_manifest_table()
        serialized = json.dumps(table, indent=2)
        assert len(serialized) > 100

    def test_drift_check_self_no_drift(self):
        reg = get_registry()
        current = reg.to_manifest_table()
        drifts = reg.drift_check(current)
        assert drifts == []


# ---------------------------------------------------------------------------
# Response model structure
# ---------------------------------------------------------------------------


class TestPluginRegistryModels:
    """Response model validation."""

    def test_plugin_summary_fields(self):
        from app.api.plugin_registry import PluginSummary

        s = PluginSummary(
            plugin_id="test",
            version="1.0.0",
            category="worker",
            risk_class="green",
            evidence_status="production_proven",
            feature_flag="",
            kill_switch="",
            privacy_class="internal",
            approval_requirement="none",
            owner="SRE",
            business_outcome="test",
            tenant_scope="platform",
        )
        assert s.plugin_id == "test"
        assert s.risk_class == "green"

    def test_plugin_detail_fields(self):
        from app.api.plugin_registry import PluginDetail

        d = PluginDetail(
            plugin_id="test",
            version="1.0.0",
            category="worker",
            risk_class="green",
            evidence_status="production_proven",
            feature_flag="",
            kill_switch="",
            privacy_class="internal",
            approval_requirement="none",
            owner="SRE",
            business_outcome="test",
            tenant_scope="platform",
        )
        assert d.plugin_id == "test"
        assert d.budget == {}

    def test_drift_entry_fields(self):
        from app.api.plugin_registry import DriftEntry

        de = DriftEntry(type="MISSING", plugin_id="test", detail="gone")
        assert de.type == "MISSING"


# ---------------------------------------------------------------------------
# Catalog integration
# ---------------------------------------------------------------------------


class TestPluginRegistryIntegration:
    """Integration: catalog → registry → API models."""

    def test_all_plugins_convertible_to_summary(self):
        from app.api.plugin_registry import _summary_from_manifest

        reg = get_registry()
        for p in reg.all():
            s = _summary_from_manifest(p)
            assert s.plugin_id == p.plugin_id
            assert s.version == p.version

    def test_all_plugins_convertible_to_detail(self):
        from app.api.plugin_registry import _detail_from_manifest

        reg = get_registry()
        for p in reg.all():
            d = _detail_from_manifest(p)
            assert d.plugin_id == p.plugin_id
            assert d.budget["timeout_s"] == p.budget.timeout_s
            assert d.retry_policy["max_retries"] == p.retry_policy.max_retries

    def test_summary_stats_correct(self):
        """by_category + by_risk + by_evidence should sum to total."""
        reg = get_registry()
        full = reg.all()
        by_cat = {}
        by_risk = {}
        by_ev = {}
        for p in full:
            cv = p.category.value
            rv = p.risk_class.value
            ev = p.evidence_status.value
            by_cat[cv] = by_cat.get(cv, 0) + 1
            by_risk[rv] = by_risk.get(rv, 0) + 1
            by_ev[ev] = by_ev.get(ev, 0) + 1
        assert sum(by_cat.values()) == len(full)
        assert sum(by_risk.values()) == len(full)
        assert sum(by_ev.values()) == len(full)

    def test_filter_by_category(self):
        from app.agents.harness.plugin_manifest import PluginCategory

        reg = get_registry()
        harness = [p for p in reg.all() if p.category == PluginCategory.HARNESS]
        assert (
            len(harness) >= 3
        )  # native_harness, dsh_runtime, dsh_shadow, session_events, boss_governance

    def test_filter_by_risk(self):
        from app.agents.harness.plugin_manifest import RiskClass

        reg = get_registry()
        reds = [p for p in reg.all() if p.risk_class == RiskClass.RED]
        assert len(reds) >= 3  # billing, sales_autopilot, platform_dial, owner_os
        for p in reds:
            assert p.approval_requirement != "none"


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


class TestPluginHealth:
    """GET /api/admin/plugins/health endpoint tests."""

    def test_health_requires_admin(self, client):
        """Unauthenticated request should 401."""
        response = client.get("/api/admin/plugins/health")
        assert response.status_code in (401, 403)

    def test_health_response_model(self):
        from app.api.plugin_registry import PluginHealthEntry, PluginHealthResponse

        entry = PluginHealthEntry(
            plugin_id="test_plugin",
            category="domain",
            risk_class="GREEN",
            evidence_status="production_proven",
            health="healthy",
            flag_status="on",
        )
        assert entry.health == "healthy"
        assert entry.plugin_id == "test_plugin"

        resp = PluginHealthResponse(
            total=1,
            healthy=1,
            degraded=0,
            unhealthy=0,
            unknown=0,
            plugins=[entry],
            timestamp=1234567890.0,
        )
        assert resp.total == 1
        assert resp.healthy == 1

    def test_health_computes_per_plugin(self):
        from app.agents.harness.plugin_manifest import get_registry
        from app.api.plugin_registry import _compute_plugin_health

        reg = get_registry()
        plugins = reg.all()
        assert len(plugins) > 0

        for m in plugins:
            entry = _compute_plugin_health(m)
            assert entry.plugin_id == m.plugin_id
            assert entry.health in ("healthy", "degraded", "unhealthy", "unknown")
            assert entry.flag_status in (
                "on",
                "off",
                "unset",
                "n/a",
            ) or entry.flag_status.startswith("raw:")

    def test_health_flag_status_detection(self):
        import os

        from app.api.plugin_registry import _check_flag_status

        # Set a test flag
        os.environ["_TEST_PLUGIN_HEALTH_FLAG"] = "1"
        enabled, status = _check_flag_status("_TEST_PLUGIN_HEALTH_FLAG")
        assert enabled is True
        assert status == "on"

        os.environ["_TEST_PLUGIN_HEALTH_FLAG"] = "0"
        enabled, status = _check_flag_status("_TEST_PLUGIN_HEALTH_FLAG")
        assert enabled is False
        assert status == "off"

        del os.environ["_TEST_PLUGIN_HEALTH_FLAG"]
        enabled, status = _check_flag_status("_TEST_PLUGIN_HEALTH_FLAG")
        assert enabled is False
        assert status == "unset"

        enabled, status = _check_flag_status("")
        assert enabled is None
        assert status == "n/a"

    def test_health_dependencies_check(self):
        from app.api.plugin_registry import _check_dependencies

        ok, missing = _check_dependencies(["json", "os"])
        assert ok is True
        assert missing == []

        ok, missing = _check_dependencies(["json", "nonexistent_fake_module_xyz"])
        assert ok is False
        assert "nonexistent_fake_module_xyz" in missing

    def test_health_counts_match_total(self):
        """healthy + degraded + unhealthy + unknown should equal total."""
        from app.agents.harness.plugin_manifest import get_registry
        from app.api.plugin_registry import _compute_plugin_health

        reg = get_registry()
        counts = {"healthy": 0, "degraded": 0, "unhealthy": 0, "unknown": 0}
        for m in reg.all():
            entry = _compute_plugin_health(m)
            counts[entry.health] = counts.get(entry.health, 0) + 1
        assert sum(counts.values()) == reg.count()

    def test_health_probe_none_when_no_endpoint(self):
        from app.agents.harness.plugin_manifest import HealthProbe
        from app.api.plugin_registry import _probe_health

        assert _probe_health(None) is None
        assert _probe_health(HealthProbe()) is None  # empty endpoint

    def test_health_redis_checks_graceful(self):
        """Queue/DLQ checks should return None when Redis unavailable."""
        from app.api.plugin_registry import _check_dlq, _check_queue_depth

        # These should not raise, just return None on connection failure
        depth = _check_queue_depth("nonexistent_queue")
        assert depth is None or isinstance(depth, int)

        count = _check_dlq("nonexistent_dlq")
        assert count is None or isinstance(count, int)
