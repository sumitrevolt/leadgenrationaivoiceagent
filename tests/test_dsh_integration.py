"""
Contract tests for DSH (DeepSeek Harness) Integration.

Tests:
- DSH_RUNTIME_ENABLED flag check
- DSH_ALLOWLIST_CSV parsing
- Shadow mode control (DSH_SHADOW_MODE=0)
- /health endpoint DSH fields
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
        env = {k: v for k, v in os.environ.items() if k != "DSH_RUNTIME_ENABLED"}
        with patch.dict(os.environ, env, clear=True):
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
        env = {k: v for k, v in os.environ.items() if k != "DSH_SHADOW_ENABLED"}
        with patch.dict(os.environ, env, clear=True):
            assert dsh_integration.is_dsh_shadow_enabled() is False


@pytest.mark.skipif(not DSH_AVAILABLE, reason="DSH integration not available")
class TestDSHAllowlist:
    """Test DSH_ALLOWLIST_CSV parsing."""

    def test_empty_allowlist(self):
        """Verify empty allowlist returns empty set."""
        with patch.dict(os.environ, {"DSH_ALLOWLIST_CSV": ""}, clear=False):
            allowlist = dsh_integration.get_dsh_allowlist()
            assert allowlist == set()

    def test_single_allowlist(self):
        """Verify single agent in allowlist."""
        with patch.dict(os.environ, {"DSH_ALLOWLIST_CSV": "agent1"}, clear=False):
            allowlist = dsh_integration.get_dsh_allowlist()
            assert allowlist == {"agent1"}

    def test_multiple_allowlist(self):
        """Verify multiple agents in allowlist."""
        with patch.dict(os.environ, {"DSH_ALLOWLIST_CSV": "agent1,agent2,agent3"}, clear=False):
            allowlist = dsh_integration.get_dsh_allowlist()
            assert allowlist == {"agent1", "agent2", "agent3"}

    def test_allowlist_case_insensitive(self):
        """Verify allowlist parsing is case-insensitive."""
        with patch.dict(os.environ, {"DSH_ALLOWLIST_CSV": "AGENT1,Agent2"}, clear=False):
            allowlist = dsh_integration.get_dsh_allowlist()
            assert "agent1" in allowlist
            assert "agent2" in allowlist

    def test_allowlist_whitespace_trimmed(self):
        """Verify whitespace is trimmed from allowlist entries."""
        with patch.dict(os.environ, {"DSH_ALLOWLIST_CSV": " agent1 , agent2 "}, clear=False):
            allowlist = dsh_integration.get_dsh_allowlist()
            assert "agent1" in allowlist
            assert "agent2" in allowlist


@pytest.mark.skipif(not DSH_AVAILABLE, reason="DSH integration not available")
class TestDSHAllowlistCheck:
    """Test is_dsh_allowed function."""

    def test_empty_allowlist_allows_all(self):
        """Verify empty allowlist allows all agents/tools."""
        with patch.dict(os.environ, {"DSH_ALLOWLIST_CSV": ""}, clear=False):
            assert dsh_integration.is_dsh_allowed(agent_id="agent1") is True
            assert dsh_integration.is_dsh_allowed(agent_id="any_agent") is True

    def test_agent_in_allowlist(self):
        """Verify agent in allowlist is allowed."""
        with patch.dict(os.environ, {"DSH_ALLOWLIST_CSV": "agent1,agent2"}, clear=False):
            assert dsh_integration.is_dsh_allowed(agent_id="agent1") is True
            assert dsh_integration.is_dsh_allowed(agent_id="agent2") is True

    def test_agent_not_in_allowlist(self):
        """Verify agent not in allowlist is denied."""
        with patch.dict(os.environ, {"DSH_ALLOWLIST_CSV": "agent1"}, clear=False):
            assert dsh_integration.is_dsh_allowed(agent_id="agent2") is False

    def test_tool_in_allowlist(self):
        """Verify tool token in allowlist is allowed."""
        with patch.dict(os.environ, {"DSH_ALLOWLIST_CSV": "tool1@1.0.0"}, clear=False):
            assert dsh_integration.is_dsh_allowed(tool_token="tool1@1.0.0") is True


@pytest.mark.skipif(not DSH_AVAILABLE, reason="DSH integration not available")
class TestDSHHealthFields:
    """Test get_dsh_health_fields function."""

    def test_health_fields_default(self):
        """Verify health fields default to disabled."""
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("DSH_RUNTIME_ENABLED", "DSH_SHADOW_ENABLED", "DSH_ALLOWLIST_CSV")
        }
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
                "DSH_ALLOWLIST_CSV": "agent1,agent2",
            },
            clear=False,
        ):
            fields = dsh_integration.get_dsh_health_fields()
            assert fields["dsh_runtime_enabled"] is True
            assert fields["dsh_shadow_enabled"] is False
            assert "agent1" in fields["dsh_allowlist"]
            assert "agent2" in fields["dsh_allowlist"]


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

    def test_fail_closed_default(self):
        """Verify DSH integration fails closed by default (no runtime, no shadow)."""
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("DSH_RUNTIME_ENABLED", "DSH_SHADOW_ENABLED")
        }
        with patch.dict(os.environ, env, clear=True):
            assert dsh_integration.is_dsh_runtime_enabled() is False
            assert dsh_integration.is_dsh_shadow_enabled() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
