"""TypeSafe consumer inventory guard.

WHY THIS EXISTS (finding `talent_pool_typesafe_cost`, 2026-09-18)
-----------------------------------------------------------------
The app's only TypeSafe consumer was `app/platform/agent_talent_pool.py`, and it
was decorative in the worst way: 31 agents x 32 specializations = **992 paid
HTTP calls** at build time, whose returned answer was then looked up in a
hardcoded snake_case map, so a human-readable answer ("Cold call expert") fell
through to `"general"`. Zero modules consumed the pool at all.

A TypeSafe call that no workflow consumes is decoration, and decoration that
costs 992 round trips is a liability. It was removed
(`git checkout d4243e7a -- app/platform/agent_talent_pool.py` restores it).

This guard makes consumers an *explicit, deliberate* list: adding one is fine,
but it must be a judgment whose result actually changes downstream behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Modules allowed to reference app.platform.typesafe_integration.
# `automation_health` only reads credential_state() (config-only, no network).
ALLOWED_CONSUMERS = {
    "app/platform/automation_health.py",
    "app/agents/workers.py",
}

# The definition module itself never counts as a consumer.
_SELF = "app/platform/typesafe_integration.py"


def _reference_sites() -> set[str]:
    sites: set[str] = set()
    for path in (ROOT / "app").rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel == _SELF:
            continue
        if "typesafe_integration" in path.read_text(encoding="utf-8", errors="replace"):
            sites.add(rel)
    return sites


def test_guard_scans_real_files():
    """A guard that scans nothing is false safety."""
    assert len(list((ROOT / "app").rglob("*.py"))) > 100
    assert (ROOT / _SELF).exists()


def test_only_allowlisted_modules_reference_typesafe():
    unexpected = _reference_sites() - ALLOWED_CONSUMERS
    assert not unexpected, (
        "New TypeSafe consumer(s) detected: "
        f"{sorted(unexpected)}. If the judgment changes downstream behaviour, add "
        "the module to ALLOWED_CONSUMERS in this test with the consumer it drives. "
        "If it is decorative (or calls TypeSafe in a loop over synthetic items), "
        "do not merge it."
    )


def test_allowlist_has_no_stale_entries():
    """A stale allowlist entry hides a deleted consumer."""
    stale = ALLOWED_CONSUMERS - _reference_sites()
    assert not stale, f"ALLOWED_CONSUMERS lists modules that no longer consume: {sorted(stale)}"


def test_decorative_talent_pool_is_gone():
    """The 992-call orphan must not silently return."""
    assert not (ROOT / "app/platform/agent_talent_pool.py").exists(), (
        "agent_talent_pool.py is back — see this test's docstring before restoring it"
    )
    with pytest.raises(ImportError):
        __import__("app.platform.agent_talent_pool")


def test_admin_triage_tool_is_a_real_consumer():
    """The admin triage tool must actually call TypeSafe and persist a trace."""
    script = ROOT / "scripts/typesafe_admin_triage.py"
    src = script.read_text(encoding="utf-8")
    assert "system_one" in src, "triage tool no longer calls the System One endpoint"
    assert "typesafe_decisions.jsonl" in src, "triage tool no longer writes a trace"
    assert "downstream_action" in src, "trace must record the downstream action"
