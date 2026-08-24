"""Tests for Agent OS routing policy + registry coverage (ADR-109)."""

from __future__ import annotations

from app.platform import agent_os_routing as routing
from app.platform.omniroute_client import _TASK_ROUTES, resolve_agent_task
from app.platform.team import STAFF


class TestAgentOsRoutingCoverage:
    def test_every_staff_key_has_explicit_override(self):
        missing = sorted(set(STAFF) - set(routing._AGENT_OVERRIDES))
        assert missing == [], f"STAFF keys missing from agent_os_routing: {missing}"

    def test_route_table_has_31_agents(self):
        table = routing.agent_route_table()
        assert len(table) == len(STAFF) == 31

    def test_sensitive_agents_forbid_omniroute(self):
        for key in ("swara", "nikhil", "vidya", "arnav", "priya", "raksha", "kabir"):
            assert routing.omniroute_allowed_for_agent(key) is False
            assert routing.get_agent_policy(key).omniroute_task is None

    def test_eligible_marketing_agents_use_internal_sanitized(self):
        for key in ("zara", "isha", "ravi", "manager", "dev"):
            assert routing.omniroute_allowed_for_agent(key) is True
            p = routing.get_agent_policy(key)
            assert p.privacy_class == routing.PRIVACY_INTERNAL
            assert p.omniroute_task in _TASK_ROUTES

    def test_publish_agents_require_approval(self):
        for key in ("zara", "isha", "ravi", "kiran", "anika", "ira"):
            assert routing.get_agent_policy(key).requires_human_approval_before_publish is True

    def test_unknown_agent_fail_closed(self):
        p = routing.get_agent_policy("not_a_real_agent")
        assert p.omniroute_task is None
        assert p.auto_run_allowed is False
        assert p.privacy_class == routing.PRIVACY_PROHIBITED


class TestResolveAgentTask:
    def test_generic_bulk_hook_uses_agent_ops(self):
        assert resolve_agent_task(None) == "leadgen.agent_ops"

    def test_voice_agent_returns_none(self):
        assert resolve_agent_task("swara") is None

    def test_zara_returns_agent_ops(self):
        assert resolve_agent_task("zara") == "leadgen.agent_ops"

    def test_hermes_returns_repo_analysis(self):
        assert resolve_agent_task("hermes") == "leadgen.repo_analysis"

    def test_assigned_tasks_exist_in_client_registry(self):
        for key, row in routing.agent_route_table().items():
            task = row["omniroute_task"]
            if task is None:
                continue
            assert task in _TASK_ROUTES, f"{key} task {task} not in _TASK_ROUTES"
