"""
Gap Analyzer — compares scanner inventory against competitive benchmarks.
Identifies missing features, scores impact/effort, and returns Gap objects.

Data source: data/competitive_features.json
"""

from __future__ import annotations

import json
import logging
import pathlib
import re
from typing import Dict, List, Optional, Set

from .assessment_models import Effort, Gap, Impact, MoSCoW

log = logging.getLogger(__name__)

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
COMPETITIVE_FEATURES_PATH = ROOT / "data" / "competitive_features.json"

# ---------------------------------------------------------------------------
# Keyword synonym maps — competitive feature name → scanner feature_name tokens
# ---------------------------------------------------------------------------
_CUSTOMER_SYNONYMS: dict[str, list[str]] = {
    "real-time notifications center": ["notification", "notif", "bell", "inbox", "unread", "alert"],
    "global search bar": ["search", "filter", "query", "khojo"],
    "date range picker": ["date", "daterange", "datepicker", "flatpickr", "daterangepicker"],
    "export to csv/pdf": ["export", "download", "csv", "pdf", "xlsx"],
    "empty state illustrations": ["empty", "no data", "nothing", "illustration"],
    "skeleton screen loading states": ["skeleton", "spinner", "loading", "aria-busy"],
    "saved views / custom dashboard layouts": ["saved", "view", "layout", "custom"],
    "bulk actions on table rows": ["bulk", "select-all", "selectall", "checkbox"],
    "dark mode toggle": ["dark", "theme", "mode", "prefers-color-scheme"],
    "keyboard shortcuts panel": ["keyboard", "shortcut", "hotkey", "keybind"],
    "onboarding checklist / getting started wizard": [
        "onboard",
        "checklist",
        "wizard",
        "getting started",
    ],
    "inline lead status editing": ["inline", "lead.*edit", "edit.*lead", "patch.*lead"],
    "collaborative comments on leads": ["comment", "note", "collab"],
    "ai-powered anomaly detection": ["anomaly", "ai.*detect", "detect.*pattern"],
    "custom dashboard widgets (drag-and-drop)": ["drag", "drop", "sortable", "widget"],
}

_ADMIN_SYNONYMS: dict[str, list[str]] = {
    "client search with instant filtering": ["search", "filter", "query", "client.*search"],
    "bulk client actions (multi-select)": ["bulk", "multi.*select", "select.*all", "checkbox"],
    "advanced multi-condition filters": [
        "filter",
        "condition",
        "advanced.*filter",
        "multi.*filter",
    ],
    "client activity timeline / audit log": ["timeline", "audit", "activity", "log", "history"],
    "revenue analytics (mrr trend, churn rate, ltv)": ["mrr", "churn", "ltv", "revenue", "arr"],
    "alert rules / threshold configuration": [
        "alert.*rule",
        "threshold",
        "trigger",
        "rule.*engine",
    ],
    "export clients to csv with active filters": ["export", "csv", "download"],
    "role-based access control (rbac) ui": ["rbac", "role", "permission", "access.*control"],
    "api usage analytics / rate limit view": ["api.*usage", "rate.*limit", "endpoint.*stat"],
    "webhook delivery dashboard": ["webhook", "delivery", "event.*log"],
    "system health monitoring panel": ["health", "monitor", "latency", "uptime", "service.*status"],
    "impersonation mode (login as customer)": ["impersonat", "login.*as", "sudo", "act.*as"],
    "multi-tenancy operator account switcher": ["tenant", "account.*switch", "operator"],
    "scheduled reports via email": ["scheduled.*report", "report.*email", "email.*report"],
}


def _load_competitive_features() -> dict:
    """Load competitive_features.json; raise RuntimeError if missing."""
    try:
        with open(COMPETITIVE_FEATURES_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"competitive_features.json not found at {COMPETITIVE_FEATURES_PATH}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"competitive_features.json is malformed: {exc}") from exc


def _normalise(text: str) -> str:
    """Lowercase + strip punctuation for fuzzy matching."""
    return re.sub(r"[^a-z0-9 ]", " ", text.lower())


def _scanned_feature_names(inventory: dict) -> list[str]:
    """Return normalised feature_name strings from scanner output dict."""
    features = inventory.get("features", [])
    names: list[str] = []
    for f in features:
        raw = f.get("feature_name", "")
        if raw:
            names.append(_normalise(raw))
        # Also include description tokens
        desc = f.get("description", "")
        if desc:
            names.append(_normalise(desc))
    return names


def _feature_detected(
    competitive_name: str,
    synonym_map: dict[str, list[str]],
    scanned_texts: list[str],
) -> bool:
    """
    Return True if any scanned feature text matches the competitive feature
    via synonym map or direct keyword overlap.
    """
    key = _normalise(competitive_name)

    # 1. Synonym-map lookup (precise)
    for map_key, keywords in synonym_map.items():
        if map_key in key or key in map_key:
            for kw in keywords:
                pattern = kw.replace(".*", r".*")
                for txt in scanned_texts:
                    if re.search(pattern, txt):
                        return True

    # 2. Direct keyword overlap: split competitive name into significant words (≥4 chars)
    words = [
        w
        for w in key.split()
        if len(w) >= 4
        and w
        not in {
            "with",
            "from",
            "this",
            "that",
            "have",
            "been",
            "will",
            "your",
            "then",
            "than",
            "mode",
            "view",
            "type",
            "show",
        }
    ]
    if words:
        for txt in scanned_texts:
            matched = sum(1 for w in words if w in txt)
            # Require at least 1 strong keyword match (≥5 chars) or 2 shorter ones
            strong = sum(1 for w in words if len(w) >= 5 and w in txt)
            if strong >= 1 or matched >= 2:
                return True

    return False


def score_gap_impact(gap: Gap) -> Impact:
    """Return Impact enum based on prevalence score from competitive data."""
    if gap.prevalence >= 6:
        return Impact.HIGH
    if gap.prevalence >= 3:
        return Impact.MEDIUM
    return Impact.LOW


def estimate_effort(gap: Gap, backend_dependency: bool) -> Effort:
    """
    Return Effort enum.
    - backend_dependency=True  → HIGH  (API + DB work needed)
    - CSS/frontend complex checks → MEDIUM
    - Pure frontend / CSS only    → LOW
    """
    if backend_dependency:
        return Effort.HIGH

    # Heuristic: features with proposed endpoints that aren't trivial = MEDIUM
    css_only_keywords = {
        "dark mode",
        "skeleton",
        "empty state",
        "illustration",
        "keyboard shortcut",
        "date range",
        "export",
        "bulk action",
    }
    name_lower = gap.name.lower()
    for kw in css_only_keywords:
        if kw in name_lower:
            return Effort.LOW

    return Effort.MEDIUM


def calculate_parity_score(gaps: list[Gap], total_competitive: int) -> float:
    """
    Parity score = (competitive features present) / total_competitive × 100.
    Presence = total_competitive - gaps detected.
    Clamped to [0, 100].
    """
    if total_competitive <= 0:
        return 100.0
    missing = len(gaps)
    present = max(0, total_competitive - missing)
    score = (present / total_competitive) * 100.0
    return round(max(0.0, min(100.0, score)), 1)


def identify_gaps(inventory: dict, dashboard_name: str) -> list[Gap]:
    """
    Compare scanner inventory against competitive benchmarks for a single
    dashboard.  Returns List[Gap] for every missing competitive feature.

    Args:
        inventory:       Dict returned by scanner.scan_dashboard()
        dashboard_name:  "customer" or "admin" (case-insensitive)
    """
    cf = _load_competitive_features()
    name_lower = dashboard_name.lower()

    # Select the right benchmark section
    if "admin" in name_lower:
        bench_key = "admin_dashboard"
        synonym_map = _ADMIN_SYNONYMS
    else:
        bench_key = "customer_dashboard"
        synonym_map = _CUSTOMER_SYNONYMS

    bench_section = cf.get(bench_key, {})
    if not bench_section:
        log.warning("No benchmark section '%s' in competitive_features.json", bench_key)
        return []

    scanned_texts = _scanned_feature_names(inventory)

    gaps: list[Gap] = []
    gap_counter = 0

    tiers_ordered = ["table_stakes", "standard", "advanced"]
    for tier in tiers_ordered:
        for feat in bench_section.get(tier, []):
            comp_name: str = feat.get("name", "")
            if not comp_name:
                continue

            detected = _feature_detected(comp_name, synonym_map, scanned_texts)
            if detected:
                continue

            # Build Gap
            gap_counter += 1
            gap_id = f"gap_{gap_counter:03d}"

            prevalence: int = feat.get("prevalence", 1)
            backend_dep: bool = feat.get("backend_dependency", False)
            proposed_ep: str | None = feat.get("proposed_endpoint")
            competitors: list[str] = feat.get("competitors", [])
            category: str = feat.get("category", "")
            description: str = feat.get("description", "")

            gap = Gap(
                id=gap_id,
                name=comp_name,
                dashboard=name_lower,
                competitive_reference=competitors,
                prevalence=prevalence,
                impact=Impact.MEDIUM,  # will be updated below
                effort=Effort.MEDIUM,  # will be updated below
                moscow=MoSCoW.SHOULD_HAVE,  # prioritizer sets final value
                category=category,
                description=description,
                backend_dependency=backend_dep,
                proposed_endpoint=proposed_ep,
            )

            # Score immediately
            gap.impact = score_gap_impact(gap)
            gap.effort = estimate_effort(gap, backend_dep)

            gaps.append(gap)

    return gaps


def get_all_gaps(
    customer_inventory: dict,
    admin_inventory: dict,
) -> dict[str, list[Gap]]:
    """
    Main entry point.  Runs gap analysis for both dashboards.

    Args:
        customer_inventory: scanner output dict for customer_dashboard.html
        admin_inventory:    scanner output dict for admin_dashboard.html

    Returns:
        {"customer": List[Gap], "admin": List[Gap]}
    """
    customer_gaps = identify_gaps(customer_inventory, "customer")
    admin_gaps = identify_gaps(admin_inventory, "admin")

    log.info(
        "Gap analysis complete — customer: %d gaps, admin: %d gaps",
        len(customer_gaps),
        len(admin_gaps),
    )

    return {
        "customer": customer_gaps,
        "admin": admin_gaps,
    }


# ---------------------------------------------------------------------------
# Convenience: competitive feature counts (for parity score denominator)
# ---------------------------------------------------------------------------


def competitive_feature_count(dashboard_name: str) -> int:
    """Return total number of competitive features benchmarked for a dashboard."""
    cf = _load_competitive_features()
    key = "admin_dashboard" if "admin" in dashboard_name.lower() else "customer_dashboard"
    section = cf.get(key, {})
    total = 0
    for tier_feats in section.values():
        total += len(tier_feats)
    return total
