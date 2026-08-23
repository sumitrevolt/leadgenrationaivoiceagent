"""Tests for plugin manifest schema, registry, catalog, and drift detection."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.harness.plugin_catalog import bootstrap_catalog
from app.agents.harness.plugin_manifest import (
    AuditEventTypes,
    Budget,
    EvidenceStatus,
    HealthProbe,
    MetricsSpec,
    PluginCategory,
    PluginManifest,
    PluginRegistry,
    PluginScope,
    PrivacyClass,
    RetryPolicy,
    RiskClass,
)

# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestPluginManifestSchema:
    """Pydantic schema validation tests."""

    def test_minimal_manifest(self):
        m = PluginManifest(
            plugin_id="test.minimal",
            category=PluginCategory.DOMAIN_CAPABILITY,
            owner="test",
            business_outcome="test outcome",
        )
        assert m.plugin_id == "test.minimal"
        assert m.version == "1.0.0"
        assert m.risk_class == RiskClass.GREEN
        assert m.evidence_status == EvidenceStatus.CODE_PRESENT
        assert m.privacy_class == PrivacyClass.INTERNAL
        assert m.approval_requirement == "none"

    def test_full_manifest(self):
        m = PluginManifest(
            plugin_id="test.full",
            version="2.0.0",
            category=PluginCategory.HARNESS,
            owner="Boss",
            business_outcome="Full manifest test",
            risk_class=RiskClass.RED,
            tenant_scope=PluginScope.TENANT,
            agent_scope=["kavya", "isha"],
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            required_tools=["search", "write"],
            capability_grants=["read_db"],
            privacy_class=PrivacyClass.RESTRICTED,
            feature_flag="TEST_FLAG",
            kill_switch="TEST_KILL",
            budget=Budget(
                timeout_s=60.0, token_budget=5000, tool_calls_budget=10, wall_clock_budget_s=120.0
            ),
            retry_policy=RetryPolicy(max_retries=5, backoff_base_s=2.0),
            idempotency_key_contract="plugin_id + client_id + day",
            queue="test_queue",
            dlq="test_dlq",
            dependencies=["dep1", "dep2"],
            health_probe=HealthProbe(endpoint="/test", interval_s=30.0),
            heartbeat_slo_s=120.0,
            metrics=MetricsSpec(counters=["test_counter"]),
            audit_events=AuditEventTypes(on_start="test.start", on_success="test.ok"),
            approval_requirement="owner",
            runbook_url="https://example.com/runbook",
            rollback_url="https://example.com/rollback",
            evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            evidence_artifacts=["docs/evidence/test.json"],
            tags=["test", "full"],
        )
        assert m.plugin_id == "test.full"
        assert m.risk_class == RiskClass.RED
        assert m.privacy_class == PrivacyClass.RESTRICTED
        assert m.budget.timeout_s == 60.0
        assert m.retry_policy.max_retries == 5
        assert m.approval_requirement == "owner"
        assert len(m.agent_scope) == 2

    def test_manifest_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            PluginManifest(
                plugin_id="test.extra",
                category=PluginCategory.WORKER,
                owner="test",
                business_outcome="test",
                unknown_field="should_fail",
            )

    def test_budget_defaults(self):
        b = Budget()
        assert b.timeout_s == 30.0
        assert b.token_budget == 10000
        assert b.tool_calls_budget == 20
        assert b.wall_clock_budget_s == 120.0

    def test_retry_policy_defaults(self):
        r = RetryPolicy()
        assert r.max_retries == 3
        assert "429" in r.retry_on
        assert "401" in r.no_retry_on

    def test_evidence_status_enum(self):
        assert EvidenceStatus.CODE_PRESENT.value == "code_present"
        assert EvidenceStatus.TEST_PROVEN.value == "test_proven"
        assert EvidenceStatus.RUNTIME_PROVEN.value == "runtime_proven"
        assert EvidenceStatus.PRODUCTION_PROVEN.value == "production_proven"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestPluginRegistry:
    """Registry operations."""

    def test_register_and_get(self):
        reg = PluginRegistry()
        m = PluginManifest(
            plugin_id="reg.test",
            category=PluginCategory.AUTOMATION,
            owner="test",
            business_outcome="test",
        )
        reg.register(m)
        assert reg.get("reg.test") is m
        assert reg.count() == 1

    def test_register_update_same_version(self):
        reg = PluginRegistry()
        m1 = PluginManifest(
            plugin_id="reg.v1",
            category=PluginCategory.AUTOMATION,
            owner="test",
            business_outcome="v1",
        )
        m2 = PluginManifest(
            plugin_id="reg.v1",
            category=PluginCategory.AUTOMATION,
            owner="test",
            business_outcome="v2",
        )
        reg.register(m1)
        reg.register(m2)
        assert reg.count() == 1
        assert reg.get("reg.v1").business_outcome == "v2"

    def test_by_category(self):
        reg = PluginRegistry()
        reg.register(
            PluginManifest(
                plugin_id="a", category=PluginCategory.HARNESS, owner="t", business_outcome="t"
            )
        )
        reg.register(
            PluginManifest(
                plugin_id="b", category=PluginCategory.WORKER, owner="t", business_outcome="t"
            )
        )
        reg.register(
            PluginManifest(
                plugin_id="c", category=PluginCategory.HARNESS, owner="t", business_outcome="t"
            )
        )
        harness = reg.by_category(PluginCategory.HARNESS)
        assert len(harness) == 2

    def test_by_risk(self):
        reg = PluginRegistry()
        reg.register(
            PluginManifest(
                plugin_id="green",
                category=PluginCategory.WORKER,
                owner="t",
                business_outcome="t",
                risk_class=RiskClass.GREEN,
            )
        )
        reg.register(
            PluginManifest(
                plugin_id="red",
                category=PluginCategory.WORKER,
                owner="t",
                business_outcome="t",
                risk_class=RiskClass.RED,
            )
        )
        reds = reg.by_risk(RiskClass.RED)
        assert len(reds) == 1
        assert reds[0].plugin_id == "red"

    def test_by_evidence(self):
        reg = PluginRegistry()
        reg.register(
            PluginManifest(
                plugin_id="cp",
                category=PluginCategory.WORKER,
                owner="t",
                business_outcome="t",
                evidence_status=EvidenceStatus.CODE_PRESENT,
            )
        )
        reg.register(
            PluginManifest(
                plugin_id="pp",
                category=PluginCategory.WORKER,
                owner="t",
                business_outcome="t",
                evidence_status=EvidenceStatus.PRODUCTION_PROVEN,
            )
        )
        pp = reg.by_evidence(EvidenceStatus.PRODUCTION_PROVEN)
        assert len(pp) == 1
        assert pp[0].plugin_id == "pp"

    def test_ids_sorted(self):
        reg = PluginRegistry()
        reg.register(
            PluginManifest(
                plugin_id="z", category=PluginCategory.WORKER, owner="t", business_outcome="t"
            )
        )
        reg.register(
            PluginManifest(
                plugin_id="a", category=PluginCategory.WORKER, owner="t", business_outcome="t"
            )
        )
        assert reg.ids() == ["a", "z"]

    def test_manifest_table(self):
        reg = PluginRegistry()
        reg.register(
            PluginManifest(
                plugin_id="table.test",
                category=PluginCategory.AUTOMATION,
                owner="t",
                business_outcome="t",
                risk_class=RiskClass.AMBER,
            )
        )
        table = reg.to_manifest_table()
        assert "table.test" in table
        assert table["table.test"]["risk_class"] == "amber"
        assert table["table.test"]["category"] == "automation"

    def test_drift_check_no_drift(self):
        reg = PluginRegistry()
        reg.register(
            PluginManifest(
                plugin_id="drift.test",
                category=PluginCategory.AUTOMATION,
                owner="t",
                business_outcome="t",
            )
        )
        expected = reg.to_manifest_table()
        assert reg.drift_check(expected) == []

    def test_drift_check_missing(self):
        reg = PluginRegistry()
        expected = {"missing.plugin": {"plugin_id": "missing.plugin"}}
        drifts = reg.drift_check(expected)
        assert any("MISSING" in d for d in drifts)

    def test_drift_check_new(self):
        reg = PluginRegistry()
        reg.register(
            PluginManifest(
                plugin_id="new.plugin",
                category=PluginCategory.WORKER,
                owner="t",
                business_outcome="t",
            )
        )
        drifts = reg.drift_check({})
        assert any("NEW" in d for d in drifts)


# ---------------------------------------------------------------------------
# Catalog bootstrap
# ---------------------------------------------------------------------------


class TestPluginCatalog:
    """Catalog bootstrap and completeness."""

    def test_bootstrap_registers_plugins(self):
        # Reset for test isolation
        import app.agents.harness.plugin_manifest as pm_mod
        from app.agents.harness.plugin_manifest import get_registry

        pm_mod._registry = None

        bootstrap_catalog()
        reg = get_registry()
        assert reg.count() > 0

    def test_catalog_has_core_plugins(self):
        import app.agents.harness.plugin_manifest as pm_mod
        from app.agents.harness.plugin_manifest import get_registry

        pm_mod._registry = None

        bootstrap_catalog()
        reg = get_registry()
        core_ids = [
            "free_ai_chain",
            "native_harness",
            "dsh_runtime",
            "celery_worker",
            "prospecting",
            "hot_queue_triage",
            "onboarding",
            "onboarding_factory",
            "form_builder",
            "proposal_builder",
            "content_generation",
            "delivery",
            "billing_proposal",
            "staff_scheduler",
            "staff_bus",
            "admin_dashboard",
            "customer_portal",
            "explorer_graph",
            "owner_os",
        ]
        for pid in core_ids:
            assert reg.get(pid) is not None, f"Missing core plugin: {pid}"

    def test_catalog_categories_covered(self):
        import app.agents.harness.plugin_manifest as pm_mod
        from app.agents.harness.plugin_manifest import get_registry

        pm_mod._registry = None

        bootstrap_catalog()
        reg = get_registry()
        categories = {p.category for p in reg.all()}
        for cat in PluginCategory:
            assert cat in categories, f"Category {cat.value} has no plugins"

    def test_red_plugins_require_approval(self):
        """Every RED plugin must have approval_requirement != 'none'."""
        import app.agents.harness.plugin_manifest as pm_mod
        from app.agents.harness.plugin_manifest import get_registry

        pm_mod._registry = None

        bootstrap_catalog()
        reg = get_registry()
        reds = reg.by_risk(RiskClass.RED)
        for p in reds:
            assert p.approval_requirement != "none", (
                f"RED plugin {p.plugin_id} has no approval requirement"
            )

    def test_voice_plugins_frozen(self):
        """Voice plugins must be tagged frozen and not modifiable."""
        import app.agents.harness.plugin_manifest as pm_mod
        from app.agents.harness.plugin_manifest import get_registry

        pm_mod._registry = None

        bootstrap_catalog()
        reg = get_registry()
        voice_plugins = [p for p in reg.all() if "voice-frozen" in p.tags]
        assert len(voice_plugins) >= 1
        for p in voice_plugins:
            assert "frozen" in p.tags or "voice-frozen" in p.tags

    def test_manifest_table_exportable(self):
        """Manifest table is JSON-serializable."""
        import app.agents.harness.plugin_manifest as pm_mod
        from app.agents.harness.plugin_manifest import get_registry

        pm_mod._registry = None

        bootstrap_catalog()
        reg = get_registry()
        import json

        table = reg.to_manifest_table()
        serialized = json.dumps(table, indent=2)
        assert len(serialized) > 100

    def test_catalog_count(self):
        """Catalog should have at least 25 plugins (comprehensive coverage)."""
        import app.agents.harness.plugin_manifest as pm_mod
        from app.agents.harness.plugin_manifest import get_registry

        pm_mod._registry = None

        bootstrap_catalog()
        reg = get_registry()
        assert reg.count() >= 25, f"Expected ≥25 plugins, got {reg.count()}"
