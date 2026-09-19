"""
Contract tests for DSH (DeepSeek Harness) Integration.

Tests:
- DSH_RUNTIME_ENABLED flag check
- DSH_AGENT_ALLOWLIST parsing (canonical var, FAIL-CLOSED)
- Shadow mode control (DSH_SHADOW_ENABLED)
- /health endpoint DSH fields

Regression history (2026-09-19):
    This module used to read ``DSH_ALLOWLIST_CSV`` while the flag manifest and
    the dispatch plane read ``DSH_AGENT_ALLOWLIST``, and it returned True on an
    empty allowlist. Since ``DSH_ALLOWLIST_CSV`` was defined nowhere in
    ``docker-compose.vps.yml``, the enforcement gate silently allowed every
    agent in production. ``TestDSHAllowlistFailClosed`` now pins the correct
    behaviour, including the legacy-name case that caused the bug.
"""

import os
from unittest.mock import patch

import pytest

# Try to import the integration module. If unavailable, tests will fail gracefully.
try:
    from app.integrations import dsh as dsh_integration

    DSH_AVAILABLE = True
except ImportError:
    DSH_AVAILABLE = False
    dsh_integration = None

_ALLOWLIST_VARS = ("DSH_AGENT_ALLOWLIST", "DSH_ALLOWLIST_CSV")


def _env_without(*names: str) -> dict:
    """Return a copy of os.environ with the named variables removed."""
    return {k: v for k, v in os.environ.items() if k not in names}


@pytest.mark.skipif(not DSH_AVAILABLE, reason="DSH integration not available")
class TestDSHFlagCheck:
    """Test DSH_RUNTIME_ENABLED flag check."""

    def test_dsh_runtime_disabled_by_default(self):
        """Verify DSH runtime is disabled when DSH_RUNTIME_ENABLED=0."""
        with patch.dict(os.environ, {"DSH_RUNTIME_ENABLED": "0"}, clear=False):
            assert dsh_integration.is_dsh_runtime_enabled() is False

    def test_dsh_runtime_enabled_when_set(self):
        """Verify DSH runtime is enabled when DSH_RUNTIME_ENABLED=1."""
        with patch.dict(os.environ, {"DSH_RUNTIME_ENABLED": "1"}, clear=False):
            assert dsh_integration.is_dsh_runtime_enabled() is True

    def test_dsh_runtime_disabled_when_unset(self):
        """Verify DSH runtime is disabled when DSH_RUNTIME_ENABLED is unset."""
        with patch.dict(os.environ, _env_without("DSH_RUNTIME_ENABLED"), clear=True):
            assert dsh_integration.is_dsh_runtime_enabled() is False


@pytest.mark.skipif(not DSH_AVAILABLE, reason="DSH integration not available")
class TestDSHShadowMode:
    """Test shadow mode control."""

    def test_shadow_mode_disabled_by_default(self):
        """Verify shadow mode is disabled when DSH_SHADOW_ENABLED=0."""
        with patch.dict(os.environ, {"DSH_SHADOW_ENABLED": "0"}, clear=False):
            assert dsh_integration.is_dsh_shadow_enabled() is False

    def test_shadow_mode_enabled_when_set(self):
        """Verify shadow mode is enabled when DSH_SHADOW_ENABLED=1."""
        with patch.dict(os.environ, {"DSH_SHADOW_ENABLED": "1"}, clear=False):
            assert dsh_integration.is_dsh_shadow_enabled() is True

    def test_shadow_mode_disabled_when_unset(self):
        """Verify shadow mode is disabled when DSH_SHADOW_ENABLED is unset."""
        with patch.dict(os.environ, _env_without("DSH_SHADOW_ENABLED"), clear=True):
            assert dsh_integration.is_dsh_shadow_enabled() is False


@pytest.mark.skipif(not DSH_AVAILABLE, reason="DSH integration not available")
class TestDSHAllowlist:
    """Test DSH_AGENT_ALLOWLIST parsing."""

    def test_empty_allowlist(self):
        """Verify empty allowlist returns empty set."""
        with patch.dict(os.environ, {"DSH_AGENT_ALLOWLIST": ""}, clear=False):
            assert dsh_integration.get_dsh_allowlist() == set()

    def test_single_allowlist(self):
        """Verify single agent in allowlist."""
        with patch.dict(os.environ, {"DSH_AGENT_ALLOWLIST": "agent1"}, clear=False):
            assert dsh_integration.get_dsh_allowlist() == {"agent1"}

    def test_multiple_allowlist(self):
        """Verify multiple agents in allowlist."""
        with patch.dict(os.environ, {"DSH_AGENT_ALLOWLIST": "agent1,agent2,agent3"}, clear=False):
            assert dsh_integration.get_dsh_allowlist() == {"agent1", "agent2", "agent3"}

    def test_allowlist_case_insensitive(self):
        """Verify allowlist parsing is case-insensitive."""
        with patch.dict(os.environ, {"DSH_AGENT_ALLOWLIST": "AGENT1,Agent2"}, clear=False):
            allowlist = dsh_integration.get_dsh_allowlist()
            assert "agent1" in allowlist
            assert "agent2" in allowlist

    def test_allowlist_whitespace_trimmed(self):
        """Verify whitespace is trimmed from allowlist entries."""
        with patch.dict(os.environ, {"DSH_AGENT_ALLOWLIST": " agent1 , agent2 "}, clear=False):
            allowlist = dsh_integration.get_dsh_allowlist()
            assert "agent1" in allowlist
            assert "agent2" in allowlist

    def test_wildcard_means_no_bounded_set(self):
        """Verify '*' yields an EMPTY set (deny all), matching Plane 1 dispatch."""
        with patch.dict(os.environ, {"DSH_AGENT_ALLOWLIST": "*"}, clear=False):
            assert dsh_integration.get_dsh_allowlist() == set()

    def test_wildcard_mixed_with_names_still_denies_all(self):
        """Verify '*' anywhere in the CSV collapses the set to empty."""
        with patch.dict(os.environ, {"DSH_AGENT_ALLOWLIST": "agent1,*"}, clear=False):
            assert dsh_integration.get_dsh_allowlist() == set()


@pytest.mark.skipif(not DSH_AVAILABLE, reason="DSH integration not available")
class TestDSHAllowlistCheck:
    """Test is_dsh_allowed function with a bounded allowlist."""

    def test_agent_in_allowlist(self):
        """Verify agent in allowlist is allowed."""
        with patch.dict(os.environ, {"DSH_AGENT_ALLOWLIST": "agent1,agent2"}, clear=False):
            assert dsh_integration.is_dsh_allowed(agent_id="agent1") is True
            assert dsh_integration.is_dsh_allowed(agent_id="agent2") is True

    def test_agent_not_in_allowlist(self):
        """Verify agent not in allowlist is denied."""
        with patch.dict(os.environ, {"DSH_AGENT_ALLOWLIST": "agent1"}, clear=False):
            assert dsh_integration.is_dsh_allowed(agent_id="agent2") is False

    def test_tool_in_allowlist(self):
        """Verify tool token in allowlist is allowed."""
        with patch.dict(os.environ, {"DSH_AGENT_ALLOWLIST": "tool1@1.0.0"}, clear=False):
            assert dsh_integration.is_dsh_allowed(tool_token="tool1@1.0.0") is True

    def test_no_identity_denied(self):
        """Verify a call with no identity at all is denied."""
        with patch.dict(os.environ, {"DSH_AGENT_ALLOWLIST": "agent1"}, clear=False):
            assert dsh_integration.is_dsh_allowed() is False


@pytest.mark.skipif(not DSH_AVAILABLE, reason="DSH integration not available")
class TestDSHAllowlistFailClosed:
    """Pin the fail-CLOSED contract, including the 2026-09-19 regression.

    Each test here FAILS on the pre-fix implementation
    (``if not allowlist: return True`` reading ``DSH_ALLOWLIST_CSV``).
    """

    def test_empty_allowlist_denies_all(self):
        """Verify an empty allowlist denies every agent/tool (was: allowed all)."""
        with patch.dict(os.environ, {"DSH_AGENT_ALLOWLIST": ""}, clear=False):
            assert dsh_integration.is_dsh_allowed(agent_id="agent1") is False
            assert dsh_integration.is_dsh_allowed(agent_id="any_agent") is False

    def test_unset_allowlist_denies_all(self):
        """Verify an UNSET allowlist denies every agent (the production case)."""
        with patch.dict(os.environ, _env_without(*_ALLOWLIST_VARS), clear=True):
            assert dsh_integration.get_dsh_allowlist() == set()
            assert dsh_integration.is_dsh_allowed(agent_id="jiya_makeover") is False
            assert dsh_integration.is_dsh_allowed(agent_id="any_agent") is False

    def test_wildcard_denies_all(self):
        """Verify '*' denies every agent (Plane 1 semantics: '*' = no bounded set)."""
        with patch.dict(os.environ, {"DSH_AGENT_ALLOWLIST": "*"}, clear=False):
            assert dsh_integration.is_dsh_allowed(agent_id="jiya_makeover") is False
            assert dsh_integration.is_dsh_allowed(agent_id="any_agent") is False

    def test_legacy_var_name_is_ignored(self):
        """REGRESSION PIN: the retired DSH_ALLOWLIST_CSV must grant NO authority.

        On the pre-fix code this test FAILS: the module read DSH_ALLOWLIST_CSV,
        so setting it to "agent1" returned True. It is defined nowhere in
        docker-compose.vps.yml, so in production the gate allowed everyone.
        """
        env = _env_without(*_ALLOWLIST_VARS)
        env["DSH_ALLOWLIST_CSV"] = "agent1,jiya_makeover"
        with patch.dict(os.environ, env, clear=True):
            assert dsh_integration.get_dsh_allowlist() == set()
            assert dsh_integration.is_dsh_allowed(agent_id="agent1") is False
            assert dsh_integration.is_dsh_allowed(agent_id="jiya_makeover") is False

    def test_legacy_var_cannot_widen_canonical_allowlist(self):
        """Verify the legacy name cannot add identities to a bounded canonical set."""
        env = _env_without(*_ALLOWLIST_VARS)
        env["DSH_AGENT_ALLOWLIST"] = "jiya_makeover"
        env["DSH_ALLOWLIST_CSV"] = "attacker_agent"
        with patch.dict(os.environ, env, clear=True):
            assert dsh_integration.get_dsh_allowlist() == {"jiya_makeover"}
            assert dsh_integration.is_dsh_allowed(agent_id="attacker_agent") is False
            assert dsh_integration.is_dsh_allowed(agent_id="jiya_makeover") is True


@pytest.mark.skipif(not DSH_AVAILABLE, reason="DSH integration not available")
class TestDSHHealthFields:
    """Test get_dsh_health_fields function."""

    def test_health_fields_default(self):
        """Verify health fields default to disabled with an empty allowlist."""
        env = _env_without(
            "DSH_RUNTIME_ENABLED",
            "DSH_SHADOW_ENABLED",
            *_ALLOWLIST_VARS,
        )
        with patch.dict(os.environ, env, clear=True):
            fields = dsh_integration.get_dsh_health_fields()
            assert fields["dsh_runtime_enabled"] is False
            assert fields["dsh_shadow_enabled"] is False
            assert fields["dsh_allowlist"] == []

    def test_health_fields_enabled(self):
        """Verify health fields when DSH is enabled."""
        with patch.dict(
            os.environ,
            {
                "DSH_RUNTIME_ENABLED": "1",
                "DSH_SHADOW_ENABLED": "0",
                "DSH_AGENT_ALLOWLIST": "agent1,agent2",
            },
            clear=False,
        ):
            fields = dsh_integration.get_dsh_health_fields()
            assert fields["dsh_runtime_enabled"] is True
            assert fields["dsh_shadow_enabled"] is False
            assert "agent1" in fields["dsh_allowlist"]
            assert "agent2" in fields["dsh_allowlist"]

    def test_health_reports_the_allowlist_enforcement_reads(self):
        """Verify /health cannot disagree with the gate that actually runs.

        Pre-fix, /health reported DSH_ALLOWLIST_CSV while dispatch reported
        DSH_AGENT_ALLOWLIST -- two contradictory allowlist truths.
        """
        env = _env_without(*_ALLOWLIST_VARS)
        env["DSH_AGENT_ALLOWLIST"] = "jiya_makeover"
        with patch.dict(os.environ, env, clear=True):
            fields = dsh_integration.get_dsh_health_fields()
            assert fields["dsh_allowlist"] == ["jiya_makeover"]


@pytest.mark.skipif(not DSH_AVAILABLE, reason="DSH integration not available")
class TestDSHIntegrationContract:
    """Contract tests for DSH integration."""

    def test_integration_module_importable(self):
        """Verify DSH integration module is importable."""
        from app.integrations import dsh as dsh_mod

        assert dsh_mod is not None

    def test_all_required_functions_present(self):
        """Verify all required functions are present."""
        from app.integrations import dsh as dsh_mod

        assert hasattr(dsh_mod, "is_dsh_runtime_enabled")
        assert hasattr(dsh_mod, "is_dsh_shadow_enabled")
        assert hasattr(dsh_mod, "get_dsh_allowlist")
        assert hasattr(dsh_mod, "get_dsh_health_fields")
        assert hasattr(dsh_mod, "is_dsh_allowed")

    def test_canonical_allowlist_var_matches_dispatch_plane(self):
        """Verify this module and the dispatch plane read the SAME variable.

        Guards against re-splitting the gate into two names, which is exactly
        what let it silently fail open in production.
        """
        import importlib

        from app.integrations import dsh as dsh_mod

        dispatch_mod = importlib.import_module("app.platform.workforce_runtime.dispatch")
        assert dsh_mod.ALLOWLIST_ENV == dispatch_mod.DSH_ALLOWLIST_FLAG
        assert dsh_mod.ALLOWLIST_ENV == "DSH_AGENT_ALLOWLIST"

    def test_fail_closed_default(self):
        """Verify DSH integration fails closed by default (no runtime, no shadow, no allowlist)."""
        env = _env_without(
            "DSH_RUNTIME_ENABLED",
            "DSH_SHADOW_ENABLED",
            *_ALLOWLIST_VARS,
        )
        with patch.dict(os.environ, env, clear=True):
            assert dsh_integration.is_dsh_runtime_enabled() is False
            assert dsh_integration.is_dsh_shadow_enabled() is False
            assert dsh_integration.get_dsh_allowlist() == set()
            assert dsh_integration.is_dsh_allowed(agent_id="any_agent") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
