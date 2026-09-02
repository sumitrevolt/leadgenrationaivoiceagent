"""Canonical 31-agent bus manifest — derive from code, never invent a 32nd STAFF."""

from __future__ import annotations

from typing import Any

# Buzz channel defaults by domain team (hosted map names; IDs resolved at publish).
_TEAM_CHANNEL: dict[str, str] = {
    "coordinator": "admin",
    "platform_engineering": "ops",
    "marketing_team": "gtm",
    "sales_crm": "gtm",
    "lead_lab": "gtm",
    "voice_team": "ops",
    "qa_audit": "dev",
    "admin_finance": "admin",
}

# Agents whose role should not manufacture decision objects in bus canaries.
_NO_DECISION_EXPECTED: frozenset[str] = frozenset(
    {
        "lekha",  # observe KPIs
        "kavya",  # ops observe
        "vidya",  # finops observe
        "kabir",  # DB observe
        "diya",  # integrity observe
        "tara",  # telephony readiness observe
    }
)


def build_manifest() -> dict[str, Any]:
    """Return one canonical manifest with exactly 31 STAFF entries."""
    from app.platform import agent_maturity, office_hq
    from app.platform.team import STAFF

    topology = office_hq.coordination_topology()
    portfolio = agent_maturity.portfolio()
    by_id = {row["agent_id"]: row for row in (portfolio.get("agents") or [])}

    team_of: dict[str, str] = {"manager": "coordinator"}
    for team in topology.get("teams") or []:
        tid = str(team.get("id") or "")
        for member in team.get("members") or []:
            team_of[str(member)] = tid

    entries: list[dict[str, Any]] = []
    for agent_id, info in STAFF.items():
        profile = by_id.get(agent_id) or {}
        coord = profile.get("coordination") or {}
        gov = profile.get("governance") or {}
        mem = profile.get("memory") or {}
        kb = profile.get("knowledge") or {}
        team_id = team_of.get(agent_id) or str(coord.get("team") or "unknown")
        is_boss = agent_id == topology.get("boss") == "manager" or coord.get("role") == "boss"
        no_decision = agent_id in _NO_DECISION_EXPECTED
        entries.append(
            {
                "agent_id": agent_id,
                "display_name": info.get("name") or agent_id,
                "canonical_role": info.get("title") or "",
                "domain_team": team_id,
                "boss_parent": "manager" if not is_boss else None,
                "routing": "boss_direct" if is_boss else "boss_via_domain_team",
                "maturity_state": profile.get("setup_state") or "unknown",
                "rollout_state": profile.get("rollout_state") or "unknown",
                "tenant_namespace": mem.get("namespace") or f"staff/{agent_id}/tenant/platform",
                "memory_kb_namespace": kb.get("private") or f"staff:{agent_id}:tenant:platform",
                "allowed_event_types": _allowed_events(is_boss=is_boss, no_decision=no_decision),
                "allowed_decision_types": (
                    []
                    if no_decision
                    else (
                        ["boss_verdict", "internal_plan", "hierarchical_member_output"]
                        if is_boss
                        else ["hierarchical_member_output", "staff_task_complete", "internal_plan"]
                    )
                ),
                "no_decision_expected": no_decision,
                "default_buzz_channel": _TEAM_CHANNEL.get(team_id, "ops"),
                "owner_os_adapter": "app.platform.owner_os",
                "compliance_gates": list(
                    (coord.get("system_hard_gates") or [])
                    + ["tenant_isolation", "staff_bus_kill_switch"]
                ),
                "bus_identity_strategy": "signed_bridge_projection",
                "retry_policy": {
                    "max_attempts": 3,
                    "backoff_s": [1, 4, 16],
                    "dlq": "staff_bus.dlq",
                },
                "audit_destination": "data/staff_bus/audit.jsonl",
                "rollback_disable": "STAFF_BUS_ENABLED=0",
                "lane": gov.get("lane") or "GREEN",
                "autonomy": gov.get("autonomy") or "L0_OBSERVE",
            }
        )

    manifest = {
        "schema_version": "staff_bus.manifest.v1",
        "workforce_count": len(entries),
        "boss": "manager",
        "comb_in_staff": False,
        "teams": topology.get("teams") or [],
        "team_count": topology.get("team_count"),
        "coverage_ok": topology.get("coverage_ok"),
        "agents": entries,
        "authority": topology.get("authority") or {},
        "claim_note": (
            "Bus projections are discoverable/routable/auditable; "
            "runtime rollout_state still gates customer side-effects."
        ),
    }
    return manifest


def validate_manifest(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    """Hard checks: exactly 31, Boss+30, 7 teams, no Comb, no orphans/dupes."""
    m = manifest or build_manifest()
    agents = m.get("agents") or []
    ids = [a.get("agent_id") for a in agents]
    problems: list[str] = []

    if len(agents) != 31:
        problems.append(f"count={len(agents)} expected 31")
    if len(set(ids)) != len(ids):
        problems.append("duplicate_agent_id")
    if "manager" not in ids:
        problems.append("boss_missing")
    if any(i in ids for i in ("comb", "Comb", "builtin:comb")):
        problems.append("comb_present_in_staff")
    if m.get("comb_in_staff"):
        problems.append("comb_flag_true")

    workers = [i for i in ids if i != "manager"]
    if len(workers) != 30:
        problems.append(f"workers={len(workers)} expected 30")

    teams = m.get("teams") or []
    if len(teams) != 7:
        problems.append(f"teams={len(teams)} expected 7")

    team_members = [mem for t in teams for mem in (t.get("members") or [])]
    if sorted(team_members) != sorted(workers):
        problems.append("orphan_or_uncovered_worker")
    if len(team_members) != len(set(team_members)):
        problems.append("duplicate_team_assignment")

    namespaces = [a.get("tenant_namespace") for a in agents]
    if len(namespaces) != len(set(namespaces)):
        problems.append("tenant_namespace_collision")

    return {
        "ok": not problems,
        "problems": problems,
        "workforce_count": len(agents),
        "team_count": len(teams),
        "boss": m.get("boss"),
        "comb_in_staff": False,
    }


def _allowed_events(*, is_boss: bool, no_decision: bool) -> list[str]:
    base = [
        "task.proposed",
        "task.assigned",
        "task.accepted",
        "work.status",
        "artifact.ready",
        "handoff.requested",
        "audit.recorded",
        "task.completed",
        "task.failed",
    ]
    if no_decision:
        return base + ["work.status"]
    if is_boss:
        return base + [
            "decision.proposed",
            "second_brain.advice",
            "boss.verdict",
            "owner.review_required",
            "execution.authorized",
            "execution.refused",
        ]
    return base + [
        "decision.proposed",
        "second_brain.advice",
        "owner.review_required",
        "execution.authorized",
        "execution.refused",
    ]
