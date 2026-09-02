"""
Report Parser — parses DASHBOARD_ASSESSMENT_REPORT.md back into structured data.
Supports round-trip: parse → format_summary → parse preserves scores dict.
"""

from __future__ import annotations

import logging
import pathlib
import re
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

# Required section headings that must be present for format validation
_REQUIRED_SECTIONS = [
    "Scoreboard",
    "Customer Dashboard",
    "Admin Dashboard",
    "Recommendations",
]


class AssessmentReportParser:
    """Parse a DASHBOARD_ASSESSMENT_REPORT.md into structured Python dicts."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, report_path: str) -> dict:
        """
        Parse report into dict with keys:
            scores    – Dict[str, float]   (metric → value)
            features  – List[Dict]          (per-dashboard feature rows)
            gaps      – List[Dict]          (recommendation items)
            issues    – List[Dict]          (UX heuristic issues)
            backlog   – List[Dict]          (combined ranked items)
        """
        path = pathlib.Path(report_path)
        if not path.exists():
            raise FileNotFoundError(f"Report not found: {report_path}")

        content = path.read_text(encoding="utf-8", errors="ignore")

        scores = self._parse_scores(content)
        features = self._parse_all_features(content)
        issues = self._parse_ux_issues(content)
        gaps = self._parse_recommendations(content)
        backlog = self._parse_backlog(content)

        return {
            "scores": scores,
            "features": features,
            "gaps": gaps,
            "issues": issues,
            "backlog": backlog,
        }

    def parse_table(self, table_markdown: str) -> list[dict]:
        """
        Parse a markdown table (pipe-delimited rows) into a list of dicts.

        Example input:
            | Dashboard | Size | Sections |
            | --- | --- | --- |
            | Customer | 58.5 KB | 0 |

        Returns:
            [{"Dashboard": "Customer", "Size": "58.5 KB", "Sections": "0"}, ...]
        """
        lines = [ln.strip() for ln in table_markdown.strip().splitlines() if ln.strip()]

        # Filter to lines that look like table rows (start and end with |)
        table_lines = [ln for ln in lines if ln.startswith("|") and ln.endswith("|")]
        if len(table_lines) < 2:
            return []

        # Parse header row
        headers = [h.strip() for h in table_lines[0].strip("|").split("|")]

        # Skip separator row (--- pattern)
        data_start = 1
        if len(table_lines) > 1:
            sep = table_lines[1].strip("|").replace("-", "").replace(" ", "")
            if sep == "" or all(c in "-: " for c in table_lines[1].replace("|", "")):
                data_start = 2

        rows: list[dict] = []
        for line in table_lines[data_start:]:
            cells = [c.strip() for c in line.strip("|").split("|")]
            # Pad or truncate to match header count
            while len(cells) < len(headers):
                cells.append("")
            row = {headers[i]: cells[i] for i in range(len(headers))}
            rows.append(row)

        return rows

    def extract_section(self, content: str, section_name: str) -> str:
        """
        Extract content between a ## heading matching section_name and the next
        ## heading (or end of file).

        Returns the extracted text (excluding the heading line itself), or ""
        if the section is not found.
        """
        # Build pattern: ## <section_name> (case-insensitive, anchored to line start)
        escaped = re.escape(section_name)
        pattern = rf"(?m)^##\s+{escaped}\s*$"
        m = re.search(pattern, content, re.IGNORECASE)
        if not m:
            return ""

        start = m.end()
        # Find the next ## heading
        next_heading = re.search(r"(?m)^##\s+", content[start:])
        if next_heading:
            end = start + next_heading.start()
            return content[start:end].strip()
        return content[start:].strip()

    def validate_format(self, report_path: str) -> bool:
        """
        Check that required sections (## headings) exist in the report.
        Returns True only if ALL required sections are present.
        """
        path = pathlib.Path(report_path)
        if not path.exists():
            log.warning("validate_format: file not found: %s", report_path)
            return False

        content = path.read_text(encoding="utf-8", errors="ignore")
        missing = []
        for section in _REQUIRED_SECTIONS:
            escaped = re.escape(section)
            if not re.search(rf"(?m)^##\s+{escaped}", content, re.IGNORECASE):
                missing.append(section)

        if missing:
            log.warning("validate_format: missing sections: %s", missing)
            return False
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_scores(self, content: str) -> dict[str, float]:
        """
        Extract numeric scores from the Scoreboard table or inline metrics.
        Returns a dict like:
          {
            "customer_ux_heuristics": 75.0,
            "admin_ux_heuristics": 75.0,
            "customer_charts": 4.0,
            "customer_tables": 3.0,
            ...
          }
        """
        scores: dict[str, float] = {}

        scoreboard_raw = self.extract_section(content, "Scoreboard")
        if scoreboard_raw:
            rows = self.parse_table(scoreboard_raw)
            for row in rows:
                dashboard_key = row.get("Dashboard", "").lower().replace(" ", "_")
                if not dashboard_key:
                    continue
                for col, val in row.items():
                    if col == "Dashboard":
                        continue
                    metric_key = (
                        f"{dashboard_key}_{col.lower().replace(' ', '_').replace('/', '_')}"
                    )
                    # Extract numeric part (e.g. "6/8 (75%)" → 75.0, "58.5 KB" → 58.5, "4" → 4.0)
                    pct_m = re.search(r"\((\d+(?:\.\d+)?)%\)", val)
                    if pct_m:
                        scores[metric_key] = float(pct_m.group(1))
                        continue
                    num_m = re.search(r"(\d+(?:\.\d+)?)", val)
                    if num_m:
                        scores[metric_key] = float(num_m.group(1))

        # Parse per-dashboard inventory tables for additional metrics
        for dash in ("Customer", "Admin"):
            dash_content = self.extract_section(content, f"{dash} Dashboard")
            if not dash_content:
                continue
            prefix = dash.lower()

            # Find the Inventory sub-table
            inv_match = re.search(r"\*\*Inventory\*\*\s*\n((?:\|[^\n]+\n)+)", dash_content)
            if inv_match:
                inv_rows = self.parse_table(inv_match.group(1))
                for inv_row in inv_rows:
                    metric = inv_row.get("Metric", "").lower().replace(" ", "_").replace("/", "_")
                    count_str = inv_row.get("Count", "0")
                    # Strip non-numeric chars for size like "58.5 KB"
                    num_m = re.search(r"(\d+(?:\.\d+)?)", count_str)
                    if metric and num_m:
                        scores[f"{prefix}_{metric}"] = float(num_m.group(1))

        # Infer completeness from UX heuristics score if present
        for dash in ("customer", "admin"):
            heur_key = f"{dash}_ux_heuristics"
            if heur_key not in scores:
                # Try to find "X/8 (Y%)" pattern in the heuristics section
                m = re.search(
                    rf"\b{dash.capitalize()}\b.*?(\d+)/(\d+)\s*\((\d+)%\)",
                    content,
                    re.IGNORECASE | re.DOTALL,
                )
                if m:
                    scores[heur_key] = float(m.group(3))

        return scores

    def _parse_all_features(self, content: str) -> list[dict]:
        """Parse inventory rows from Customer + Admin Dashboard sections."""
        features: list[dict] = []
        for dash in ("Customer", "Admin"):
            dash_content = self.extract_section(content, f"{dash} Dashboard")
            if not dash_content:
                continue
            inv_match = re.search(r"\*\*Inventory\*\*\s*\n((?:\|[^\n]+\n?)+)", dash_content)
            if inv_match:
                rows = self.parse_table(inv_match.group(1))
                for row in rows:
                    row["_dashboard"] = dash.lower()
                    features.append(row)
        return features

    def _parse_ux_issues(self, content: str) -> list[dict]:
        """
        Parse UX heuristics tables and return a list of issues
        (only rows where Present? indicates a problem: ⚠️/missing/no/❌).
        """
        issues: list[dict] = []
        for dash in ("Customer", "Admin"):
            dash_content = self.extract_section(content, f"{dash} Dashboard")
            if not dash_content:
                continue
            heur_match = re.search(r"\*\*UX heuristics\*\*\s*\n((?:\|[^\n]+\n?)+)", dash_content)
            if not heur_match:
                continue
            rows = self.parse_table(heur_match.group(1))
            for row in rows:
                present_val = row.get("Present?", "").lower()
                # Flag rows that look like failures
                if any(kw in present_val for kw in ["missing", "no ", "⚠", "❌", "warn"]):
                    check = row.get("Check", "")
                    if check:
                        issues.append(
                            {
                                "name": check,
                                "dashboard": dash.lower(),
                                "present": row.get("Present?", ""),
                                "is_wcag": any(
                                    kw in check.lower()
                                    for kw in [
                                        "aria",
                                        "focus",
                                        "keyboard",
                                        "screen reader",
                                        "contrast",
                                    ]
                                ),
                            }
                        )
        return issues

    def _parse_recommendations(self, content: str) -> list[dict]:
        """
        Parse numbered recommendations from the Recommendations section.
        Returns list of dicts with keys: rank (int), title (str), detail (str).
        """
        rec_content = self.extract_section(content, "Recommendations")
        if not rec_content:
            return []

        gaps: list[dict] = []
        # Match numbered items: "1. **Title** — description"
        for m in re.finditer(
            r"(\d+)\.\s+\*\*([^\*]+)\*\*\s*(?:—|-|:)?\s*(.*?)(?=\n\d+\.|$)", rec_content, re.DOTALL
        ):
            rank = int(m.group(1))
            title = m.group(2).strip()
            detail = m.group(3).strip().replace("\n", " ")
            gaps.append({"rank": rank, "title": title, "detail": detail})

        return gaps

    def _parse_backlog(self, content: str) -> list[dict]:
        """
        Attempt to parse a Backlog section table if present.
        Falls back to empty list if section does not exist.
        """
        backlog_content = self.extract_section(content, "Backlog")
        if not backlog_content:
            return []
        table_match = re.search(r"((?:\|[^\n]+\n?)+)", backlog_content)
        if not table_match:
            return []
        return self.parse_table(table_match.group(1))


class AssessmentReportPrinter:
    """Format parsed assessment data back to a Markdown summary."""

    def format_summary(self, data: dict) -> str:
        """
        Format parsed data (as returned by AssessmentReportParser.parse) back
        into a Markdown report string.

        Round-trip guarantee: parse → format_summary → parse preserves the
        scores dict (numeric values survive the text serialisation → re-parse).
        """
        lines: list[str] = []
        lines.append("# Dashboard Assessment Report (Lean)")
        lines.append("")

        scores: dict[str, float] = data.get("scores", {})

        # ---- Scoreboard ----
        lines.append("## Scoreboard")
        lines.append("")

        c_ux = scores.get("customer_ux_heuristics", 0.0)
        a_ux = scores.get("admin_ux_heuristics", 0.0)
        c_size = scores.get("customer_file_size", 0.0)
        a_size = scores.get("admin_file_size", 0.0)
        c_charts = int(
            scores.get("customer_charts_(chart.js_canvas)", scores.get("customer_charts", 0))
        )
        a_charts = int(scores.get("admin_charts_(chart.js_canvas)", scores.get("admin_charts", 0)))
        c_tables = int(scores.get("customer_tables", 0))
        a_tables = int(scores.get("admin_tables", 0))

        lines.append("| Dashboard | Size | Charts | Tables | UX heuristics |")
        lines.append("| --- | --- | --- | --- | --- |")
        lines.append(f"| Customer | {c_size} KB | {c_charts} | {c_tables} | {c_ux:.0f}% |")
        lines.append(f"| Admin | {a_size} KB | {a_charts} | {a_tables} | {a_ux:.0f}% |")
        lines.append("")

        # ---- Per-dashboard inventory ----
        features: list[dict] = data.get("features", [])
        for dash in ("customer", "admin"):
            dash_features = [f for f in features if f.get("_dashboard") == dash]
            lines.append(f"## {dash.capitalize()} Dashboard")
            lines.append("")
            lines.append("**Inventory**")
            lines.append("")
            lines.append("| Metric | Count |")
            lines.append("| --- | --- |")
            for row in dash_features:
                for k, v in row.items():
                    if k == "_dashboard":
                        continue
                    lines.append(f"| {k} | {v} |")
            lines.append("")

        # ---- UX Issues ----
        issues: list[dict] = data.get("issues", [])
        if issues:
            lines.append("## UX Issues")
            lines.append("")
            lines.append("| Dashboard | Check | Present? |")
            lines.append("| --- | --- | --- |")
            for issue in issues:
                lines.append(
                    f"| {issue.get('dashboard', '')} "
                    f"| {issue.get('name', '')} "
                    f"| {issue.get('present', '⚠️ missing')} |"
                )
            lines.append("")

        # ---- Recommendations (gaps) ----
        gaps: list[dict] = data.get("gaps", [])
        if gaps:
            lines.append("## Recommendations")
            lines.append("")
            for gap in gaps:
                rank = gap.get("rank", "")
                title = gap.get("title", "")
                detail = gap.get("detail", "")
                if detail:
                    lines.append(f"{rank}. **{title}** — {detail}")
                else:
                    lines.append(f"{rank}. **{title}**")
            lines.append("")

        # ---- Backlog ----
        backlog: list[dict] = data.get("backlog", [])
        if backlog:
            lines.append("## Backlog")
            lines.append("")
            if backlog:
                headers = list(backlog[0].keys())
                lines.append("| " + " | ".join(headers) + " |")
                lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
                for item in backlog:
                    lines.append("| " + " | ".join(str(item.get(h, "")) for h in headers) + " |")
            lines.append("")

        return "\n".join(lines)
