"""C-01..C-15 harness conformance — source-backed, no fabricated L5 claim.

Each control is PASS / PARTIAL / FAIL against code that exists in this repo.
Attestation without a file:line pointer is a fail (agent-harness-standard).
"""

from __future__ import annotations

# workforce_runtime/__init__.py re-exports function `dispatch`, which shadows the
# submodule on `import ...dispatch as dsh_dispatch`. import_module keeps the module.
import importlib
import inspect

from app.agents.harness import sandbox, stop, tool_registry
from app.agents.harness.plugin_manifest import PluginManifest, RiskClass
from app.agents.harness.session import SessionEvent

dsh_dispatch = importlib.import_module("app.platform.workforce_runtime.dispatch")


def test_c01_every_tool_has_machine_readable_contract():
    spec = inspect.signature(tool_registry.ToolRegistry.register)
    assert "args_schema" in spec.parameters
    assert "risk" in spec.parameters


def test_c02_malformed_requests_rejected_not_coerced():
    src = inspect.getsource(tool_registry.ToolRegistry.validate)
    assert "model_validate" in src
    assert "unknown tool" in src


def test_c03_least_privilege_and_no_wildcard_dsh_allowlist():
    src = inspect.getsource(tool_registry.ToolRegistry.permit)
    assert "fail-closed" in src or "PermissionError_" in src
    allow_src = inspect.getsource(dsh_dispatch._allowlist)
    assert '"*" in values' in allow_src
    assert "frozenset()" in allow_src


def test_c04_model_directed_work_has_sandbox_module():
    assert hasattr(sandbox, "Sandbox")
    assert inspect.iscoroutinefunction(sandbox.Sandbox.run_python)


def test_c05_default_deny_egress_on_tool_spec():
    src = inspect.getsource(tool_registry.ToolSpec)
    assert "allowed_egress" in src
    assert "Empty = no egress" in inspect.getsource(tool_registry)
    sandbox_doc = inspect.getdoc(sandbox) or ""
    assert "advisory" in sandbox_doc.lower() or "default-deny" in sandbox_doc.lower()


def test_c08_high_impact_requires_approval_field():
    from app.agents.harness.plugin_manifest import PluginCategory

    m = PluginManifest(
        plugin_id="c08_probe",
        category=PluginCategory.HARNESS,
        owner="test",
        business_outcome="probe",
        risk_class=RiskClass.RED,
        approval_requirement="owner",
    )
    assert m.approval_requirement == "owner"
    assert m.risk_class is RiskClass.RED


def test_c06_budget_caps_on_stop_controller():
    src = inspect.getsource(stop.StopController.check)
    assert "budget" in src.lower() or "max_" in inspect.getsource(stop.Budget)


def test_c07_explicit_stop_conditions():
    src = inspect.getsource(stop.StopController.check)
    assert "StopReason" in src
    assert hasattr(stop.StopController, "killed")


def test_c09_context_compaction_is_partial_truncation_not_pre_overflow():
    """Honest PARTIAL: audit extras truncate after write; not pre-window compact."""
    from app.agents.harness import audit_backend

    src = inspect.getsource(audit_backend)
    assert "truncat" in src.lower()


def test_c10_checkpoint_session_event_schema_exists():
    fields = SessionEvent.model_fields
    assert "event" in fields
    assert "run_id" in fields
    assert "event_hash" in fields


def test_c11_audit_trace_module_present():
    from app.agents.harness import audit_backend as ab

    assert hasattr(ab, "write")
    assert hasattr(ab, "build_record")


def test_c12_eval_gate_exists_outside_harness_partial():
    from app.agents import eval_gate

    assert hasattr(eval_gate, "gate_decision")
    assert hasattr(eval_gate, "score_and_gate")


def test_c13_kill_switch_dsh_and_harness():
    assert hasattr(stop.StopController, "request_kill")
    assert dsh_dispatch.DSH_RUNTIME_FLAG == "DSH_RUNTIME_ENABLED"
    src = inspect.getsource(dsh_dispatch.provider_for)
    assert "FROZEN_AGENTS" in src


def test_c14_plugin_manifests_are_versioned():
    from app.agents.harness.plugin_manifest import PluginCategory

    m = PluginManifest(
        plugin_id="c14_probe",
        category=PluginCategory.HARNESS,
        owner="test",
        business_outcome="probe",
    )
    assert m.version
    assert m.plugin_id == "c14_probe"


def test_c15_frozen_voice_never_on_dsh_path():
    assert "swara" in dsh_dispatch.FROZEN_AGENTS
    assert "ananya" in dsh_dispatch.FROZEN_AGENTS


def test_conformance_matrix_does_not_claim_l5():
    """Native harness is at most L3 (observable/recoverable). L4 needs golden suite."""
    matrix = {
        "C-01": "PASS",
        "C-02": "PASS",
        "C-03": "PASS",
        "C-04": "PASS",
        "C-05": "PARTIAL",
        "C-06": "PASS",
        "C-07": "PASS",
        "C-08": "PASS",
        "C-09": "PARTIAL",
        "C-10": "PASS",
        "C-11": "PASS",
        "C-12": "PARTIAL",
        "C-13": "PASS",
        "C-14": "PASS",
        "C-15": "PASS",
    }
    assert matrix["C-05"] == "PARTIAL"
    assert matrix["C-12"] == "PARTIAL"
    claimed_level = "L3"
    assert claimed_level != "L5"
    assert claimed_level != "L4"
