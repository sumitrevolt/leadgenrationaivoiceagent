"""Determinism + conformance of the canonical registry manifest fingerprint.

The manifest hash is a CHANGE / CONFORMANCE fingerprint: the same registry
definitions must always produce the same hash regardless of PYTHONHASHSEED,
process, container or restart. Historical non-deterministic fingerprints
(a20e2ede196c30ae / 697b56f06ed35102) are NOT authoritative post-fix values.
"""

import json
import os
import subprocess
import sys

import pytest

from app.agents.harness.registry import (
    REGISTRY,
    AuthorityClass,
    CanonicalToolRegistry,
    RiskLane,
    SideEffectClass,
    ToolDefinition,
    canonicalize_manifest_value,
)

# Deterministic canonical fingerprint of the current approved registry tool set.
# To intentionally update: change the registry, run this test, and replace this
# value with the new deterministic hash (identical across every PYTHONHASHSEED).
GOLDEN_MANIFEST = "b4009738e32b2c82"  # pragma: allowlist secret

CANONICAL_TOOLS = {
    "batch.internal.safe_calculation",
    "workflow.dag.internal_calculation",
    "agent.nikhil.revenue_operations",
    "agent.delegate.dev",
    "agent.delegate.isha",
    "agent.delegate.rohan",
    "video.brief.create",
    "video.script.write",
    "video.render.social",
    "video.qa.run",
    "video.review.whatsapp_send",
    "video.version.approve",
    "video.feedback.ingest",
    "video.social.schedule",
}


def _td(**kw):
    base = {
        "name": "test.canon.alpha",
        "version": "1.0.0",
        "description": "deterministic test tool",
        "input_schema": {
            "type": "object",
            "properties": {"n": {"type": "integer"}},
            "required": ["n"],
        },
        "risk_class": RiskLane.GREEN,
        "side_effect_class": SideEffectClass.NONE,
        "authority": AuthorityClass.INTERNAL_AUTONOMOUS,
        "allowed_agents": frozenset({"manager", "nikhil"}),
        "allowed_tenant_scopes": frozenset({"__system__", "tenant_a"}),
    }
    base.update(kw)
    return ToolDefinition(**base)


def _reg(defs):
    r = CanonicalToolRegistry()
    for d in defs:
        r.register(d)
    return r


def _subprocess_hash(seed):
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = str(seed)
    code = "from app.agents.harness.registry import REGISTRY; print(REGISTRY.manifest_hash())"
    out = subprocess.check_output([sys.executable, "-c", code], env=env, text=True)
    return out.strip()


# ---- cross-process determinism ------------------------------------------- #
@pytest.mark.parametrize("seed", ["0", "1", "2", "3", "42", "1000", "random"])
def test_manifest_hash_same_under_every_seed(seed):
    assert _subprocess_hash(seed) == GOLDEN_MANIFEST


def test_manifest_hash_one_unique_value_across_many_seeds():
    hashes = {_subprocess_hash(s) for s in ["1", "2", "3", "42", "7", "13", "random", "random"]}
    assert len(hashes) == 1
    assert hashes == {GOLDEN_MANIFEST}


def test_main_process_matches_subprocess():
    assert REGISTRY.manifest_hash() == _subprocess_hash("random")


# ---- collection ordering (unordered => same hash) ------------------------ #
def test_frozenset_agent_order_irrelevant():
    a = _reg([_td(allowed_agents=frozenset(["a", "b", "c"]))])
    b = _reg([_td(allowed_agents=frozenset(["c", "a", "b"]))])
    assert a.manifest_hash() == b.manifest_hash()


def test_tenant_scope_order_irrelevant():
    a = _reg([_td(allowed_tenant_scopes=frozenset(["__system__", "x", "y"]))])
    b = _reg([_td(allowed_tenant_scopes=frozenset(["y", "x", "__system__"]))])
    assert a.manifest_hash() == b.manifest_hash()


def test_registry_insertion_order_irrelevant():
    d1, d2, d3 = _td(name="test.canon.a"), _td(name="test.canon.b"), _td(name="test.canon.c")
    assert _reg([d1, d2, d3]).manifest_hash() == _reg([d3, d1, d2]).manifest_hash()


def test_identical_registries_same_hash():
    assert _reg([_td()]).manifest_hash() == _reg([_td()]).manifest_hash()


# ---- ordered lists preserve order (semantic) ----------------------------- #
def test_ordered_list_reordering_changes_hash():
    a = _reg([_td(input_schema={"type": "object", "required": ["a", "b"]})])
    b = _reg([_td(input_schema={"type": "object", "required": ["b", "a"]})])
    assert a.manifest_hash() != b.manifest_hash()


# ---- semantic drift (any policy change => hash change) -------------------- #
def test_name_change_changes_hash():
    assert (
        _reg([_td(name="test.canon.alpha")]).manifest_hash()
        != _reg([_td(name="test.canon.beta")]).manifest_hash()
    )


def test_version_change_changes_hash():
    assert (
        _reg([_td(version="1.0.0")]).manifest_hash() != _reg([_td(version="1.0.1")]).manifest_hash()
    )


def test_risk_change_changes_hash():
    assert (
        _reg([_td(risk_class=RiskLane.GREEN)]).manifest_hash()
        != _reg([_td(risk_class=RiskLane.AMBER)]).manifest_hash()
    )


def test_authority_change_changes_hash():
    assert (
        _reg([_td(authority=AuthorityClass.INTERNAL_AUTONOMOUS)]).manifest_hash()
        != _reg([_td(authority=AuthorityClass.APPROVAL_REQUIRED)]).manifest_hash()
    )


def test_allowed_agents_change_changes_hash():
    assert (
        _reg([_td(allowed_agents=frozenset(["manager"]))]).manifest_hash()
        != _reg([_td(allowed_agents=frozenset(["manager", "extra"]))]).manifest_hash()
    )


def test_tenant_scopes_change_changes_hash():
    assert (
        _reg([_td(allowed_tenant_scopes=frozenset(["__system__"]))]).manifest_hash()
        != _reg([_td(allowed_tenant_scopes=frozenset(["__system__", "t2"]))]).manifest_hash()
    )


def test_input_schema_change_changes_hash():
    a = _reg([_td(input_schema={"type": "object", "properties": {"n": {"type": "integer"}}})])
    b = _reg([_td(input_schema={"type": "object", "properties": {"n": {"type": "string"}}})])
    assert a.manifest_hash() != b.manifest_hash()


def test_side_effect_change_changes_hash():
    assert (
        _reg([_td(side_effect_class=SideEffectClass.NONE)]).manifest_hash()
        != _reg([_td(side_effect_class=SideEffectClass.EXTERNAL_SEND)]).manifest_hash()
    )


def test_enabled_change_changes_hash():
    assert (
        _reg([_td(enabled_by_default=True)]).manifest_hash()
        != _reg([_td(enabled_by_default=False)]).manifest_hash()
    )


# ---- serialization safety ------------------------------------------------ #
def test_canonicalize_sorts_sets():
    assert canonicalize_manifest_value(frozenset(["b", "a", "c"])) == ["a", "b", "c"]
    assert canonicalize_manifest_value({"b", "a"}) == ["a", "b"]


def test_canonicalize_preserves_list_order():
    assert canonicalize_manifest_value(["b", "a"]) == ["b", "a"]


def test_canonicalize_dict_keys_sorted():
    assert list(canonicalize_manifest_value({"b": 1, "a": 2}).keys()) == ["a", "b"]


def test_canonicalize_enum_to_value():
    assert canonicalize_manifest_value(RiskLane.AMBER) == "AMBER"
    assert canonicalize_manifest_value(SideEffectClass.NONE) == "NONE"


def test_canonicalize_nan_rejected():
    with pytest.raises(ValueError):
        json.dumps(canonicalize_manifest_value(float("nan")), allow_nan=False)


def test_canonicalize_unicode_stable():
    assert canonicalize_manifest_value("café") == "café"


def test_canonicalize_none_stable():
    assert canonicalize_manifest_value(None) is None


# ---- compatibility: registry policy unchanged ---------------------------- #
def test_five_canonical_tools_present():
    names = {t["name"] for t in REGISTRY.list_tools()}
    assert names == CANONICAL_TOOLS


def test_golden_conformance_hash():
    assert REGISTRY.manifest_hash() == GOLDEN_MANIFEST


def test_nikhil_amber_approval_required():
    d = REGISTRY.resolve("agent.nikhil.revenue_operations", "1.0.0")
    assert d.risk_class is RiskLane.AMBER
    assert d.authority is AuthorityClass.APPROVAL_REQUIRED


def test_rohan_amber():
    d = REGISTRY.resolve("agent.delegate.rohan", "1.0.0")
    assert d.risk_class is RiskLane.AMBER


def test_dev_green_readonly():
    d = REGISTRY.resolve("agent.delegate.dev", "1.0.0")
    assert d.risk_class is RiskLane.GREEN
    assert d.side_effect_class in (SideEffectClass.READ_ONLY, SideEffectClass.NONE)


def test_isha_green_readonly():
    d = REGISTRY.resolve("agent.delegate.isha", "1.0.0")
    assert d.risk_class is RiskLane.GREEN
    assert d.side_effect_class in (SideEffectClass.READ_ONLY, SideEffectClass.NONE)


def test_dag_green_none():
    d = REGISTRY.resolve("workflow.dag.internal_calculation", "1.0.0")
    assert d.risk_class is RiskLane.GREEN
    assert d.side_effect_class is SideEffectClass.NONE


def test_batch_green_readonly():
    d = REGISTRY.resolve("batch.internal.safe_calculation", "1.0.0")
    assert d.risk_class is RiskLane.GREEN
    assert d.side_effect_class is SideEffectClass.READ_ONLY


def test_manifest_view_exposes_no_callables():
    for t in REGISTRY.list_tools():
        json.dumps(t)  # must be pure JSON-native; raises if a callable leaked
