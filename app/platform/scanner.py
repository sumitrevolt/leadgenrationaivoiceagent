"""
Dashboard Scanner — extracts feature inventory from HTML/JS files.
Static heuristic analysis: detects PRESENCE of patterns, not runtime correctness.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import pathlib
import re
from typing import Dict, List, Tuple

from .assessment_models import Evidence, Feature, FeatureCategory, FeatureStatus

log = logging.getLogger(__name__)

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
FRONTEND = ROOT / "frontend"

# --- Heuristic patterns ---

KPI_PATTERNS = [
    r'class="[^"]*\b(?:kpi|stat|metric|counter|number|score|count)\b',
    r'class="[^"]*\bkpi\b',
    r'id="[^"]*(?:total|count|kpi|stat)',
]

CHART_PATTERNS = [
    r"new\s+Chart\s*\(",
    r"<canvas\b",
    r"Chart\.register",
    r"chartjs|chart\.js",
]

TABLE_PATTERNS = [
    r"<table\b",
    r"<tbody\b",
]

FORM_PATTERNS = [
    r"<form\b",
    r"<input\b",
    r"<select\b",
    r"<textarea\b",
]

REALTIME_PATTERNS = [
    r"new\s+WebSocket\s*\(",
    r"EventSource\s*\(",
    r"setInterval\s*\(",
    r"socket\.io",
    r"pusher",
]

NAV_PATTERNS = [
    r"<nav\b",
    r'class="[^"]*\bnavlink\b',
    r'class="[^"]*\bsidebar\b',
    r'class="[^"]*\btopbar\b',
]

LOADING_PATTERNS = [
    r"spinner|skeleton|loading|aria-busy",
    r'class="[^"]*\bspin\b',
    r"display.*none.*loading",
]

MODAL_PATTERNS = [
    r"<dialog\b",
    r'class="[^"]*\bmodal\b',
    r'class="[^"]*\boverlay\b',
]

EXPORT_PATTERNS = [
    r"export|download|csv|pdf|xlsx",
    r"application/.*(?:csv|pdf|excel)",
    r"\.csv\b",
]

SEARCH_PATTERNS = [
    r"<input[^>]*(?:search|query|filter)",
    r'type="search"',
    r'placeholder="[^"]*(?:search|cari|khojo)',
]

NOTIFICATION_PATTERNS = [
    r"notification|bell-icon|unread|inbox",
    r'class="[^"]*\bnotif\b',
    r"badge.*count",
]

DARK_MODE_PATTERNS = [
    r"dark[-_]mode|prefers-color-scheme|theme-toggle",
    r"darkMode|dark_mode",
]

DATE_RANGE_PATTERNS = [
    r"daterange|datepicker|date-range|date_range",
    r"startDate.*endDate|from_date.*to_date",
    r"flatpickr|daterangepicker",
]

BULK_ACTION_PATTERNS = [
    r"bulk|select-all|selectAll|check.*all",
    r'class="[^"]*\bcheckbox\b.*table',
]

KEYBOARD_SHORTCUT_PATTERNS = [
    r"keydown|keyup|hotkey|keyboard.*shortcut",
    r"event\.key.*(?:Escape|Enter|ArrowUp|ArrowDown)",
    r"shortcut|keybind",
]

ARIA_PATTERNS = [
    r'aria-label|aria-[a-z]+="',
    r'role="[a-z]+"',
    r'alt="[^"]+"',
]

WCAG_FOCUS_PATTERNS = [
    r":focus\b",
    r"outline.*none.*(?!.*:focus)",  # outline:none without :focus (bad)
    r"tabindex",
]


def _count(pattern: str, html: str) -> int:
    return len(re.findall(pattern, html, re.I))


def _match(patterns: list, html: str) -> bool:
    return any(re.search(p, html, re.I) for p in patterns)


def _extract_api_endpoints(html: str) -> list[dict]:
    """Extract /api/* endpoints from fetch/axios calls."""
    endpoints = []
    seen = set()

    # fetch('/api/...')
    for m in re.finditer(r"""(?:fetch|axios\.\w+)\s*\(\s*['"`](/api/[^'"`?\s]+)""", html, re.I):
        path = m.group(1)
        if path not in seen:
            seen.add(path)
            endpoints.append({"path": path, "method": "GET", "usage_context": "fetch"})

    # '/api/...' strings
    for m in re.finditer(r"""['"`](/api/[A-Za-z0-9_\-/]+)['"`]""", html):
        path = m.group(1)
        if path not in seen:
            seen.add(path)
            endpoints.append({"path": path, "method": "?", "usage_context": "string_literal"})

    # method hints
    for ep in endpoints:
        ctx_match = re.search(
            rf"""['"`]{re.escape(ep["path"])}['"`][^{{]*method\s*:\s*['"`](\w+)['"`]""", html, re.I
        )
        if ctx_match:
            ep["method"] = ctx_match.group(1).upper()

    return sorted(endpoints, key=lambda x: x["path"])


def _extract_evidence(pattern: str, html: str, max_snippets: int = 3) -> Evidence:
    """Extract line numbers and code snippets for a pattern."""
    lines = html.split("\n")
    found_lines = []
    snippets = []

    for i, line in enumerate(lines, 1):
        if re.search(pattern, line, re.I):
            found_lines.append(i)
            if len(snippets) < max_snippets:
                snippets.append(line.strip()[:120])

    return Evidence(line_numbers=found_lines[:5], code_snippets=snippets)


def scan_dashboard(filepath: pathlib.Path, dashboard_name: str) -> dict:
    """
    Scan a dashboard HTML file and return feature inventory.
    Returns dict matching scanner output schema.
    """
    try:
        html = filepath.read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        log.error(f"Dashboard not found: {filepath}")
        return {
            "dashboard_name": dashboard_name,
            "error": "file_not_found",
            "features": [],
            "api_endpoints_discovered": [],
        }
    except PermissionError:
        log.error(f"Permission denied: {filepath}")
        return {
            "dashboard_name": dashboard_name,
            "error": "permission_denied",
            "features": [],
            "api_endpoints_discovered": [],
        }

    file_stat = filepath.stat()

    # ---- Feature extraction ----
    raw_features = []

    # 1. KPI Cards
    kpi_count = sum(_count(p, html) for p in KPI_PATTERNS)
    raw_features.append(
        {
            "feature_name": "KPI Dashboard Cards",
            "category": FeatureCategory.ANALYTICS.value,
            "status": FeatureStatus.COMPLETE.value if kpi_count > 0 else FeatureStatus.BROKEN.value,
            "description": f"{kpi_count} KPI/metric cards detected",
            "ui_elements": ["kpi-card", "metric-card"],
            "api_endpoints": [],
            "evidence": _extract_evidence(KPI_PATTERNS[0], html).__dict__,
        }
    )

    # 2. Charts / Data Visualization
    chart_count = sum(_count(p, html) for p in CHART_PATTERNS[:2])
    raw_features.append(
        {
            "feature_name": "Data Visualizations (Charts)",
            "category": FeatureCategory.VISUALIZATION.value,
            "status": (
                FeatureStatus.COMPLETE.value if chart_count > 0 else FeatureStatus.BROKEN.value
            ),
            "description": f"{chart_count} chart instances detected (Chart.js/canvas)",
            "ui_elements": ["canvas", "chart"],
            "api_endpoints": [],
            "evidence": _extract_evidence(CHART_PATTERNS[0], html).__dict__,
        }
    )

    # 3. Data Tables
    table_count = _count(TABLE_PATTERNS[0], html)
    raw_features.append(
        {
            "feature_name": "Data Tables",
            "category": FeatureCategory.DATA_TABLE.value,
            "status": (
                FeatureStatus.COMPLETE.value if table_count > 0 else FeatureStatus.BROKEN.value
            ),
            "description": f"{table_count} tables detected",
            "ui_elements": ["table", "tbody", "thead"],
            "api_endpoints": [],
            "evidence": _extract_evidence(TABLE_PATTERNS[0], html).__dict__,
        }
    )

    # 4. Forms & Inputs
    form_count = sum(_count(p, html) for p in FORM_PATTERNS)
    raw_features.append(
        {
            "feature_name": "Forms & Inputs",
            "category": FeatureCategory.ACTION.value,
            "status": (
                FeatureStatus.COMPLETE.value if form_count > 0 else FeatureStatus.BROKEN.value
            ),
            "description": f"{form_count} form elements detected",
            "ui_elements": ["form", "input", "select", "textarea"],
            "api_endpoints": [],
            "evidence": _extract_evidence(FORM_PATTERNS[0], html).__dict__,
        }
    )

    # 5. Real-time / Live Data
    has_realtime = _match(REALTIME_PATTERNS, html)
    raw_features.append(
        {
            "feature_name": "Real-time Updates",
            "category": FeatureCategory.REAL_TIME.value,
            "status": FeatureStatus.COMPLETE.value if has_realtime else FeatureStatus.BROKEN.value,
            "description": (
                "WebSocket/SSE/polling for live data" if has_realtime else "No real-time detected"
            ),
            "ui_elements": [],
            "api_endpoints": [],
            "evidence": (
                _extract_evidence(REALTIME_PATTERNS[0], html).__dict__
                if has_realtime
                else Evidence().__dict__
            ),
        }
    )

    # 6. Navigation / Sidebar
    has_nav = _match(NAV_PATTERNS, html)
    raw_features.append(
        {
            "feature_name": "Navigation / Sidebar",
            "category": FeatureCategory.NAVIGATION.value,
            "status": FeatureStatus.COMPLETE.value if has_nav else FeatureStatus.PARTIAL.value,
            "description": "Sidebar navigation present" if has_nav else "Navigation not detected",
            "ui_elements": ["nav", "sidebar", "navlink"],
            "api_endpoints": [],
            "evidence": _extract_evidence(NAV_PATTERNS[0], html).__dict__,
        }
    )

    # 7. Loading States
    has_loading = _match(LOADING_PATTERNS, html)
    raw_features.append(
        {
            "feature_name": "Loading States",
            "category": FeatureCategory.ACTION.value,
            "status": FeatureStatus.COMPLETE.value if has_loading else FeatureStatus.BROKEN.value,
            "description": (
                "Spinner/skeleton/loading indicators"
                if has_loading
                else "No loading states detected"
            ),
            "ui_elements": ["spinner", "skeleton", "loading"],
            "api_endpoints": [],
            "evidence": _extract_evidence(LOADING_PATTERNS[0], html).__dict__,
        }
    )

    # 8. Export / Download
    has_export = _match(EXPORT_PATTERNS, html)
    raw_features.append(
        {
            "feature_name": "Export / Download (CSV, PDF)",
            "category": FeatureCategory.ACTION.value,
            "status": FeatureStatus.COMPLETE.value if has_export else FeatureStatus.BROKEN.value,
            "description": "CSV/PDF export capability" if has_export else "No export detected",
            "ui_elements": ["export-btn", "download"],
            "api_endpoints": [],
            "evidence": _extract_evidence(EXPORT_PATTERNS[0], html).__dict__,
        }
    )

    # 9. Search
    has_search = _match(SEARCH_PATTERNS, html)
    raw_features.append(
        {
            "feature_name": "Search / Filter",
            "category": FeatureCategory.NAVIGATION.value,
            "status": FeatureStatus.COMPLETE.value if has_search else FeatureStatus.BROKEN.value,
            "description": "Search/filter input present" if has_search else "No search detected",
            "ui_elements": ["input[search]", "filter-bar"],
            "api_endpoints": [],
            "evidence": _extract_evidence(SEARCH_PATTERNS[0], html).__dict__,
        }
    )

    # 10. Notifications
    has_notif = _match(NOTIFICATION_PATTERNS, html)
    raw_features.append(
        {
            "feature_name": "Notifications / Alerts",
            "category": FeatureCategory.REAL_TIME.value,
            "status": FeatureStatus.COMPLETE.value if has_notif else FeatureStatus.BROKEN.value,
            "description": "Notification center/bell" if has_notif else "No notification center",
            "ui_elements": ["notification-bell", "badge"],
            "api_endpoints": [],
            "evidence": _extract_evidence(NOTIFICATION_PATTERNS[0], html).__dict__,
        }
    )

    # 11. Dark Mode
    has_dark = _match(DARK_MODE_PATTERNS, html)
    raw_features.append(
        {
            "feature_name": "Dark Mode Toggle",
            "category": FeatureCategory.ACTION.value,
            "status": FeatureStatus.COMPLETE.value if has_dark else FeatureStatus.BROKEN.value,
            "description": "Dark/light mode support" if has_dark else "No dark mode",
            "ui_elements": ["theme-toggle"],
            "api_endpoints": [],
            "evidence": Evidence().__dict__,
        }
    )

    # 12. Date Range Picker
    has_daterange = _match(DATE_RANGE_PATTERNS, html)
    raw_features.append(
        {
            "feature_name": "Date Range Picker",
            "category": FeatureCategory.ACTION.value,
            "status": FeatureStatus.COMPLETE.value if has_daterange else FeatureStatus.BROKEN.value,
            "description": "Dynamic date range filter" if has_daterange else "No date range picker",
            "ui_elements": ["date-picker", "date-range"],
            "api_endpoints": [],
            "evidence": Evidence().__dict__,
        }
    )

    # 13. Modals / Dialogs
    has_modal = _match(MODAL_PATTERNS, html)
    raw_features.append(
        {
            "feature_name": "Modals / Dialogs",
            "category": FeatureCategory.ACTION.value,
            "status": FeatureStatus.COMPLETE.value if has_modal else FeatureStatus.BROKEN.value,
            "description": "Modal dialogs present" if has_modal else "No modals detected",
            "ui_elements": ["modal", "dialog", "overlay"],
            "api_endpoints": [],
            "evidence": _extract_evidence(MODAL_PATTERNS[0], html).__dict__,
        }
    )

    # 14. Keyboard Shortcuts
    has_kbd = _match(KEYBOARD_SHORTCUT_PATTERNS, html)
    raw_features.append(
        {
            "feature_name": "Keyboard Shortcuts",
            "category": FeatureCategory.ACTION.value,
            "status": FeatureStatus.COMPLETE.value if has_kbd else FeatureStatus.BROKEN.value,
            "description": "Keyboard shortcut support" if has_kbd else "No keyboard shortcuts",
            "ui_elements": [],
            "api_endpoints": [],
            "evidence": Evidence().__dict__,
        }
    )

    # 15. ARIA / Accessibility
    has_aria = _match(ARIA_PATTERNS, html)
    raw_features.append(
        {
            "feature_name": "ARIA / Screen Reader Support",
            "category": FeatureCategory.ACTION.value,
            "status": FeatureStatus.COMPLETE.value if has_aria else FeatureStatus.BROKEN.value,
            "description": (
                "ARIA labels and roles present" if has_aria else "No ARIA labels — WCAG violation"
            ),
            "ui_elements": [],
            "api_endpoints": [],
            "evidence": _extract_evidence(ARIA_PATTERNS[0], html).__dict__,
        }
    )

    # 16. Focus Indicators
    has_focus = _match([r":focus\b"], html) and not re.search(
        r"outline\s*:\s*0|outline\s*:\s*none", html
    )
    raw_features.append(
        {
            "feature_name": "Keyboard Focus Indicators",
            "category": FeatureCategory.ACTION.value,
            "status": (
                FeatureStatus.COMPLETE.value
                if has_focus
                else (
                    FeatureStatus.PARTIAL.value
                    if _match([r":focus\b"], html)
                    else FeatureStatus.BROKEN.value
                )
            ),
            "description": (
                ":focus styles present"
                if _match([r":focus\b"], html)
                else "No :focus styling — WCAG violation"
            ),
            "ui_elements": [],
            "api_endpoints": [],
            "evidence": _extract_evidence(r":focus\b", html).__dict__,
        }
    )

    # ---- API Endpoint extraction ----
    api_endpoints = _extract_api_endpoints(html)

    # Tag api_endpoints to relevant features
    billing_eps = [ep for ep in api_endpoints if "/billing" in ep["path"]]
    customer_eps = [ep for ep in api_endpoints if "/customer" in ep["path"]]

    # Add billing feature if billing endpoints found
    if billing_eps:
        raw_features.append(
            {
                "feature_name": "Billing / Subscription Management",
                "category": FeatureCategory.BILLING.value,
                "status": FeatureStatus.COMPLETE.value,
                "description": f"{len(billing_eps)} billing API endpoints wired",
                "ui_elements": ["billing-portal", "invoice", "subscription"],
                "api_endpoints": [ep["path"] for ep in billing_eps],
                "evidence": Evidence().__dict__,
            }
        )

    # Add feature IDs
    features = []
    for i, f in enumerate(raw_features):
        f["id"] = f"feat_{dashboard_name[:3].lower()}_{i + 1:03d}"
        f["dashboard"] = dashboard_name.lower()
        features.append(f)

    # ---- Summary ----
    complete = sum(1 for f in features if f["status"] == FeatureStatus.COMPLETE.value)
    partial = sum(1 for f in features if f["status"] == FeatureStatus.PARTIAL.value)
    broken = sum(1 for f in features if f["status"] == FeatureStatus.BROKEN.value)

    return {
        "dashboard_name": dashboard_name,
        "scan_timestamp": datetime.datetime.now().isoformat(),
        "file_metadata": {
            "path": str(filepath),
            "size_bytes": file_stat.st_size,
            "last_modified": datetime.datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
        },
        "features": features,
        "api_endpoints_discovered": api_endpoints,
        "summary": {
            "total_features": len(features),
            "complete": complete,
            "partial": partial,
            "broken": broken,
            "completeness_score": round(complete / len(features) * 100, 1) if features else 0,
        },
    }


def scan_all_dashboards() -> dict[str, dict]:
    """Scan all known dashboard files."""
    dashboards = {
        "Customer": FRONTEND / "customer_dashboard.html",
        "Admin": FRONTEND / "admin_dashboard.html",
    }
    return {name: scan_dashboard(path, name) for name, path in dashboards.items()}
