"""Canonical 14-combo routing contract (2026-09-05).

The app's `_TASK_ROUTES` must reference the CANONICAL `leadsgen combo N`
ids that actually exist in the gateway DB (see scripts/seed_omniroute_14combos.py)
— legacy alias ids (leadgen-free-first, hermes-*, claude-code, vps-01/02) are
registered as same-UUID aliases for backward compat but are NOT the routing
authority anymore.

Rules pinned here:
  1. Every primary/fallback model id is a canonical `leadsgen combo N` id.
  2. Every route's primary is a DIFFERENT combo from its fallback (a dead lane
     must never route to itself).
  3. All 14 canonical combos are referenced across the route table, so each
     combo's worker actually receives traffic.
  4. Each combo appears at most once as a primary (one job owns each worker).
  5. Every staff-agent task type resolves to a route in the registry.
"""

from __future__ import annotations

import re

from app.platform.agent_os_routing import agent_route_table
from app.platform.omniroute_client import _TASK_ROUTES, list_task_routes
from app.platform.team import STAFF

CANONICAL = {f"leadsgen combo {n}" for n in range(1, 15)}
_CANONICAL_RE = re.compile(r"^leadsgen combo ([1-9]|1[0-4])$")


class TestCanonicalComboRouting:
    def test_all_route_models_are_canonical_combo_ids(self):
        for task, route in list_task_routes().items():
            assert _CANONICAL_RE.match(route.primary_model), (
                f"{task} primary {route.primary_model!r} is not a canonical combo id"
            )
            assert _CANONICAL_RE.match(route.fallback_model), (
                f"{task} fallback {route.fallback_model!r} is not a canonical combo id"
            )

    def test_primary_never_equals_fallback(self):
        for task, route in list_task_routes().items():
            assert route.primary_model != route.fallback_model, (
                f"{task} routes to itself ({route.primary_model})"
            )

    def test_all_14_combos_referenced(self):
        referenced = set()
        for route in list_task_routes().values():
            referenced.add(route.primary_model)
            referenced.add(route.fallback_model)
        missing = CANONICAL - referenced
        assert not missing, f"combos never referenced by routing: {sorted(missing)}"

    def test_each_combo_owns_at_most_one_primary(self):
        primaries = [r.primary_model for r in list_task_routes().values()]
        dupes = {c for c in primaries if primaries.count(c) > 1}
        assert not dupes, f"combos owning more than one primary route: {dupes}"

    def test_all_12_task_types_registered(self):
        assert len(_TASK_ROUTES) == 12
        assert set(_TASK_ROUTES) == {
            "leadgen.coding_primary",
            "leadgen.coding_fast",
            "leadgen.repo_analysis",
            "leadgen.test_generation",
            "leadgen.agent_ops",
            "leadgen.swara_live",
            "leadgen.marketing_content",
            "leadgen.prospect_enrich",
            "leadgen.outreach_email",
            "leadgen.seo_keyword",
            "leadgen.governor_review",
            "leadgen.project_best",
        }

    def test_every_agent_task_resolves_to_canonical_route(self):
        table = agent_route_table()
        assert len(table) == len(STAFF) == 31
        for key, row in table.items():
            task = row.get("omniroute_task")
            if task is None:
                continue
            assert task in _TASK_ROUTES, f"{key} task {task} missing from registry"
            route = _TASK_ROUTES[task]
            assert _CANONICAL_RE.match(route.primary_model), (
                f"{key} -> {task} primary {route.primary_model!r} not canonical"
            )
