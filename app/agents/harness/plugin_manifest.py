"""
Plugin Manifest — machine-readable contract for every governed plugin.

Every plugin in the LeadGen AI control plane registers a ``PluginManifest``
that declares its identity, scope, risks, budgets, and evidence status.
The manifest is the single source of truth for what a plugin IS; the
``AUTOMATION_FLAGS`` registry remains the single source for whether it is ON.

Design principles:
- Additive: importing this module registers nothing until ``register()`` is called.
- Pydantic v2: validated, serialisable, deterministic.
- No app.* imports in the schema (CI/test-importable in isolation).
- Evidence labels match project vocabulary (PRODUCTION-PROVEN etc.).
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RiskClass(str, Enum):
    """How dangerous a plugin is. Drives approval + sandbox + Boss authority."""

    GREEN = "green"  # read-only / planning / reversible internal routing
    AMBER = "amber"  # customer-visible drafts / outbound proposal / config proposal
    RED = "red"  # payment / deploy / secret / deletion / compliance bypass


class EvidenceStatus(str, Enum):
    """How proven this plugin is. Only CLAIMED status; evidence lives in docs/evidence/."""

    CODE_PRESENT = "code_present"
    TEST_PROVEN = "test_proven"
    RUNTIME_PROVEN = "runtime_proven"
    PRODUCTION_PROVEN = "production_proven"


class PluginCategory(str, Enum):
    """Top-level plugin classification."""

    MODEL_ROUTING = "model_routing"
    HARNESS = "harness"
    WORKER = "worker"
    DOMAIN_CAPABILITY = "domain_capability"
    AUTOMATION = "automation"
    COORDINATION = "coordination"
    UI_PROJECTION = "ui_projection"


class PluginScope(str, Enum):
    """Tenant/agent scope of the plugin."""

    PLATFORM = "platform"  # global, all tenants
    TENANT = "tenant"  # per-customer isolation
    AGENT = "agent"  # per-STAFF-agent
    HYBRID = "hybrid"  # platform + agent overlay


class PrivacyClass(str, Enum):
    """Data privacy sensitivity of the plugin."""

    PUBLIC = "public"  # no PII, safe for public endpoints
    INTERNAL = "internal"  # platform-internal, no customer data
    CONFIDENTIAL = "confidential"  # customer PII, payment, compliance
    RESTRICTED = "restricted"  # secrets, credentials, auth tokens


# ---------------------------------------------------------------------------
# Schema models
# ---------------------------------------------------------------------------


class RetryPolicy(BaseModel):
    """Retry behaviour for a plugin."""

    model_config = ConfigDict(extra="forbid")
    max_retries: int = Field(3, ge=0, le=10)
    backoff_base_s: float = Field(1.0, ge=0.0, le=60.0)
    backoff_max_s: float = Field(60.0, ge=0.0, le=600.0)
    retry_on: list[str] = Field(default_factory=lambda: ["timeout", "5xx", "429"])
    no_retry_on: list[str] = Field(default_factory=lambda: ["401", "403", "schema_violation"])


class Budget(BaseModel):
    """Resource budgets for a plugin execution."""

    model_config = ConfigDict(extra="forbid")
    timeout_s: float = Field(30.0, ge=0.0, le=3600.0)
    token_budget: int = Field(10000, ge=0, description="Max LLM tokens per invocation")
    tool_calls_budget: int = Field(20, ge=0, description="Max tool calls per invocation")
    wall_clock_budget_s: float = Field(120.0, ge=0.0, le=3600.0)


class HealthProbe(BaseModel):
    """How to check if a plugin is healthy."""

    model_config = ConfigDict(extra="forbid")
    endpoint: str = Field("", description="HTTP endpoint or function path")
    interval_s: float = Field(60.0, ge=0.0)
    timeout_s: float = Field(5.0, ge=0.0)
    healthy_condition: str = Field("ok=true", description="Boolean expression on probe response")


class MetricsSpec(BaseModel):
    """Metrics a plugin emits."""

    model_config = ConfigDict(extra="forbid")
    counters: list[str] = Field(default_factory=list, description="Counter metric names")
    gauges: list[str] = Field(default_factory=list, description="Gauge metric names")
    histograms: list[str] = Field(default_factory=list, description="Histogram metric names")


class AuditEventTypes(BaseModel):
    """Audit events this plugin emits."""

    model_config = ConfigDict(extra="forbid")
    on_start: str = Field("", description="Event name on plugin start")
    on_success: str = Field("", description="Event name on success")
    on_failure: str = Field("", description="Event name on failure")
    on_refusal: str = Field("", description="Event name on refusal")


# ---------------------------------------------------------------------------
# Core manifest
# ---------------------------------------------------------------------------


class PluginManifest(BaseModel):
    """
    Machine-readable contract for a single plugin.

    Every plugin in the governed control plane MUST have a manifest.
    The manifest is immutable once registered (version bumps create new entries).
    """

    model_config = ConfigDict(extra="forbid")

    # Identity
    plugin_id: str = Field(..., description="Unique plugin identifier (e.g. 'dsplanner.v1')")
    version: str = Field("1.0.0", description="SemVer of this manifest")
    category: PluginCategory
    owner: str = Field(..., description="Responsible team/person (e.g. 'Boss', 'Owner', 'SRE')")

    # Business
    business_outcome: str = Field(..., description="What business value this plugin delivers")
    risk_class: RiskClass = Field(RiskClass.GREEN)

    # Scope
    tenant_scope: PluginScope = Field(PluginScope.PLATFORM)
    agent_scope: list[str] = Field(
        default_factory=list,
        description="Agent identities this plugin applies to (empty = all eligible)",
    )

    # Schema
    input_schema: dict[str, Any] = Field(
        default_factory=dict, description="JSON Schema for plugin input"
    )
    output_schema: dict[str, Any] = Field(
        default_factory=dict, description="JSON Schema for plugin output"
    )

    # Tools & capabilities
    required_tools: list[str] = Field(default_factory=list)
    capability_grants: list[str] = Field(default_factory=list)

    # Privacy
    privacy_class: PrivacyClass = Field(PrivacyClass.INTERNAL)

    # Feature flag / kill switch
    feature_flag: str = Field(
        "", description="AUTOMATION_FLAGS key that gates this plugin (empty = always on)"
    )
    kill_switch: str = Field(
        "", description="Emergency kill switch env var (empty = no kill switch)"
    )

    # Budgets
    budget: Budget = Field(default_factory=Budget)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)

    # Idempotency
    idempotency_key_contract: str = Field(
        "", description="How idempotency keys are formed (e.g. 'plugin_id + client_id + day')"
    )

    # Queue & DLQ
    queue: str = Field("", description="Celery queue this plugin routes to")
    dlq: str = Field("", description="Dead-letter queue for failed invocations")

    # Dependencies
    dependencies: list[str] = Field(
        default_factory=list, description="Other plugin_ids this depends on"
    )

    # Health & observability
    health_probe: HealthProbe = Field(default_factory=HealthProbe)
    heartbeat_slo_s: float = Field(
        300.0, ge=0.0, description="Expected max time between heartbeats"
    )
    metrics: MetricsSpec = Field(default_factory=MetricsSpec)
    audit_events: AuditEventTypes = Field(default_factory=AuditEventTypes)

    # Governance
    approval_requirement: str = Field(
        "none", description="'none' | 'owner' | 'boss_recommend' | 'boss_authorize'"
    )
    runbook_url: str = Field("", description="Link to operational runbook")
    rollback_url: str = Field("", description="Link to rollback procedure")

    # Evidence
    evidence_status: EvidenceStatus = Field(EvidenceStatus.CODE_PRESENT)
    evidence_artifacts: list[str] = Field(
        default_factory=list, description="Paths to evidence files (e.g. 'docs/evidence/DSH_*')"
    )

    # Metadata
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class PluginRegistry:
    """
    In-memory registry of all plugin manifests.

    Not a second flag platform — this catalogues WHAT each plugin is.
    ``AUTOMATION_FLAGS`` still controls WHETHER it is ON.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, PluginManifest] = {}

    def register(self, manifest: PluginManifest) -> None:
        """Register or update a plugin manifest."""
        if manifest.plugin_id in self._plugins:
            existing = self._plugins[manifest.plugin_id]
            if existing.version == manifest.version:
                # Same version = update (additive fields may change)
                self._plugins[manifest.plugin_id] = manifest
                return
            # Different version = keep both? For now, latest wins.
        self._plugins[manifest.plugin_id] = manifest

    def get(self, plugin_id: str) -> PluginManifest | None:
        return self._plugins.get(plugin_id)

    def all(self) -> list[PluginManifest]:
        return list(self._plugins.values())

    def by_category(self, category: PluginCategory) -> list[PluginManifest]:
        return [p for p in self._plugins.values() if p.category == category]

    def by_risk(self, risk: RiskClass) -> list[PluginManifest]:
        return [p for p in self._plugins.values() if p.risk_class == risk]

    def by_evidence(self, status: EvidenceStatus) -> list[PluginManifest]:
        return [p for p in self._plugins.values() if p.evidence_status == status]

    def ids(self) -> list[str]:
        return sorted(self._plugins.keys())

    def count(self) -> int:
        return len(self._plugins)

    def to_manifest_table(self) -> dict[str, dict[str, Any]]:
        """Export a machine-readable manifest table for drift detection."""
        return {
            pid: {
                "plugin_id": p.plugin_id,
                "version": p.version,
                "category": p.category.value,
                "risk_class": p.risk_class.value,
                "evidence_status": p.evidence_status.value,
                "feature_flag": p.feature_flag,
                "privacy_class": p.privacy_class.value,
                "approval_requirement": p.approval_requirement,
            }
            for pid, p in self._plugins.items()
        }

    def drift_check(self, expected: dict[str, dict[str, Any]]) -> list[str]:
        """
        Compare current registry against an expected snapshot.
        Returns list of drift descriptions (empty = no drift).
        """
        drifts: list[str] = []
        current = self.to_manifest_table()
        for pid, exp in expected.items():
            if pid not in current:
                drifts.append(f"MISSING: {pid}")
            elif current[pid] != exp:
                for key in set(list(exp.keys()) + list(current[pid].keys())):
                    if current[pid].get(key) != exp.get(key):
                        drifts.append(
                            f"CHANGED: {pid}.{key}: {exp.get(key)} -> {current[pid].get(key)}"
                        )
        for pid in current:
            if pid not in expected:
                drifts.append(f"NEW: {pid}")
        return drifts


# ---------------------------------------------------------------------------
# Singleton (lazy; import-safe)
# ---------------------------------------------------------------------------

_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    """Get or create the global plugin registry."""
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry


def register(manifest: PluginManifest) -> None:
    """Convenience: register a plugin manifest on the global registry."""
    get_registry().register(manifest)
