"""
Org Chart — Paperclip-inspired agent reporting hierarchy.
==========================================================

Defines manager→report relationships. Used for:
- Escalation: agent can't cancel peer's task — must escalate UP
- Request depth tracking: how deep is a delegation chain
- Org tree visualization in admin UI

The hierarchy is defined HERE as single source, derived from STAFF product teams.
Manager (boss) sits at root. Team leads per product area report to manager.
Individual contributors report to their team lead.

Usage:
    from app.platform import org_chart

    org_chart.manager_of("arjun")       # → "kavya" (voice QA → ops lead)
    org_chart.reports("kavya")           # → ["arjun", "meera", "swara", ...]
    org_chart.can_cancel("kavya", task)  # → True if kavya manages the task's agent
    org_chart.escalation_path("arjun")   # → ["kavya", "manager"]
    org_chart.full_tree()                # → nested dict for UI
"""

from __future__ import annotations

from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# --------------------------------------------------------------------------- #
# Hierarchy definition — team leads per product, ICs under them.
# manager (Boss) is root. Each product has a lead.
# --------------------------------------------------------------------------- #
TEAM_LEADS: dict[str, str] = {
    # product → team lead agent_id
    "voice": "lekha",  # Call Analytics Lead — oversees voice team
    "marketing": "rohan",  # Leads Manager — oversees marketing team
    "platform": "kavya",  # Ops Monitor — oversees platform/engineering team
}

# Explicit manager overrides (agent → manager). If not here, falls back to
# team lead based on product. Team leads report to "manager" (Boss).
MANAGER_OVERRIDES: dict[str, str] = {
    # Team leads report directly to Boss
    "lekha": "manager",
    "rohan": "manager",
    "kavya": "manager",
    "hermes": "manager",  # Infra handler — direct to boss (cross-cutting)
}


def _get_staff() -> dict[str, dict[str, Any]]:
    """Lazy load STAFF to avoid circular imports."""
    try:
        from app.platform.team import STAFF

        return STAFF
    except Exception:
        return {}


def manager_of(agent_id: str) -> str | None:
    """Get the manager of an agent. Returns None for 'manager' (root)."""
    key = agent_id.strip().lower()
    if key == "manager":
        return None  # Boss has no manager

    # Explicit override?
    if key in MANAGER_OVERRIDES:
        return MANAGER_OVERRIDES[key]

    # Team lead based on product
    staff = _get_staff()
    agent = staff.get(key)
    if not agent:
        return "manager"  # unknown → escalate to boss

    product = agent.get("product", "platform")
    lead = TEAM_LEADS.get(product, "manager")

    # Don't report to yourself
    if lead == key:
        return "manager"

    return lead


def reports(manager_id: str) -> list[str]:
    """Get direct reports of a manager."""
    key = manager_id.strip().lower()
    staff = _get_staff()
    result = []
    for agent_id in staff:
        if agent_id == key:
            continue
        if manager_of(agent_id) == key:
            result.append(agent_id)
    return sorted(result)


def escalation_path(agent_id: str, max_depth: int = 5) -> list[str]:
    """Get escalation chain from agent to root (manager/Boss).
    Returns list of manager agent_ids, NOT including the agent itself."""
    path = []
    current = agent_id.strip().lower()
    for _ in range(max_depth):
        mgr = manager_of(current)
        if mgr is None:
            break
        path.append(mgr)
        current = mgr
    return path


def can_cancel(requester: str, task_agent: str) -> bool:
    """Paperclip rule: you can only cancel tasks of your REPORTS.
    Peers must escalate UP. Manager (Boss) can cancel anyone."""
    req = requester.strip().lower()
    agent = task_agent.strip().lower()

    if req == "manager" or req == "admin" or req == "human":
        return True  # Boss/admin can cancel anything

    # Direct manager?
    if manager_of(agent) == req:
        return True

    # Check if requester is in the management chain of the task agent
    chain = escalation_path(agent)
    return req in chain


def request_depth(agent_id: str) -> int:
    """How deep is this agent in the hierarchy (0 = Boss, 1 = team lead, 2+ = IC)."""
    return len(escalation_path(agent_id))


def full_tree() -> dict[str, Any]:
    """Full org tree for UI visualization. Nested dict."""
    staff = _get_staff()

    def _build_node(agent_id: str) -> dict[str, Any]:
        info = staff.get(agent_id, {})
        direct = reports(agent_id)
        node: dict[str, Any] = {
            "id": agent_id,
            "name": info.get("name", agent_id),
            "title": info.get("title", ""),
            "emoji": info.get("emoji", ""),
            "product": info.get("product", ""),
            "depth": request_depth(agent_id),
        }
        if direct:
            node["reports"] = [_build_node(r) for r in direct]
        return node

    return _build_node("manager")


def product_teams() -> dict[str, list[dict[str, str]]]:
    """Group agents by product team with their manager."""
    staff = _get_staff()
    teams: dict[str, list[dict[str, str]]] = {}
    for agent_id, info in staff.items():
        product = info.get("product", "platform")
        if product not in teams:
            teams[product] = []
        teams[product].append(
            {
                "id": agent_id,
                "name": info.get("name", agent_id),
                "title": info.get("title", ""),
                "manager": manager_of(agent_id) or "none",
            }
        )
    return teams
