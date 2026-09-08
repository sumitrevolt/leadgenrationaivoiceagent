"""
Dashboard Assessment Orchestrator — ties scanner, gap_analyzer, ux_evaluator,
prioritizer, report_generator, report_parser, and regression_detector together
into a single cohesive pipeline.

Usage:
    python app/platform/dashboard_assessment.py --mode full
    python app/platform/dashboard_assessment.py --mode diff
    python app/platform/dashboard_assessment.py --mode ci
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import json
import logging
import pathlib
import sys
import uuid
from typing import Dict, List, Optional

from .assessment_models import (
    AssessmentData,
    Evidence,
    Feature,
    FeatureCategory,
    FeatureStatus,
    Gap,
    MoSCoW,
    Severity,
    UXIssue,
)
from .gap_analyzer import competitive_feature_count, get_all_gaps
from .prioritizer import build_backlog, generate_roadmap
from .regression_detector import AssessmentComparator, load_baseline, save_baseline
from .report_generator import save_reports
from .report_parser import AssessmentReportParser
from .scanner import scan_all_dashboards

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# UX evaluator — optional module; graceful stub if not present
# ---------------------------------------------------------------------------


def _load_ux_evaluator():
    """
    Attempt to import the ux_evaluator module.
    Returns (get_all_ux_issues, calculate_ux_score) callables, or stubs
    that return safe empty defaults if the module does not exist yet.
    """
    try:
        from .ux_evaluator import calculate_ux_score, get_all_ux_issues  # type: ignore

        return get_all_ux_issues, calculate_ux_score
    except ImportError:
        log.debug("ux_evaluator not found — using stub (no UX issues will be detected)")

        def _stub_get_all_ux_issues(
            customer_path: pathlib.Path,
            admin_path: pathlib.Path,
        ) -> list[UXIssue]:
            """
            Lightweight heuristic UX evaluation when ux_evaluator module is absent.
            Reads both dashboard files and checks for common WCAG/UX patterns.
            """
            issues: list[UXIssue] = []
            import re

            checks = [
                # (id_prefix, dashboard_name, path)
                ("ux_cus", "customer", customer_path),
                ("ux_adm", "admin", admin_path),
            ]
            counter = 0
            for prefix, dash, fpath in checks:
                if not fpath.exists():
                    continue
                html = fpath.read_text(encoding="utf-8", errors="ignore")

                # WCAG: missing ARIA labels
                has_aria = bool(re.search(r'aria-label|role="[a-z]+"', html, re.I))
                if not has_aria:
                    counter += 1
                    issues.append(
                        UXIssue(
                            id=f"{prefix}_{counter:03d}",
                            name="Missing ARIA labels",
                            dashboard=dash,
                            dimension="accessibility",
                            severity=Severity.CRITICAL,
                            wcag_violation=True,
                            wcag_criterion="4.1.2 Name, Role, Value",
                            user_impact="Screen readers cannot identify interactive elements",
                            evidence=Evidence(),
                            remediation="Add aria-label or aria-labelledby to all interactive elements",
                        )
                    )

                # WCAG: focus indicators suppressed
                outline_none = bool(re.search(r"outline\s*:\s*(?:0|none)", html, re.I))
                has_focus = bool(re.search(r":focus\b", html, re.I))
                if outline_none and not has_focus:
                    counter += 1
                    issues.append(
                        UXIssue(
                            id=f"{prefix}_{counter:03d}",
                            name="Keyboard focus indicators suppressed",
                            dashboard=dash,
                            dimension="accessibility",
                            severity=Severity.CRITICAL,
                            wcag_violation=True,
                            wcag_criterion="2.4.7 Focus Visible",
                            user_impact="Keyboard-only users cannot navigate the dashboard",
                            evidence=Evidence(),
                            remediation="Remove outline:none; add visible :focus styles",
                        )
                    )

                # Major: no empty-state handling
                has_empty = bool(re.search(r"empty[- _]state|no.data|nothing.here", html, re.I))
                if not has_empty:
                    counter += 1
                    issues.append(
                        UXIssue(
                            id=f"{prefix}_{counter:03d}",
                            name="Missing empty-state illustrations",
                            dashboard=dash,
                            dimension="feedback",
                            severity=Severity.MAJOR,
                            wcag_violation=False,
                            user_impact="Users see blank sections with no guidance",
                            evidence=Evidence(),
                            remediation="Add friendly empty-state messages for each data section",
                        )
                    )

                # Minor: no keyboard shortcuts
                has_kbd = bool(re.search(r"keydown|hotkey|shortcut|keybind", html, re.I))
                if not has_kbd:
                    counter += 1
                    issues.append(
                        UXIssue(
                            id=f"{prefix}_{counter:03d}",
                            name="No keyboard shortcuts",
                            dashboard=dash,
                            dimension="efficiency",
                            severity=Severity.MINOR,
                            wcag_violation=False,
                            user_impact="Power users cannot navigate efficiently",
                            evidence=Evidence(),
                            remediation="Add keyboard shortcut panel (e.g. ? key for help overlay)",
                        )
                    )

            return issues

        def _stub_calculate_ux_score(issues: list[UXIssue]) -> float:
            """
            UX quality = 100 − (critical×10 + major×4 + minor×1), clamped to [0, 100].
            """
            penalty = 0.0
            for issue in issues:
                if issue.severity == Severity.CRITICAL:
                    penalty += 10
                elif issue.severity == Severity.MAJOR:
                    penalty += 4
                else:
                    penalty += 1
            return max(0.0, min(100.0, 100.0 - penalty))

        return _stub_get_all_ux_issues, _stub_calculate_ux_score


# ---------------------------------------------------------------------------
# Score helpers
# ---------------------------------------------------------------------------


def _build_features_from_inventory(inventory: dict, dashboard: str) -> list[Feature]:
    """Convert scanner inventory dict into Feature model objects."""
    features: list[Feature] = []
    for raw in inventory.get("features", []):
        try:
            cat = FeatureCategory(raw.get("category", "action"))
        except ValueError:
            cat = FeatureCategory.ACTION
        try:
            status = FeatureStatus(raw.get("status", "broken"))
        except ValueError:
            status = FeatureStatus.BROKEN

        ev_raw = raw.get("evidence", {})
        evidence = Evidence(
            line_numbers=ev_raw.get("line_numbers", []),
            code_snippets=ev_raw.get("code_snippets", []),
        )
        features.append(
            Feature(
                id=raw.get("id", f"feat_{dashboard[:3]}_{len(features):03d}"),
                name=raw.get("feature_name", raw.get("name", "Unknown")),
                dashboard=dashboard,
                category=cat,
                status=status,
                description=raw.get("description", ""),
                ui_elements=raw.get("ui_elements", []),
                api_endpoints=raw.get("api_endpoints", []),
                evidence=evidence,
                requirement_mapping=raw.get("requirement_mapping", []),
            )
        )
    return features


def _build_backend_dependencies(gaps: list[Gap]) -> list[dict]:
    """Extract proposed API endpoints and backend dependencies from gap list."""
    deps = []
    for gap in gaps:
        if gap.backend_dependency:
            dep: dict = {"type": "backend_logic", "component": gap.name, "effort": gap.effort.value}
            deps.append(dep)
        if gap.proposed_endpoint:
            deps.append(
                {
                    "type": "new_endpoint",
                    "method": "GET",
                    "path": gap.proposed_endpoint,
                    "description": gap.description or gap.name,
                    "effort": gap.effort.value,
                }
            )
    return deps


def _assessment_to_dict(assessment: AssessmentData) -> dict:
    """
    Serialise AssessmentData to a JSON-compatible dict for baseline storage
    and regression comparisons.

    Includes scores, feature list, gaps, issues, and backlog counts.
    """

    def _ser(obj):
        if isinstance(obj, dict):
            return {k: _ser(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_ser(v) for v in obj]
        if hasattr(obj, "value"):  # Enum
            return obj.value
        if hasattr(obj, "__dataclass_fields__"):
            return _ser(dataclasses.asdict(obj))
        return obj

    features_list = []
    for f in assessment.features:
        features_list.append(
            {
                "id": f.id,
                "name": f.name,
                "dashboard": f.dashboard,
                "category": f.category.value,
                "status": f.status.value,
                "description": f.description,
                "ui_elements": f.ui_elements,
                "api_endpoints": f.api_endpoints,
            }
        )

    gaps_list = []
    for g in assessment.gaps:
        gaps_list.append(
            {
                "id": g.id,
                "name": g.name,
                "dashboard": g.dashboard,
                "impact": g.impact.value,
                "effort": g.effort.value,
                "moscow": g.moscow.value,
                "prevalence": g.prevalence,
                "category": g.category,
                "backend_dependency": g.backend_dependency,
            }
        )

    issues_list = []
    for i in assessment.issues:
        issues_list.append(
            {
                "id": i.id,
                "name": i.name,
                "dashboard": i.dashboard,
                "dimension": i.dimension,
                "severity": i.severity.value,
                "wcag_violation": i.wcag_violation,
                "wcag_criterion": i.wcag_criterion,
            }
        )

    backlog_list = []
    for b in assessment.backlog:
        backlog_list.append(
            {
                "item": b.item,
                "dashboard": b.dashboard,
                "category": b.category,
                "moscow": b.moscow.value,
                "impact_score": b.impact_score,
                "effort_score": b.effort_score,
                "priority_rank": b.priority_rank,
                "estimated_days": b.estimated_days,
            }
        )

    # Augment scores with CI-relevant counters so regression_detector can use them
    scores = dict(assessment.scores)
    scores["must_have_count"] = float(
        sum(1 for b in assessment.backlog if b.moscow == MoSCoW.MUST_HAVE)
    )
    scores["wcag_critical_count"] = float(
        sum(1 for i in assessment.issues if i.wcag_violation and i.severity == Severity.CRITICAL)
    )

    return {
        "assessment_id": assessment.assessment_id,
        "generated_at": assessment.generated_at,
        "scores": scores,
        "features": features_list,
        "gaps": gaps_list,
        "issues": issues_list,
        "backlog": backlog_list,
    }


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


class DashboardAssessment:
    """
    Orchestrates the full dashboard assessment pipeline:
      scan → gap analysis → UX evaluation → prioritization → scoring → reports
    """

    def __init__(
        self,
        customer_dashboard: str = "frontend/customer_dashboard.html",
        admin_dashboard: str = "frontend/admin_dashboard.html",
    ) -> None:
        self.customer_path = pathlib.Path(customer_dashboard)
        self.admin_path = pathlib.Path(admin_dashboard)
        # Resolve relative to repo root if path doesn't exist as-is
        _root = pathlib.Path(__file__).resolve().parent.parent.parent
        if not self.customer_path.exists():
            self.customer_path = _root / customer_dashboard
        if not self.admin_path.exists():
            self.admin_path = _root / admin_dashboard

        self.data_dir = _root / "data"
        self.docs_dir = _root / "docs"

        # Lazy-load UX evaluator (graceful stub if module absent)
        self._get_all_ux_issues, self._calculate_ux_score = _load_ux_evaluator()

    # ------------------------------------------------------------------
    # Public pipeline methods
    # ------------------------------------------------------------------

    def run_assessment(self) -> AssessmentData:
        """
        Run the full assessment pipeline and return an AssessmentData object.

        Steps:
          1. scan_all_dashboards() — build feature inventories
          2. get_all_gaps()        — competitive gap analysis
          3. get_all_ux_issues()   — UX heuristics
          4. build_backlog()       — MoSCoW prioritization
          5. Calculate scores
          6. generate_roadmap()    — sprint roadmap
          7. Assemble AssessmentData
        """
        assessment_id = (
            f"assess_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        )
        generated_at = datetime.datetime.now().isoformat()

        log.info("Assessment %s: scanning dashboards ...", assessment_id)

        # Step 1: Scan
        inventories = scan_all_dashboards()
        customer_inventory = inventories.get("Customer", {})
        admin_inventory = inventories.get("Admin", {})

        # Step 2: Gap analysis
        log.info("Assessment %s: running gap analysis ...", assessment_id)
        gaps_by_dash = get_all_gaps(customer_inventory, admin_inventory)
        all_gaps: list[Gap] = gaps_by_dash.get("customer", []) + gaps_by_dash.get("admin", [])

        # Step 3: UX issues
        log.info("Assessment %s: evaluating UX ...", assessment_id)
        ux_result = self._get_all_ux_issues(self.customer_path, self.admin_path)
        # get_all_ux_issues returns either List[UXIssue] (stub) or
        # Dict[str, List[UXIssue]] (real ux_evaluator) — normalise to flat list
        if isinstance(ux_result, dict):
            all_issues: list[UXIssue] = ux_result.get("customer", []) + ux_result.get("admin", [])
        else:
            all_issues = list(ux_result)

        # Step 4: Build backlog
        log.info("Assessment %s: building prioritized backlog ...", assessment_id)
        backlog = build_backlog(all_gaps, all_issues)

        # Step 5: Scores
        log.info("Assessment %s: calculating scores ...", assessment_id)
        scores = self._calculate_scores(
            customer_inventory=customer_inventory,
            admin_inventory=admin_inventory,
            all_gaps=all_gaps,
            all_issues=all_issues,
        )

        # Step 6: Roadmap (embedded in report generation)
        roadmap = generate_roadmap(backlog)
        log.info(
            "Assessment %s: roadmap — %d dev-days (%d weeks)",
            assessment_id,
            roadmap["total_days"],
            roadmap["estimated_weeks"],
        )

        # Step 7: Build Feature objects from inventories
        customer_features = _build_features_from_inventory(customer_inventory, "customer")
        admin_features = _build_features_from_inventory(admin_inventory, "admin")
        all_features = customer_features + admin_features

        # Backend dependencies from gaps
        backend_deps = _build_backend_dependencies(all_gaps)

        return AssessmentData(
            assessment_id=assessment_id,
            generated_at=generated_at,
            scores=scores,
            features=all_features,
            gaps=all_gaps,
            issues=all_issues,
            backlog=backlog,
            backend_dependencies=backend_deps,
        )

    def generate_reports(self, assessment: AssessmentData) -> dict:
        """
        Write Markdown and JSON reports to docs_dir.

        Returns dict mapping logical name → absolute Path (as strings).
        """
        log.info("Writing reports to %s ...", self.docs_dir)
        paths = save_reports(assessment, self.docs_dir)
        return {k: str(v) for k, v in paths.items()}

    def run_full(self) -> AssessmentData:
        """
        Run the complete pipeline:
          1. run_assessment()
          2. generate_reports()
          3. save_baseline()

        Returns the AssessmentData object.
        """
        assessment = self.run_assessment()
        report_paths = self.generate_reports(assessment)
        log.info("Reports written: %s", list(report_paths.values()))

        # Save baseline for future diff/CI runs
        baseline_path = save_baseline(_assessment_to_dict(assessment), self.data_dir)
        log.info("Baseline saved: %s", baseline_path)

        return assessment

    def run_diff(self, baseline_id: str = "latest") -> dict:
        """
        Load the specified baseline, run a fresh assessment, compare them,
        and return the regression report as a plain dict.

        Args:
            baseline_id: "latest" or a specific assessment_id.

        Returns:
            Dict with keys: regressions, improvements, score_deltas,
                            baseline_id, current_id, comparison_date.
        """
        # Load baseline
        baseline_data = load_baseline(self.data_dir, baseline_id)
        if baseline_data is None:
            log.warning("No baseline found for id=%s — running full assessment only", baseline_id)
            assessment = self.run_assessment()
            return {
                "regressions": [],
                "improvements": [],
                "score_deltas": {},
                "baseline_id": None,
                "current_id": assessment.assessment_id,
                "comparison_date": assessment.generated_at,
                "warning": "No baseline available; first run — use run_full() to save a baseline",
            }

        # Run current assessment
        assessment = self.run_assessment()
        current_data = _assessment_to_dict(assessment)

        # Write both to temp files so AssessmentComparator can load them
        tmp_dir = self.data_dir / "assessment_history" / "_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        baseline_tmp = tmp_dir / "baseline_compare.json"
        current_tmp = tmp_dir / "current_compare.json"

        baseline_tmp.write_text(
            json.dumps(baseline_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        current_tmp.write_text(
            json.dumps(current_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        comparator = AssessmentComparator()
        report = comparator.compare(str(baseline_tmp), str(current_tmp))

        # Clean up temp files
        for f in (baseline_tmp, current_tmp):
            f.unlink(missing_ok=True)

        return {
            "regressions": report.regressions,
            "improvements": report.improvements,
            "score_deltas": report.score_deltas,
            "baseline_id": report.baseline_id,
            "current_id": report.current_id,
            "comparison_date": report.comparison_date,
        }

    def run_ci(self, baseline_id: str = "latest") -> int:
        """
        Run a diff and return the appropriate CI exit code.

        Exit codes (from AssessmentComparator.get_exit_code):
          0 — no regressions
          1 — feature_completeness dropped > 5%
          2 — WCAG critical violations count increased
          3 — must_have items increased

        If no baseline exists, exits 0 (first run — not a failure).
        """
        baseline_data = load_baseline(self.data_dir, baseline_id)
        if baseline_data is None:
            log.info("CI: no baseline found — saving current assessment as baseline (exit 0)")
            self.run_full()
            return 0

        assessment = self.run_assessment()
        current_data = _assessment_to_dict(assessment)

        tmp_dir = self.data_dir / "assessment_history" / "_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        baseline_tmp = tmp_dir / "ci_baseline.json"
        current_tmp = tmp_dir / "ci_current.json"

        baseline_tmp.write_text(
            json.dumps(baseline_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        current_tmp.write_text(
            json.dumps(current_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        comparator = AssessmentComparator()
        regression_report = comparator.compare(str(baseline_tmp), str(current_tmp))
        exit_code = comparator.get_exit_code(regression_report)

        # Clean up
        for f in (baseline_tmp, current_tmp):
            f.unlink(missing_ok=True)

        log.info(
            "CI complete — exit_code=%d  regressions=%d  improvements=%d",
            exit_code,
            len(regression_report.regressions),
            len(regression_report.improvements),
        )
        return exit_code

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _calculate_scores(
        self,
        customer_inventory: dict,
        admin_inventory: dict,
        all_gaps: list[Gap],
        all_issues: list[UXIssue],
    ) -> dict[str, float]:
        """
        Compute all assessment scores.

        customer_completeness: complete / total_features × 100 (customer dash)
        admin_completeness:    complete / total_features × 100 (admin dash)
        competitive_parity:    (all competitive features − gaps) / all × 100
        ux_quality:            100 − weighted issue penalty
        """
        scores: dict[str, float] = {}

        # Completeness scores
        for dash, inv in (("customer", customer_inventory), ("admin", admin_inventory)):
            summary = inv.get("summary", {})
            total = summary.get("total_features", 0)
            complete = summary.get("complete", 0)
            key = f"{dash}_completeness"
            scores[key] = round((complete / total * 100) if total else 0.0, 1)

        # Competitive parity
        customer_gaps = [g for g in all_gaps if g.dashboard == "customer"]
        admin_gaps = [g for g in all_gaps if g.dashboard == "admin"]
        total_customer_competitive = competitive_feature_count("customer")
        total_admin_competitive = competitive_feature_count("admin")
        total_competitive = total_customer_competitive + total_admin_competitive
        total_gaps = len(customer_gaps) + len(admin_gaps)
        if total_competitive > 0:
            present = max(0, total_competitive - total_gaps)
            parity = round(present / total_competitive * 100, 1)
        else:
            parity = 100.0
        scores["competitive_parity"] = parity

        # UX quality
        ux_score = self._calculate_ux_score(all_issues)
        scores["ux_quality"] = round(ux_score, 1)

        return scores


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Dashboard Assessment Tool")
    parser.add_argument(
        "--mode",
        choices=["full", "diff", "ci"],
        default="full",
        help="full = run+save; diff = compare vs baseline; ci = exit code for CI",
    )
    parser.add_argument(
        "--baseline",
        default="latest",
        help="Baseline ID for diff/ci modes (default: latest)",
    )
    parser.add_argument(
        "--customer",
        default="frontend/customer_dashboard.html",
        help="Path to customer dashboard HTML",
    )
    parser.add_argument(
        "--admin",
        default="frontend/admin_dashboard.html",
        help="Path to admin dashboard HTML",
    )
    args = parser.parse_args()

    assessor = DashboardAssessment(
        customer_dashboard=args.customer,
        admin_dashboard=args.admin,
    )

    if args.mode == "full":
        result = assessor.run_full()
        print(f"Assessment complete: {result.assessment_id}")
        print(f"Customer completeness: {result.scores.get('customer_completeness', 0):.1f}%")
        print(f"Admin completeness:    {result.scores.get('admin_completeness', 0):.1f}%")
        print(f"Competitive parity:    {result.scores.get('competitive_parity', 0):.1f}%")
        print(f"UX quality:            {result.scores.get('ux_quality', 0):.1f}%")
        print(f"Gaps found:            {len(result.gaps)}")
        print(f"UX issues:             {len(result.issues)}")
        print(f"Backlog items:         {len(result.backlog)}")
        sys.exit(0)

    elif args.mode == "diff":
        report = assessor.run_diff(args.baseline)
        print(f"Baseline:     {report.get('baseline_id', 'N/A')}")
        print(f"Current:      {report.get('current_id', 'N/A')}")
        print(f"Regressions:  {len(report.get('regressions', []))}")
        print(f"Improvements: {len(report.get('improvements', []))}")
        if report.get("regressions"):
            print("\nRegressions:")
            for r in report["regressions"]:
                print(
                    f"  [{r.get('dashboard', '?')}] {r.get('feature_name', '?')} "
                    f"{r.get('regression_type', '?')}"
                )
        if report.get("improvements"):
            print("\nImprovements (gaps closed):")
            for imp in report["improvements"]:
                print(f"  [{imp.get('dashboard', '?')}] {imp.get('gap_name', '?')}")
        sys.exit(0)

    elif args.mode == "ci":
        exit_code = assessor.run_ci(args.baseline)
        _messages = {
            0: "CI PASS — no regressions",
            1: "CI FAIL — feature completeness dropped > 5%",
            2: "CI FAIL — WCAG critical violations increased",
            3: "CI FAIL — must_have backlog items increased",
        }
        print(_messages.get(exit_code, f"CI exit {exit_code}"))
        sys.exit(exit_code)
