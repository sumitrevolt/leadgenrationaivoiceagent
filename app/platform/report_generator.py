"""
Report generator for dashboard assessment.
Produces Markdown (DASHBOARD_ASSESSMENT_REPORT.md, PRIORITIZED_BACKLOG.md)
and JSON (dashboard_metrics.json) from an AssessmentData object.

All output is stdlib-only (no Jinja2, no third-party deps).
"""

from __future__ import annotations

import json
import pathlib
import textwrap
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.platform.assessment_models import (
    AssessmentData,
    BacklogItem,
    Feature,
    FeatureStatus,
    Gap,
    MoSCoW,
    Severity,
    UXIssue,
)
from app.platform.prioritizer import build_backlog, generate_roadmap

# ---------------------------------------------------------------------------
# Low-level Markdown helpers
# ---------------------------------------------------------------------------


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a GitHub-flavoured Markdown table."""
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    header_row = "| " + " | ".join(headers) + " |"
    data_rows = ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join([header_row, sep] + data_rows)


def _score_bar(score: float) -> str:
    """Return a compact textual indicator next to a score (0-100)."""
    if score >= 80:
        return "Good"
    if score >= 60:
        return "Fair"
    if score >= 40:
        return "Needs Work"
    return "Critical"


def _moscow_label(m: MoSCoW) -> str:
    return m.value.replace("_", " ").title()


def _feature_rows(features: list[Feature], dashboard: str) -> list[list[str]]:
    return [
        [f.name, f.category.value.replace("_", " ").title(), f.status.value.title()]
        for f in features
        if f.dashboard == dashboard
    ]


def _gap_rows(gaps: list[Gap], dashboard: str) -> list[list[str]]:
    return [
        [
            g.name,
            ", ".join(g.competitive_reference) or "—",
            str(g.prevalence),
            g.impact.value.title(),
            g.effort.value.title(),
            _moscow_label(g.moscow),
        ]
        for g in gaps
        if g.dashboard == dashboard
    ]


def _ux_rows_by_severity(issues: list[UXIssue], severity: Severity) -> list[list[str]]:
    filtered = [i for i in issues if i.severity == severity]
    return [
        [
            i.name,
            i.dashboard.title(),
            i.dimension,
            "Yes" if i.wcag_violation else "No",
            i.wcag_criterion or "—",
            textwrap.shorten(i.remediation, width=60, placeholder="...") if i.remediation else "—",
        ]
        for i in filtered
    ]


def _backlog_section(items: list[BacklogItem]) -> str:
    if not items:
        return "_No items in this category._\n"
    lines = []
    for rank, bi in enumerate(items, 1):
        effort_label = f"{bi.estimated_days}d"
        lines.append(
            f"{rank}. **{bi.item}** ({bi.dashboard}) — "
            f"Category: {bi.category} | Effort: {effort_label} | "
            f"Rank: {bi.priority_rank:.0f}"
        )
    return "\n".join(lines) + "\n"


def _sprint_section(label: str, items: list[BacklogItem]) -> str:
    if not items:
        return f"### {label}\n\n_No items._\n\n"
    total = sum(b.estimated_days for b in items)
    rows = [[b.item, b.dashboard, b.category, f"{b.estimated_days}d"] for b in items]
    table = md_table(["Item", "Dashboard", "Category", "Effort"], rows)
    return f"### {label}\n\n**Total effort:** {total} dev-days\n\n{table}\n\n"


# ---------------------------------------------------------------------------
# Main report generators
# ---------------------------------------------------------------------------


def generate_markdown_report(assessment: AssessmentData) -> str:  # noqa: C901
    """
    Generate full DASHBOARD_ASSESSMENT_REPORT.md content as a string.
    """
    a = assessment
    gaps: list[Gap] = a.gaps
    issues: list[UXIssue] = a.issues
    features: list[Feature] = a.features
    backlog: list[BacklogItem] = a.backlog or build_backlog(gaps, issues)
    roadmap = generate_roadmap(backlog)

    scores = a.scores
    cust_comp = scores.get("customer_completeness", 0.0)
    admin_comp = scores.get("admin_completeness", 0.0)
    comp_par = scores.get("competitive_parity", 0.0)
    ux_qual = scores.get("ux_quality", 0.0)

    must_items = [b for b in backlog if b.moscow == MoSCoW.MUST_HAVE]
    should_items = [b for b in backlog if b.moscow == MoSCoW.SHOULD_HAVE]
    could_items = [b for b in backlog if b.moscow == MoSCoW.COULD_HAVE]
    critical_issues = [i for i in issues if i.severity == Severity.CRITICAL]

    # Version info from scores dict (stored by audit script if available)
    cust_ver = scores.get("customer_version", "N/A")
    admin_ver = scores.get("admin_version", "N/A")

    lines: list[str] = []

    # ── 1. Header ──────────────────────────────────────────────────────────
    lines += [
        "# Dashboard Assessment Report",
        "",
        f"**Assessment ID:** `{a.assessment_id}`  ",
        f"**Generated:** {a.generated_at}  ",
        f"**Customer Dashboard Version:** {cust_ver}  ",
        f"**Admin Dashboard Version:** {admin_ver}  ",
        "",
        "---",
        "",
    ]

    # ── 2. Executive Summary ───────────────────────────────────────────────
    lines += [
        "## Executive Summary",
        "",
        md_table(
            ["Metric", "Score", "Status"],
            [
                ["Customer Completeness", f"{cust_comp:.1f}%", _score_bar(cust_comp)],
                ["Admin Completeness", f"{admin_comp:.1f}%", _score_bar(admin_comp)],
                ["Competitive Parity", f"{comp_par:.1f}%", _score_bar(comp_par)],
                ["UX Quality", f"{ux_qual:.1f}%", _score_bar(ux_qual)],
            ],
        ),
        "",
        "### Key Findings",
        "",
    ]
    # Build key findings from counts
    total_gaps = len(gaps)
    total_issues = len(issues)
    lines += [
        f"- **{len(must_items)} MUST HAVE** items require immediate attention before first paid customer.",
        f"- **{len(critical_issues)} critical UX issues** block basic usability ({len([i for i in critical_issues if i.wcag_violation])} are WCAG violations).",
        f"- **{total_gaps} feature gaps** identified across both dashboards vs. top 10 competitors.",
        f"- **{total_issues} UX issues** documented (Critical: {len(critical_issues)}, Major: {len([i for i in issues if i.severity == Severity.MAJOR])}, Minor: {len([i for i in issues if i.severity == Severity.MINOR])}).",
        f"- Estimated **{roadmap['total_days']} dev-days** ({roadmap['estimated_weeks']} weeks) to reach feature parity.",
        "",
        "---",
        "",
    ]

    # ── 3. Current State Inventory ─────────────────────────────────────────
    lines += ["## Current State Inventory", ""]

    cust_rows = _feature_rows(features, "customer")
    admin_rows = _feature_rows(features, "admin")

    lines += ["### Customer Dashboard Features", ""]
    if cust_rows:
        lines += [md_table(["Feature", "Category", "Status"], cust_rows), ""]
    else:
        lines += ["_No features catalogued._", ""]

    lines += ["### Admin Dashboard Features", ""]
    if admin_rows:
        lines += [md_table(["Feature", "Category", "Status"], admin_rows), ""]
    else:
        lines += ["_No features catalogued._", ""]

    lines += ["---", ""]

    # ── 4. Gap Analysis ────────────────────────────────────────────────────
    lines += ["## Gap Analysis", ""]

    cust_gap_rows = _gap_rows(gaps, "customer")
    admin_gap_rows = _gap_rows(gaps, "admin")

    gap_headers = ["Gap", "Competitors", "Prevalence", "Impact", "Effort", "MoSCoW"]

    lines += ["### Customer Dashboard Gaps", ""]
    if cust_gap_rows:
        lines += [md_table(gap_headers, cust_gap_rows), ""]
    else:
        lines += ["_No gaps identified._", ""]

    lines += ["### Admin Dashboard Gaps", ""]
    if admin_gap_rows:
        lines += [md_table(gap_headers, admin_gap_rows), ""]
    else:
        lines += ["_No gaps identified._", ""]

    lines += ["---", ""]

    # ── 5. UX Quality Assessment ───────────────────────────────────────────
    lines += ["## UX Quality Assessment", ""]

    ux_headers = ["Issue", "Dashboard", "Dimension", "WCAG Violation", "Criterion", "Remediation"]

    for sev_label, sev_enum in [
        ("Critical Issues", Severity.CRITICAL),
        ("Major Issues", Severity.MAJOR),
        ("Minor Issues", Severity.MINOR),
    ]:
        rows = _ux_rows_by_severity(issues, sev_enum)
        lines += [f"### {sev_label}", ""]
        if rows:
            lines += [md_table(ux_headers, rows), ""]
        else:
            lines += ["_None identified._", ""]

    lines += ["---", ""]

    # ── 6. Prioritized Backlog ─────────────────────────────────────────────
    lines += [
        "## Prioritized Backlog",
        "",
        "### Must Have",
        "",
        _backlog_section(must_items),
        "### Should Have",
        "",
        _backlog_section(should_items),
        "### Could Have",
        "",
        _backlog_section(could_items),
        "---",
        "",
    ]

    # ── 7. Roadmap to Completion ───────────────────────────────────────────
    lines += ["## Roadmap to Completion", ""]
    lines += [_sprint_section("Sprint 1 — Must Have (2 weeks)", roadmap["sprint_1"])]
    lines += [_sprint_section("Sprint 2 — Should Have (2 weeks)", roadmap["sprint_2"])]
    lines += [_sprint_section("Sprint 3+ — Remaining (4 weeks)", roadmap["sprint_3_plus"])]

    lines += [
        f"**Total estimated effort:** {roadmap['total_days']} dev-days "
        f"({roadmap['estimated_weeks']} weeks)",
        "",
        "---",
        "",
    ]

    # ── 8. Backend Dependencies ────────────────────────────────────────────
    lines += ["## Backend Dependencies", ""]

    backend_deps: list[dict] = a.backend_dependencies
    new_endpoints = [d for d in backend_deps if d.get("type") == "new_endpoint"]
    backend_changes = [d for d in backend_deps if d.get("type") == "backend_logic"]

    lines += ["### New API Endpoints Required", ""]
    if new_endpoints:
        ep_rows = [
            [
                d.get("method", "GET"),
                d.get("path", "—"),
                d.get("description", "—"),
                d.get("effort", "—"),
            ]
            for d in new_endpoints
        ]
        lines += [md_table(["Method", "Path", "Description", "Effort"], ep_rows), ""]
    else:
        lines += ["_No new endpoints required._", ""]

    lines += ["### Backend Logic Changes", ""]
    if backend_changes:
        bc_rows = [
            [d.get("component", "—"), d.get("change", "—"), d.get("effort", "—")]
            for d in backend_changes
        ]
        lines += [md_table(["Component", "Change", "Effort"], bc_rows), ""]
    else:
        lines += ["_No backend logic changes required._", ""]

    lines += ["---", ""]

    # ── 9. Appendices ─────────────────────────────────────────────────────
    lines += ["## Appendix A: Full API Endpoint Catalog", ""]
    all_endpoints: list[str] = []
    for f in features:
        all_endpoints.extend(f.api_endpoints)
    all_endpoints = sorted(set(all_endpoints))
    if all_endpoints:
        ep_rows = [[i + 1, ep] for i, ep in enumerate(all_endpoints)]
        lines += [md_table(["#", "Endpoint"], [[str(r[0]), r[1]] for r in ep_rows]), ""]
    else:
        lines += ["_No endpoints catalogued in feature inventory._", ""]

    lines += [
        "## Appendix B: Methodology",
        "",
        "This report was generated by the LeadGen AI automated dashboard assessment pipeline.",
        "",
        "**Scoring methodology:**",
        "- *Completeness* = (complete features / total features) × 100",
        "- *Competitive Parity* = (implemented competitor features / total tracked) × 100",
        "- *UX Quality* = 100 − (weighted issue penalty: critical×10 + major×4 + minor×1)",
        "",
        "**MoSCoW classification rules:**",
        "- MUST HAVE: WCAG CRITICAL violations; prevalence ≥ 6 + HIGH impact; core-workflow blocks",
        "- SHOULD HAVE: prevalence ≥ 3 + HIGH impact; WCAG MAJOR violations; prevalence ≥ 4",
        "- COULD HAVE: prevalence ≤ 2; LOW effort + MEDIUM impact; MINOR UX issues",
        "- WONT HAVE: backend-dependent + HIGH effort + prevalence ≤ 2",
        "",
        "**Priority rank formula:** `moscow_score + (impact_score × 10) − (effort_score × 2)`",
        "",
        "_End of report._",
    ]

    return "\n".join(lines) + "\n"


def generate_prioritized_backlog_md(backlog: list[BacklogItem], roadmap: dict) -> str:
    """Standalone PRIORITIZED_BACKLOG.md content."""
    must = [b for b in backlog if b.moscow == MoSCoW.MUST_HAVE]
    should = [b for b in backlog if b.moscow == MoSCoW.SHOULD_HAVE]
    could = [b for b in backlog if b.moscow == MoSCoW.COULD_HAVE]
    wont = [b for b in backlog if b.moscow == MoSCoW.WONT_HAVE]

    def _section(title: str, items: list[BacklogItem]) -> str:
        if not items:
            return f"## {title}\n\n_No items._\n\n"
        rows = [
            [
                str(i + 1),
                b.item,
                b.dashboard,
                b.category,
                str(b.estimated_days) + "d",
                str(b.impact_score),
                str(b.effort_score),
                f"{b.priority_rank:.0f}",
            ]
            for i, b in enumerate(items)
        ]
        tbl = md_table(
            ["#", "Item", "Dashboard", "Category", "Effort", "Impact", "Effort Score", "Rank"],
            rows,
        )
        total_d = sum(b.estimated_days for b in items)
        return f"## {title}\n\n**Items:** {len(items)} | **Total effort:** {total_d} dev-days\n\n{tbl}\n\n"

    lines = [
        "# Prioritized Backlog — Dashboard Assessment",
        "",
        f"**Generated:** {datetime.now(tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}  ",
        f"**Total items:** {len(backlog)} | "
        f"**Total effort:** {roadmap['total_days']} dev-days ({roadmap['estimated_weeks']} weeks)",
        "",
        "---",
        "",
        _section("MUST HAVE", must),
        _section("SHOULD HAVE", should),
        _section("COULD HAVE", could),
        _section("WONT HAVE (deferred)", wont),
        "---",
        "",
        "## Sprint Allocation Summary",
        "",
    ]

    sprint1_days = sum(b.estimated_days for b in roadmap["sprint_1"])
    sprint2_days = sum(b.estimated_days for b in roadmap["sprint_2"])
    sprint3_days = sum(b.estimated_days for b in roadmap["sprint_3_plus"])
    summary_rows = [
        ["Sprint 1 (Must Have, 2 wks)", str(len(roadmap["sprint_1"])), str(sprint1_days) + "d"],
        ["Sprint 2 (Should Have, 2 wks)", str(len(roadmap["sprint_2"])), str(sprint2_days) + "d"],
        [
            "Sprint 3+ (Remaining, 4 wks)",
            str(len(roadmap["sprint_3_plus"])),
            str(sprint3_days) + "d",
        ],
        ["**Total**", str(len(backlog)), f"**{roadmap['total_days']}d**"],
    ]
    lines += [md_table(["Phase", "Items", "Effort"], summary_rows), ""]

    return "\n".join(lines) + "\n"


def generate_json_metrics(assessment: AssessmentData) -> dict:
    """
    Returns a JSON-serialisable dict with all key assessment metrics.
    """
    a = assessment
    gaps = a.gaps
    issues = a.issues
    features = a.features
    backlog = a.backlog or build_backlog(gaps, issues)
    roadmap = generate_roadmap(backlog)

    must_items = [b for b in backlog if b.moscow == MoSCoW.MUST_HAVE]
    should_items = [b for b in backlog if b.moscow == MoSCoW.SHOULD_HAVE]

    complete_features = [f for f in features if f.status == FeatureStatus.COMPLETE]

    new_endpoints = [d for d in a.backend_dependencies if d.get("type") == "new_endpoint"]
    backend_days = sum(_effort_days_str(d.get("effort", "medium")) for d in a.backend_dependencies)

    scores = a.scores
    cust_ver = scores.get("customer_version", "unknown")
    admin_ver = scores.get("admin_version", "unknown")

    return {
        "assessment_id": a.assessment_id,
        "generated_at": a.generated_at,
        "dashboard_versions": {
            "customer": {"version": cust_ver},
            "admin": {"version": admin_ver},
        },
        "scores": {
            "customer_completeness": round(scores.get("customer_completeness", 0.0), 2),
            "admin_completeness": round(scores.get("admin_completeness", 0.0), 2),
            "competitive_parity": round(scores.get("competitive_parity", 0.0), 2),
            "ux_quality": round(scores.get("ux_quality", 0.0), 2),
        },
        "counts": {
            "total_features": len(features),
            "complete_features": len(complete_features),
            "gaps_identified": len(gaps),
            "ux_issues": len(issues),
            "must_have_items": len(must_items),
            "should_have_items": len(should_items),
        },
        "backend_impact": {
            "new_endpoints": len(new_endpoints),
            "estimated_backend_days": backend_days,
        },
        "estimated_effort": {
            "total_days": roadmap["total_days"],
            "sprints": 3 if roadmap["sprint_3_plus"] else (2 if roadmap["sprint_2"] else 1),
        },
    }


def _effort_days_str(effort_str: str) -> int:
    """Convert a freeform effort string to an integer day count."""
    s = effort_str.lower()
    if s in ("high", "5+ days", "7d", "5d"):
        return 7
    if s in ("medium", "2-4 days", "3d"):
        return 3
    if s in ("low", "<2 days", "1d"):
        return 1
    # Try to parse e.g. "3d" or "5"
    digits = "".join(c for c in s if c.isdigit())
    return int(digits) if digits else 3


# ---------------------------------------------------------------------------
# File writer
# ---------------------------------------------------------------------------


def save_reports(
    assessment: AssessmentData,
    docs_dir: pathlib.Path,
) -> dict[str, pathlib.Path]:
    """
    Write all three report files to docs_dir.

    Files written:
    - DASHBOARD_ASSESSMENT_REPORT.md
    - dashboard_metrics.json
    - PRIORITIZED_BACKLOG.md

    Returns a dict mapping logical name → absolute Path.
    """
    docs_dir.mkdir(parents=True, exist_ok=True)

    # Ensure backlog + roadmap are computed once and stored on assessment
    if not assessment.backlog:
        assessment.backlog = build_backlog(assessment.gaps, assessment.issues)
    backlog = assessment.backlog
    roadmap = generate_roadmap(backlog)

    # 1. Main markdown report
    report_path = docs_dir / "DASHBOARD_ASSESSMENT_REPORT.md"
    report_path.write_text(generate_markdown_report(assessment), encoding="utf-8")

    # 2. JSON metrics
    metrics_path = docs_dir / "dashboard_metrics.json"
    metrics = generate_json_metrics(assessment)
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")

    # 3. Prioritized backlog markdown
    backlog_path = docs_dir / "PRIORITIZED_BACKLOG.md"
    backlog_path.write_text(generate_prioritized_backlog_md(backlog, roadmap), encoding="utf-8")

    return {
        "assessment_report": report_path.resolve(),
        "metrics_json": metrics_path.resolve(),
        "prioritized_backlog": backlog_path.resolve(),
    }
