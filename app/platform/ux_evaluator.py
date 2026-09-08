"""
UX Evaluator — static heuristic analysis of dashboard HTML files.
Uses regex only (no BeautifulSoup/lxml dependency).
Evaluates 9 UX dimensions and produces UXIssue objects with WCAG metadata.

Data source: data/ux_checklist.json
"""

from __future__ import annotations

import json
import logging
import pathlib
import re
from typing import Dict, List, Optional

from .assessment_models import Evidence, Severity, UXIssue

log = logging.getLogger(__name__)

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
UX_CHECKLIST_PATH = ROOT / "data" / "ux_checklist.json"

# Total check count used in scoring denominator.
# 9 checks × 3 (max weight per CRITICAL) = denominator basis.
_TOTAL_CHECKS = 9


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_ux_checklist() -> dict:
    """Load ux_checklist.json; raises RuntimeError if missing or malformed."""
    try:
        with open(UX_CHECKLIST_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise RuntimeError(f"ux_checklist.json not found at {UX_CHECKLIST_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ux_checklist.json is malformed: {exc}") from exc


def _read_html(filepath: pathlib.Path) -> str:
    """Read HTML file, return empty string on any IO error (issue detected by caller)."""
    try:
        return filepath.read_text(encoding="utf-8", errors="ignore")
    except (FileNotFoundError, PermissionError) as exc:
        log.error("Cannot read dashboard file %s: %s", filepath, exc)
        return ""


def _count_pattern(pattern: str, html: str, flags: int = re.IGNORECASE) -> int:
    """Return count of all non-overlapping regex matches."""
    return len(re.findall(pattern, html, flags))


def _find_evidence(pattern: str, html: str, max_snippets: int = 3) -> Evidence:
    """Build Evidence object: line numbers + code snippets for first few matches."""
    lines = html.split("\n")
    found_lines: list[int] = []
    snippets: list[str] = []

    for i, line in enumerate(lines, 1):
        if re.search(pattern, line, re.IGNORECASE):
            found_lines.append(i)
            if len(snippets) < max_snippets:
                snippets.append(line.strip()[:120])
        if len(found_lines) >= 5:
            break

    return Evidence(line_numbers=found_lines, code_snippets=snippets)


def _next_id(counter: list[int]) -> str:
    """Thread-unsafe monotonic ID generator via mutable list trick."""
    counter[0] += 1
    return f"ux_{counter[0]:03d}"


# ---------------------------------------------------------------------------
# Individual check functions
# Each returns Optional[UXIssue] — None means check passed.
# ---------------------------------------------------------------------------


def _check_loading_states(html: str, dashboard: str, counter: list[int]) -> UXIssue | None:
    """MAJOR: missing spinner/skeleton loading indicators."""
    patterns = [
        r"spinner",
        r"skeleton",
        r"aria-busy",
        r"\.loading\b",
        r"class=[\"'][^\"']*\bloading\b",
    ]
    found = any(re.search(p, html, re.IGNORECASE) for p in patterns)
    if found:
        return None

    # Also accept any element with loading in text content
    if re.search(r"loading\.\.\.|please wait|data.*load", html, re.IGNORECASE):
        return None

    return UXIssue(
        id=_next_id(counter),
        name="Missing Loading States",
        dashboard=dashboard,
        dimension="loading_states",
        severity=Severity.MAJOR,
        wcag_violation=False,
        wcag_criterion=None,
        user_impact=(
            "Users see blank screens or stale data during API calls, "
            "leading to confusion and perceived slowness."
        ),
        evidence=Evidence(line_numbers=[], code_snippets=[]),
        remediation=(
            "Add <div class='skeleton'> placeholder rows for tables and a "
            "<span class='spinner' aria-label='Loading...'> for async sections. "
            "Show on fetch start, hide on data arrival or error."
        ),
    )


def _check_empty_states(html: str, dashboard: str, counter: list[int]) -> UXIssue | None:
    """MINOR: no empty-state illustrations or messages."""
    patterns = [
        r"empty[\-_]state",
        r"no.{0,10}data",
        r"no.{0,10}result",
        r"nothing.{0,10}found",
        r"koi.{0,10}nahi",
        r"empty.{0,10}illustration",
        r"class=[\"'][^\"']*empty[^\"']*[\"']",
    ]
    found = any(re.search(p, html, re.IGNORECASE) for p in patterns)
    if found:
        return None

    return UXIssue(
        id=_next_id(counter),
        name="Missing Empty State Messages",
        dashboard=dashboard,
        dimension="empty_states",
        severity=Severity.MINOR,
        wcag_violation=False,
        wcag_criterion=None,
        user_impact=(
            "When tables or lists have no data, the user sees a blank area "
            "with no guidance — feels broken."
        ),
        evidence=Evidence(line_numbers=[], code_snippets=[]),
        remediation=(
            "Add empty-state <div> with an SVG illustration and a helpful CTA "
            "(e.g. 'No leads yet — Import your first CSV')."
        ),
    )


def _check_error_handling(html: str, dashboard: str, counter: list[int]) -> UXIssue | None:
    """MAJOR: no .catch() or error handler in JS fetch calls."""
    # Look for .catch(), try/catch, onerror, window.onerror, error callback patterns
    patterns = [
        r"\.catch\s*\(",
        r"\bcatch\s*\(",
        r"onerror\s*=",
        r"window\.onerror",
        r"\.on\s*\(\s*['\"]error['\"]",
        r"error.*message|showError|displayError",
    ]
    found = any(re.search(p, html, re.IGNORECASE) for p in patterns)
    if found:
        return None

    evidence = _find_evidence(r"fetch\s*\(|axios\.", html)
    return UXIssue(
        id=_next_id(counter),
        name="Missing JavaScript Error Handlers",
        dashboard=dashboard,
        dimension="error_states",
        severity=Severity.MAJOR,
        wcag_violation=False,
        wcag_criterion=None,
        user_impact=(
            "Unhandled network errors silently fail; users see no feedback when API "
            "calls return 4xx/5xx, causing confusion and abandoned sessions."
        ),
        evidence=evidence,
        remediation=(
            "Add .catch(err => showToast(err.message, 'error')) to every fetch() call. "
            "Add a global window.onerror handler for unexpected JS errors."
        ),
    )


def _check_aria_labels(html: str, dashboard: str, counter: list[int]) -> UXIssue | None:
    """MAJOR WCAG 4.1.2: fewer than 5 aria-label occurrences."""
    count = _count_pattern(r"aria-label\s*=", html)
    if count >= 5:
        return None

    evidence = _find_evidence(r"aria-label\s*=", html)
    return UXIssue(
        id=_next_id(counter),
        name="Insufficient ARIA Labels",
        dashboard=dashboard,
        dimension="screen_reader_support",
        severity=Severity.MAJOR,
        wcag_violation=True,
        wcag_criterion="4.1.2 Name, Role, Value",
        user_impact=(
            f"Only {count} aria-label attribute(s) found. Screen reader users cannot "
            "understand icon buttons, status badges, or interactive elements without labels."
        ),
        evidence=evidence,
        remediation=(
            "Add aria-label to every icon-only button (e.g. <button aria-label='Delete lead'>), "
            "navigation landmarks, and dynamic regions. "
            "Aim for at least one aria-label or aria-labelledby per interactive component."
        ),
    )


def _check_keyboard_focus(html: str, dashboard: str, counter: list[int]) -> UXIssue | None:
    """
    CRITICAL WCAG 2.4.7: outline:none or outline:0 present AND :focus styles absent
    or insufficient.
    """
    # Detect outline suppression
    has_outline_none = bool(re.search(r"outline\s*:\s*(?:none|0\s*;?)", html, re.IGNORECASE))
    has_outline_zero = bool(re.search(r"outline\s*:\s*0\b", html, re.IGNORECASE))
    outline_suppressed = has_outline_none or has_outline_zero

    if not outline_suppressed:
        return None

    # Check if there's a compensating :focus override
    has_focus_override = bool(
        re.search(
            r":focus(?:-visible)?\s*\{[^}]*(?:outline|box-shadow|border)",
            html,
            re.IGNORECASE | re.DOTALL,
        )
    )
    if has_focus_override:
        return None

    evidence = _find_evidence(r"outline\s*:\s*(?:none|0)", html)
    return UXIssue(
        id=_next_id(counter),
        name="Focus Indicator Suppressed Without Override",
        dashboard=dashboard,
        dimension="focus_indicators",
        severity=Severity.CRITICAL,
        wcag_violation=True,
        wcag_criterion="2.4.7 Focus Visible",
        user_impact=(
            "Keyboard-only users cannot see which element is focused. "
            "This is a Level AA WCAG failure and blocks keyboard navigation entirely."
        ),
        evidence=evidence,
        remediation=(
            "Remove 'outline: none' from global resets, OR add a :focus-visible override: "
            ":focus-visible { outline: 2px solid #0066FF; outline-offset: 2px; }. "
            "Test by tabbing through the entire dashboard."
        ),
    )


def _check_semantic_html(html: str, dashboard: str, counter: list[int]) -> UXIssue | None:
    """MINOR: missing <main>, <nav>, or <header> landmark elements."""
    has_main = bool(re.search(r"<main\b", html, re.IGNORECASE))
    has_nav = bool(re.search(r"<nav\b", html, re.IGNORECASE))
    has_header = bool(re.search(r"<header\b", html, re.IGNORECASE))

    missing = []
    if not has_main:
        missing.append("<main>")
    if not has_nav:
        missing.append("<nav>")
    if not has_header:
        missing.append("<header>")

    if not missing:
        return None

    return UXIssue(
        id=_next_id(counter),
        name="Missing Semantic HTML Landmarks",
        dashboard=dashboard,
        dimension="screen_reader_support",
        severity=Severity.MINOR,
        wcag_violation=True,
        wcag_criterion="1.3.6 Identify Purpose",
        user_impact=(
            f"Missing semantic landmarks: {', '.join(missing)}. "
            "Screen reader users rely on landmarks to jump between page sections."
        ),
        evidence=Evidence(line_numbers=[], code_snippets=[]),
        remediation=(
            "Wrap the main content area in <main>, wrap the sidebar in <nav>, "
            "and wrap the topbar in <header>. "
            "These replace <div id='main'> / <div id='nav'> patterns."
        ),
    )


def _check_alt_text(html: str, dashboard: str, counter: list[int]) -> UXIssue | None:
    """MAJOR WCAG 1.1.1: <img> tags without alt attribute."""
    # All <img> tags
    img_tags = re.findall(r"<img\b[^>]*>", html, re.IGNORECASE | re.DOTALL)
    bad_imgs = [tag for tag in img_tags if not re.search(r"\balt\s*=", tag, re.IGNORECASE)]

    if not bad_imgs:
        return None

    snippets = [t[:120] for t in bad_imgs[:3]]
    # Find approximate line numbers
    lines = html.split("\n")
    found_lines = []
    for i, line in enumerate(lines, 1):
        if re.search(r"<img\b", line, re.IGNORECASE) and not re.search(
            r"\balt\s*=", line, re.IGNORECASE
        ):
            found_lines.append(i)
        if len(found_lines) >= 5:
            break

    return UXIssue(
        id=_next_id(counter),
        name="Images Missing Alt Text",
        dashboard=dashboard,
        dimension="screen_reader_support",
        severity=Severity.MAJOR,
        wcag_violation=True,
        wcag_criterion="1.1.1 Non-text Content",
        user_impact=(
            f"{len(bad_imgs)} <img> tag(s) have no alt attribute. "
            "Screen readers announce them as unlabelled images; decorative images "
            "should use alt='' to be skipped."
        ),
        evidence=Evidence(line_numbers=found_lines, code_snippets=snippets),
        remediation=(
            "Add alt='descriptive text' to informative images. "
            "Use alt='' for decorative images so screen readers skip them. "
            "Never omit the alt attribute entirely."
        ),
    )


def _check_form_labels(html: str, dashboard: str, counter: list[int]) -> UXIssue | None:
    """MAJOR WCAG 1.3.1: <input> elements without associated <label> or aria-label."""
    # Count inputs excluding hidden/submit/button/image types
    inputs = re.findall(
        r'<input\b(?![^>]*type\s*=\s*["\'](?:hidden|submit|button|image|reset|checkbox|radio)["\'])[^>]*>',
        html,
        re.IGNORECASE | re.DOTALL,
    )
    unlabelled = []
    for tag in inputs:
        has_id = re.search(r'\bid\s*=\s*["\']([^"\']+)["\']', tag, re.IGNORECASE)
        has_aria_label = re.search(r"aria-label(?:ledby)?\s*=", tag, re.IGNORECASE)
        has_title = re.search(r"\btitle\s*=", tag, re.IGNORECASE)

        if has_aria_label or has_title:
            continue  # has programmatic label

        if has_id:
            input_id = has_id.group(1)
            # Check if a <label for="..."> or <label> immediately wrapping exists
            label_pattern = rf'<label\b[^>]*\bfor\s*=\s*["\'{re.escape(input_id)}["\']'
            if re.search(label_pattern, html, re.IGNORECASE):
                continue

        unlabelled.append(tag)

    if not unlabelled:
        return None

    snippets = [t[:120] for t in unlabelled[:3]]
    lines = html.split("\n")
    found_lines = []
    for i, line in enumerate(lines, 1):
        if re.search(r"<input\b", line, re.IGNORECASE) and not re.search(
            r"aria-label|<label", line, re.IGNORECASE
        ):
            found_lines.append(i)
        if len(found_lines) >= 5:
            break

    return UXIssue(
        id=_next_id(counter),
        name="Form Inputs Missing Labels",
        dashboard=dashboard,
        dimension="form_validation",
        severity=Severity.MAJOR,
        wcag_violation=True,
        wcag_criterion="1.3.1 Info and Relationships",
        user_impact=(
            f"{len(unlabelled)} text input(s) have no associated <label> or aria-label. "
            "Screen reader users cannot determine what to type into the field. "
            "Placeholder text alone is not sufficient."
        ),
        evidence=Evidence(line_numbers=found_lines, code_snippets=snippets),
        remediation=(
            "Associate every input with a label via <label for='inputId'> "
            "or aria-label='Description'. "
            "If a visible label is not desired, use aria-label or visually-hidden <label>."
        ),
    )


def _check_responsive(html: str, dashboard: str, counter: list[int]) -> UXIssue | None:
    """MAJOR: missing @media query or viewport meta tag."""
    has_viewport = bool(re.search(r'name\s*=\s*["\']viewport["\']', html, re.IGNORECASE))
    has_media = bool(re.search(r"@media\b", html, re.IGNORECASE))

    issues: list[str] = []
    if not has_viewport:
        issues.append("missing viewport meta tag")
    if not has_media:
        issues.append("no @media breakpoints")

    if not issues:
        return None

    return UXIssue(
        id=_next_id(counter),
        name="Responsive Design Issues",
        dashboard=dashboard,
        dimension="responsive_breakpoints",
        severity=Severity.MAJOR,
        wcag_violation=False,
        wcag_criterion=None,
        user_impact=(
            f"Dashboard may be unusable on mobile/tablet devices ({', '.join(issues)}). "
            "Mobile users will see unscaled or overflowing layout."
        ),
        evidence=Evidence(line_numbers=[], code_snippets=[]),
        remediation=(
            "Add <meta name='viewport' content='width=device-width, initial-scale=1'> "
            "in <head>. Add @media (max-width: 768px) CSS rules for mobile layout. "
            "Test on Chrome DevTools mobile emulator."
        ),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_dashboard(filepath: pathlib.Path, dashboard_name: str) -> list[UXIssue]:
    """
    Run all UX heuristic checks against a dashboard HTML file.

    Args:
        filepath:        Absolute path to the HTML file.
        dashboard_name:  "customer" or "admin" (used for issue labelling).

    Returns:
        List[UXIssue] — one entry per failed check; passed checks are omitted.
    """
    html = _read_html(filepath)
    if not html:
        # File missing / unreadable — return a single critical issue
        return [
            UXIssue(
                id="ux_001",
                name="Dashboard File Not Found",
                dashboard=dashboard_name.lower(),
                dimension="loading_states",
                severity=Severity.CRITICAL,
                wcag_violation=False,
                user_impact="Dashboard HTML file could not be read; all checks skipped.",
                evidence=Evidence(line_numbers=[], code_snippets=[str(filepath)]),
                remediation=f"Ensure the file exists at {filepath}.",
            )
        ]

    counter: list[int] = [0]
    dash = dashboard_name.lower()

    # Run all checks in order; None return = passed
    checks = [
        _check_loading_states(html, dash, counter),
        _check_empty_states(html, dash, counter),
        _check_error_handling(html, dash, counter),
        _check_aria_labels(html, dash, counter),
        _check_keyboard_focus(html, dash, counter),
        _check_semantic_html(html, dash, counter),
        _check_alt_text(html, dash, counter),
        _check_form_labels(html, dash, counter),
        _check_responsive(html, dash, counter),
    ]

    issues = [issue for issue in checks if issue is not None]
    log.info(
        "UX evaluation '%s': %d/%d checks failed",
        dashboard_name,
        len(issues),
        len(checks),
    )
    return issues


def calculate_ux_score(issues: list[UXIssue]) -> float:
    """
    Score = (total_checks - critical*3 - major*2 - minor*1) / (total_checks*3) * 100
    Clamped to [0, 100].

    total_checks = _TOTAL_CHECKS (9)
    """
    total = _TOTAL_CHECKS

    critical = sum(1 for i in issues if i.severity == Severity.CRITICAL)
    major = sum(1 for i in issues if i.severity == Severity.MAJOR)
    minor = sum(1 for i in issues if i.severity == Severity.MINOR)

    penalty = critical * 3 + major * 2 + minor * 1
    numerator = max(0, total * 3 - penalty)
    raw = (numerator / (total * 3)) * 100.0
    return round(max(0.0, min(100.0, raw)), 1)


def get_all_ux_issues(
    customer_path: pathlib.Path,
    admin_path: pathlib.Path,
) -> dict[str, list[UXIssue]]:
    """
    Main entry point. Evaluates both dashboards.

    Args:
        customer_path: Absolute path to customer_dashboard.html
        admin_path:    Absolute path to admin_dashboard.html

    Returns:
        {"customer": List[UXIssue], "admin": List[UXIssue]}
    """
    customer_issues = evaluate_dashboard(customer_path, "customer")
    admin_issues = evaluate_dashboard(admin_path, "admin")

    log.info(
        "UX evaluation complete — customer: %d issues, admin: %d issues",
        len(customer_issues),
        len(admin_issues),
    )

    return {
        "customer": customer_issues,
        "admin": admin_issues,
    }
