"""Security test — code_exec permission guardrail (defense-in-depth on armed RCE).

Confirms: trusted human identity always allowed; named automation agents need an
explicit execute_code grant (HIGH_RISK, fail-safe); permission_denied short-circuits
BEFORE any subprocess spawn. Pure-python, no real code execution.
"""

import asyncio

from app.agents import agent_permissions, code_exec


def test_trusted_identities_always_permitted():
    assert code_exec._permitted("super_admin") is True
    assert code_exec._permitted("") is True  # default → super_admin


def test_system_identity_not_auto_trusted(monkeypatch, tmp_path):
    """Audit hardening: 'system' is NOT a free pass — enforcement on + unset → deny."""
    monkeypatch.setenv("AGENT_PERMISSIONS", "1")
    monkeypatch.setattr(agent_permissions, "_DATA_FILE", str(tmp_path / "perms.json"))
    assert code_exec._permitted("system") is False


def test_named_agent_allowed_when_enforcement_off(monkeypatch):
    monkeypatch.delenv("AGENT_PERMISSIONS", raising=False)
    # enforcement off → can() allow-all → named agent permitted
    assert code_exec._permitted("rohan") is True


def test_named_agent_denied_when_enforcement_on_and_unset(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_PERMISSIONS", "1")
    monkeypatch.setattr(agent_permissions, "_DATA_FILE", str(tmp_path / "perms.json"))
    # execute_code is HIGH_RISK → unset → DENY (fail-safe)
    assert code_exec._permitted("rohan") is False


def test_named_agent_allowed_with_explicit_grant(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_PERMISSIONS", "1")
    monkeypatch.setattr(agent_permissions, "_DATA_FILE", str(tmp_path / "perms.json"))
    res = agent_permissions.set_permission("rohan", "execute_code", "allow")
    assert res["ok"] is True
    assert code_exec._permitted("rohan") is True


def test_execute_permission_denied_no_spawn(monkeypatch, tmp_path):
    """A named agent without grant must be blocked WITHOUT running anything."""
    monkeypatch.setenv("CODE_EXEC", "1")  # flag on so we get past the disabled gate
    monkeypatch.setenv("AGENT_PERMISSIONS", "1")
    monkeypatch.setattr(agent_permissions, "_DATA_FILE", str(tmp_path / "perms.json"))
    out = asyncio.run(
        code_exec.execute("import os; os.system('echo SHOULD_NOT_RUN')", agent="vikram")
    )
    assert out["ok"] is False
    assert out["error"] == "permission_denied"
    assert out["agent"] == "vikram"


def test_execute_disabled_still_first(monkeypatch):
    """Flag-off disabled gate still wins (existing behaviour preserved)."""
    monkeypatch.delenv("CODE_EXEC", raising=False)
    out = asyncio.run(code_exec.execute("print(1)", agent="rohan"))
    assert out["ok"] is False
    assert out["error"] == "disabled"


def test_execute_code_is_high_risk_category():
    assert "execute_code" in agent_permissions.TOOL_CATEGORIES
    assert "execute_code" in agent_permissions.HIGH_RISK
