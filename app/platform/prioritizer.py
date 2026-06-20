"""
MoSCoW prioritization engine for dashboard assessment backlog.
Works on Gap and UXIssue objects produced by gap_analyzer / ux_evaluator.
"""

from __future__ import annotations

import math
from typing import Dict, List, Union

from app.platform.assessment_models import (
    BacklogItem,
    Effort,
    Gap,
    Impact,
    MoSCoW,
    Severity,
    UXIssue,
)

# ---------------------------------------------------------------------------
# Internal type alias
# ---------------------------------------------------------------------------
_Item = Union[Gap, UXIssue]

# ---------------------------------------------------------------------------
# Effort → estimated days mapping
# ---------------------------------------------------------------------------
_EFFORT_DAYS: dict[Effort, int] = {
    Effort.LOW: 1,
    Effort.MEDIUM: 3,
    Effort.HIGH: 7,
}

# ---------------------------------------------------------------------------
# Score maps used for priority rank
# ---------------------------------------------------------------------------
_IMPACT_MAP: dict[str, int] = {"high": 10, "medium": 5, "low": 2}
_EFFORT_MAP: dict[str, int] = {"high": 8, "medium": 4, "low": 1}
_MOSCOW_MAP: dict[str, int] = {
    "must_have": 100,
    "should_have": 50,
    "could_have": 20,
    "wont_have": 0,
}


def classify_moscow(item: _Item) -> MoSCoW:
    """
    Classify a Gap or UXIssue into a MoSCoW bucket.

    MUST HAVE
    - UXIssue: wcag_violation=True AND severity=CRITICAL
    - Gap:     prevalence >= 6 AND impact == HIGH
    - Gap:     blocks_core_workflow  (prevalence >= 6 AND category in navigation/action)

    SHOULD HAVE
    - Gap:     prevalence >= 3 AND impact == HIGH
    - UXIssue: wcag_violation=True AND severity=MAJOR
    - Gap:     prevalence >= 4

    COULD HAVE
    - Gap/Issue: prevalence <= 2
    - Gap:       effort == LOW AND impact == MEDIUM
    - UXIssue:   severity == MINOR

    WONT HAVE
    - Gap: backend_dependency=True AND effort == HIGH AND prevalence <= 2
    """

    if isinstance(item, UXIssue):
        return _classify_ux_issue(item)
    if isinstance(item, Gap):
        return _classify_gap(item)
    raise TypeError(f"Unsupported item type: {type(item)}")


def _classify_ux_issue(issue: UXIssue) -> MoSCoW:
    # MUST HAVE
    if issue.wcag_violation and issue.severity == Severity.CRITICAL:
        return MoSCoW.MUST_HAVE

    # SHOULD HAVE
    if issue.wcag_violation and issue.severity == Severity.MAJOR:
        return MoSCoW.SHOULD_HAVE

    # COULD HAVE — minor severity UX issues
    if issue.severity == Severity.MINOR:
        return MoSCoW.COULD_HAVE

    # Default COULD HAVE for remaining UX issues (e.g. non-wcag MAJOR)
    return MoSCoW.COULD_HAVE


def _classify_gap(gap: Gap) -> MoSCoW:
    # WONT HAVE — expensive, obscure, backend-heavy
    if gap.backend_dependency and gap.effort == Effort.HIGH and gap.prevalence <= 2:
        return MoSCoW.WONT_HAVE

    # MUST HAVE — high prevalence + high impact
    if gap.prevalence >= 6 and gap.impact == Impact.HIGH:
        return MoSCoW.MUST_HAVE

    # MUST HAVE — blocks core workflow (navigation or action, highly prevalent)
    _core_categories = {"navigation", "action"}
    if gap.prevalence >= 6 and gap.category.lower() in _core_categories:
        return MoSCoW.MUST_HAVE

    # SHOULD HAVE — moderately prevalent + high impact
    if gap.prevalence >= 3 and gap.impact == Impact.HIGH:
        return MoSCoW.SHOULD_HAVE

    # SHOULD HAVE — common feature (prevalence >= 4)
    if gap.prevalence >= 4:
        return MoSCoW.SHOULD_HAVE

    # COULD HAVE — easy wins on medium-impact features
    if gap.effort == Effort.LOW and gap.impact == Impact.MEDIUM:
        return MoSCoW.COULD_HAVE

    # COULD HAVE — low prevalence / niche
    if gap.prevalence <= 2:
        return MoSCoW.COULD_HAVE

    # Default COULD HAVE
    return MoSCoW.COULD_HAVE


def calculate_priority_rank(item: BacklogItem) -> float:
    """
    rank = moscow_score + (impact_score * 10) - (effort_score * 2)

    All three dimensions retrieved from the BacklogItem's stored scores /
    MoSCoW value.
    """
    moscow_score = _MOSCOW_MAP.get(item.moscow.value, 0)
    rank = moscow_score + (item.impact_score * 10) - (item.effort_score * 2)
    return float(rank)


def _make_backlog_item(item: _Item) -> BacklogItem:
    """Convert a Gap or UXIssue to a BacklogItem with MoSCoW + rank."""
    moscow = classify_moscow(item)

    if isinstance(item, Gap):
        impact_score = _IMPACT_MAP.get(item.impact.value, 5)
        effort_score = _EFFORT_MAP.get(item.effort.value, 4)
        estimated_days = _EFFORT_DAYS.get(item.effort, 3)
        category = item.category or "gap"
        dashboard = item.dashboard
        name = item.name
    else:  # UXIssue
        # UXIssue doesn't carry Impact/Effort enums — derive from severity
        _sev_impact = {
            Severity.CRITICAL: 10,
            Severity.MAJOR: 5,
            Severity.MINOR: 2,
        }
        _sev_effort = {
            Severity.CRITICAL: 4,  # medium effort to fix a critical accessibility bug
            Severity.MAJOR: 4,
            Severity.MINOR: 1,
        }
        _sev_days = {
            Severity.CRITICAL: 3,
            Severity.MAJOR: 2,
            Severity.MINOR: 1,
        }
        impact_score = _sev_impact.get(item.severity, 5)
        effort_score = _sev_effort.get(item.severity, 4)
        estimated_days = _sev_days.get(item.severity, 2)
        category = item.dimension or "ux"
        dashboard = item.dashboard
        name = item.name

    bi = BacklogItem(
        item=name,
        dashboard=dashboard,
        category=category,
        moscow=moscow,
        impact_score=impact_score,
        effort_score=effort_score,
        estimated_days=estimated_days,
    )
    bi.priority_rank = calculate_priority_rank(bi)
    return bi


def build_backlog(gaps: list[Gap], ux_issues: list[UXIssue]) -> list[BacklogItem]:
    """
    Combine gaps + ux_issues into a ranked BacklogItem list.

    1. Convert each item to BacklogItem (MoSCoW + score computation).
    2. Sort descending by priority_rank.
    """
    items: list[BacklogItem] = []
    for g in gaps:
        items.append(_make_backlog_item(g))
    for u in ux_issues:
        items.append(_make_backlog_item(u))

    items.sort(key=lambda x: x.priority_rank, reverse=True)
    return items


def generate_roadmap(backlog: list[BacklogItem]) -> dict:
    """
    Allocate backlog items to sprints:

    Sprint 1 (2 weeks, ~10 dev-days): all MUST HAVE items.
    Sprint 2 (2 weeks, ~10 dev-days): top SHOULD HAVE items (up to 15 dev-days).
    Sprint 3+ (4 weeks): remaining SHOULD HAVE + COULD HAVE items.

    Returns a dict with sprint lists + summary totals.
    """
    must_have = [b for b in backlog if b.moscow == MoSCoW.MUST_HAVE]
    should_have = [b for b in backlog if b.moscow == MoSCoW.SHOULD_HAVE]
    could_have = [b for b in backlog if b.moscow == MoSCoW.COULD_HAVE]
    # WONT HAVE items are excluded from the roadmap

    # Sprint 2: fill up to 15 dev-days from should_have (already sorted by rank)
    sprint2: list[BacklogItem] = []
    sprint2_days = 0
    sprint2_cap = 15
    remaining_should: list[BacklogItem] = []
    for item in should_have:
        if sprint2_days + item.estimated_days <= sprint2_cap:
            sprint2.append(item)
            sprint2_days += item.estimated_days
        else:
            remaining_should.append(item)

    sprint3_plus = remaining_should + could_have

    sprint1_days = sum(b.estimated_days for b in must_have)
    sprint3_days = sum(b.estimated_days for b in sprint3_plus)
    total_days = sprint1_days + sprint2_days + sprint3_days

    # Estimate weeks: 5 dev-days per week
    estimated_weeks = math.ceil(total_days / 5) if total_days > 0 else 0

    return {
        "sprint_1": must_have,
        "sprint_2": sprint2,
        "sprint_3_plus": sprint3_plus,
        "total_days": total_days,
        "estimated_weeks": estimated_weeks,
    }
