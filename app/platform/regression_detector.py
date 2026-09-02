"""
Regression Detector — compares two assessment JSON snapshots to surface
regressions (status downgrades), improvements (gaps closed), and score deltas.

Exit-code contract:
  0 — no regressions
  1 — feature_completeness dropped > 5 percentage points
  2 — WCAG critical violations count increased
  3 — must_have backlog items count increased
"""

from __future__ import annotations

import datetime
import json
import logging
import pathlib
import uuid
from typing import Dict, List, Optional

from .assessment_models import RegressionReport

log = logging.getLogger(__name__)

# Status severity order (higher index = worse)
_STATUS_RANK: dict[str, int] = {
    "complete": 2,
    "partial": 1,
    "broken": 0,
}

# Threshold: completeness drop (percentage points) that triggers exit code 1
_COMPLETENESS_DROP_THRESHOLD = 5.0


class AssessmentComparator:
    """
    Compare two assessment JSON snapshots and produce a RegressionReport.

    Expected JSON schema (both baseline and current):
    {
        "assessment_id": "...",
        "generated_at": "...",
        "scores": {"customer_completeness": 85.0, "admin_completeness": 70.0, ...},
        "features": [
            {"id": "feat_cus_001", "name": "KPI Dashboard Cards",
             "dashboard": "customer", "status": "complete", ...},
            ...
        ],
        "gaps": [
            {"id": "gap_001", "name": "Global search bar",
             "dashboard": "customer", "moscow": "must_have", ...},
            ...
        ],
        "issues": [
            {"id": "ux_001", "name": "ARIA missing",
             "wcag_violation": true, "severity": "critical", ...},
            ...
        ],
        "backlog": [...],
    }
    """

    def compare(self, baseline_path: str, current_path: str) -> RegressionReport:
        """
        Load two assessment JSONs, compare them, and return a RegressionReport.

        Args:
            baseline_path: Path to the baseline assessment JSON file.
            current_path:  Path to the current assessment JSON file.

        Returns:
            RegressionReport dataclass populated with regressions, improvements,
            and score_deltas.
        """
        baseline = self._load(baseline_path)
        current = self._load(current_path)

        baseline_id = baseline.get("assessment_id", "baseline")
        current_id = current.get("assessment_id", "current")

        regressions = self.detect_regressions(
            baseline.get("features", []),
            current.get("features", []),
        )
        improvements = self.detect_improvements(
            baseline.get("gaps", []),
            current.get("gaps", []),
        )
        score_deltas = self.calculate_score_deltas(
            baseline.get("scores", {}),
            current.get("scores", {}),
        )

        return RegressionReport(
            comparison_id=str(uuid.uuid4()),
            baseline_id=baseline_id,
            current_id=current_id,
            comparison_date=datetime.datetime.now().isoformat(),
            regressions=regressions,
            improvements=improvements,
            score_deltas=score_deltas,
        )

    def detect_regressions(
        self,
        baseline_features: list[dict],
        current_features: list[dict],
    ) -> list[dict]:
        """
        Match features by name (case-insensitive) across dashboards, find
        status regressions (complete→broken or complete→partial or
        partial→broken).

        Returns a list of regression dicts:
        {
            "feature_name": str,
            "dashboard": str,
            "baseline_status": str,
            "current_status": str,
            "regression_type": "complete->broken" | "complete->partial" | "partial->broken",
        }
        """
        # Build lookup: (name_lower, dashboard) -> status
        baseline_map: dict[tuple, str] = {}
        for feat in baseline_features:
            key = (feat.get("name", "").lower(), feat.get("dashboard", "").lower())
            if key[0]:
                baseline_map[key] = feat.get("status", "").lower()

        regressions: list[dict] = []
        for feat in current_features:
            name = feat.get("name", "")
            dashboard = feat.get("dashboard", "").lower()
            current_status = feat.get("status", "").lower()
            key = (name.lower(), dashboard)

            baseline_status = baseline_map.get(key)
            if baseline_status is None:
                # New feature — not a regression
                continue

            b_rank = _STATUS_RANK.get(baseline_status, 1)
            c_rank = _STATUS_RANK.get(current_status, 1)

            if c_rank < b_rank:
                regression_type = f"{baseline_status}->{current_status}"
                regressions.append(
                    {
                        "feature_name": name,
                        "dashboard": dashboard,
                        "baseline_status": baseline_status,
                        "current_status": current_status,
                        "regression_type": regression_type,
                    }
                )

        return regressions

    def detect_improvements(
        self,
        baseline_gaps: list[dict],
        current_gaps: list[dict],
    ) -> list[dict]:
        """
        Find gaps that existed in the baseline but are absent in the current
        assessment (i.e., closed/resolved gaps).

        Matching is by gap name (case-insensitive) scoped to dashboard.

        Returns a list of improvement dicts:
        {
            "gap_name": str,
            "dashboard": str,
            "baseline_moscow": str,
        }
        """
        current_set: set = {
            (g.get("name", "").lower(), g.get("dashboard", "").lower())
            for g in current_gaps
            if g.get("name")
        }

        improvements: list[dict] = []
        for gap in baseline_gaps:
            name = gap.get("name", "")
            dashboard = gap.get("dashboard", "").lower()
            key = (name.lower(), dashboard)
            if key[0] and key not in current_set:
                improvements.append(
                    {
                        "gap_name": name,
                        "dashboard": dashboard,
                        "baseline_moscow": gap.get("moscow", ""),
                    }
                )

        return improvements

    def calculate_score_deltas(
        self,
        baseline_scores: dict[str, float],
        current_scores: dict[str, float],
    ) -> dict[str, float]:
        """
        Compute (current - baseline) for every score key present in either dict.

        Missing keys in either dict are treated as 0.0.
        Returns dict mapping score_key → delta (float).
        """
        all_keys = set(baseline_scores) | set(current_scores)
        deltas: dict[str, float] = {}
        for key in sorted(all_keys):
            b_val = float(baseline_scores.get(key, 0.0))
            c_val = float(current_scores.get(key, 0.0))
            deltas[key] = round(c_val - b_val, 4)
        return deltas

    def get_exit_code(self, report: RegressionReport) -> int:
        """
        Determine the CI exit code from a RegressionReport.

        Priority (first match wins):
          3 — must_have backlog items increased vs baseline
          2 — WCAG critical violations count increased (more issues with
              wcag_violation=True and severity='critical')
          1 — feature_completeness dropped more than _COMPLETENESS_DROP_THRESHOLD %
          0 — no regressions

        The method examines score_deltas and regression lists; it does NOT
        reload JSON files, so callers should pass the full RegressionReport as
        produced by compare().
        """
        # --- Exit 3: must_have backlog items increased ---
        must_have_delta = report.score_deltas.get("must_have_count", None)
        if must_have_delta is not None and must_have_delta > 0:
            log.warning("CI exit 3: must_have backlog count increased by %.0f", must_have_delta)
            return 3

        # --- Exit 2: WCAG critical violations increased ---
        wcag_delta = report.score_deltas.get("wcag_critical_count", None)
        if wcag_delta is not None and wcag_delta > 0:
            log.warning("CI exit 2: WCAG critical violations increased by %.0f", wcag_delta)
            return 2

        # --- Exit 1: overall feature completeness dropped > threshold ---
        # Check both customer and admin completeness keys
        completeness_keys = [k for k in report.score_deltas if "completeness" in k.lower()]
        for key in completeness_keys:
            delta = report.score_deltas[key]
            if delta < -_COMPLETENESS_DROP_THRESHOLD:
                log.warning("CI exit 1: %s dropped by %.1f%%", key, abs(delta))
                return 1

        # --- Exit 1 fallback: any complete->broken regressions ---
        critical_regressions = [
            r for r in report.regressions if r.get("regression_type", "") == "complete->broken"
        ]
        if critical_regressions:
            log.warning(
                "CI exit 1: %d complete→broken regressions detected",
                len(critical_regressions),
            )
            return 1

        return 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load(path: str) -> dict:
        """Load and parse a JSON assessment file."""
        p = pathlib.Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Assessment file not found: {path}")
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def save_baseline(
    assessment_data: dict,
    data_dir: pathlib.Path,
) -> pathlib.Path:
    """
    Serialise assessment_data to JSON and save as the latest baseline under
    data_dir/assessment_history/.

    Two files are written atomically (write-then-rename):
      1. <assessment_id>.json  — immutable snapshot keyed by ID
      2. latest.json           — always points to the most recent baseline

    Args:
        assessment_data: Dict produced by DashboardAssessment.run_assessment()
                         (must contain "assessment_id" and "generated_at" keys).
        data_dir:        Root data directory (pathlib.Path), e.g. Path("data").

    Returns:
        Path to the saved <assessment_id>.json file.
    """
    history_dir = data_dir / "assessment_history"
    history_dir.mkdir(parents=True, exist_ok=True)

    assessment_id = assessment_data.get("assessment_id", str(uuid.uuid4()))
    json_bytes = json.dumps(_serialise(assessment_data), indent=2, ensure_ascii=False).encode(
        "utf-8"
    )

    # Write snapshot file
    snapshot_path = history_dir / f"{assessment_id}.json"
    _atomic_write(snapshot_path, json_bytes)

    # Write latest.json
    latest_path = history_dir / "latest.json"
    _atomic_write(latest_path, json_bytes)

    log.info("Baseline saved: %s", snapshot_path)
    return snapshot_path


def load_baseline(
    data_dir: pathlib.Path,
    baseline_id: str = "latest",
) -> dict | None:
    """
    Load a baseline JSON from data_dir/assessment_history/.

    Args:
        data_dir:    Root data directory.
        baseline_id: Either "latest" or a specific assessment_id.

    Returns:
        Parsed dict, or None if the file does not exist.
    """
    history_dir = data_dir / "assessment_history"
    filename = "latest.json" if baseline_id == "latest" else f"{baseline_id}.json"
    path = history_dir / filename

    if not path.exists():
        log.warning("Baseline not found: %s", path)
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        log.error("Corrupt baseline JSON at %s: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _atomic_write(path: pathlib.Path, data: bytes) -> None:
    """Write data to a temp file then rename — avoids partial-write corruption."""
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_bytes(data)
        tmp.replace(path)
    except Exception:
        # Clean up temp on failure
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def _serialise(obj):
    """Recursively make an assessment dict JSON-serialisable."""
    if isinstance(obj, dict):
        return {k: _serialise(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialise(v) for v in obj]
    # dataclasses / enums — convert to string/dict where needed
    if hasattr(obj, "value"):  # Enum
        return obj.value
    if hasattr(obj, "__dataclass_fields__"):
        import dataclasses

        return _serialise(dataclasses.asdict(obj))
    return obj
