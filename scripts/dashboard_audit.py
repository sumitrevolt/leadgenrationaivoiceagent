#!/usr/bin/env python3
"""
dashboard_audit.py — LEAN one-shot audit of customer + admin dashboards.

Deliberately NOT the 7-module framework from the Kiro design doc (scanner /
gap_analyzer / ux_evaluator / prioritizer / report_parser / regression_detector
/ CI) — that is over-engineered for two static HTML files that change rarely.
This is a single-file, stdlib-only static heuristic scan that emits a markdown
report. Re-run anytime: `python scripts/dashboard_audit.py`.

Honest caveat: static heuristics detect PRESENCE of patterns, not whether a
feature actually works at runtime. Treat as a checklist, not a guarantee.
"""

from __future__ import annotations

import datetime
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
DOCS = ROOT / "docs"
DASHBOARDS = {
    "Customer": FRONTEND / "customer_dashboard.html",
    "Admin": FRONTEND / "admin_dashboard.html",
}


def inventory(html: str) -> dict:
    return {
        "size_kb": round(len(html) / 1024, 1),
        "sections": len(re.findall(r'id="sec-', html))
        or len(re.findall(r"<section\b", html, re.I)),
        "kpi_cards": len(re.findall(r'class="[^"]*\b(?:kpi|stat|metric)\b', html, re.I)),
        "charts": len(re.findall(r"new\s+Chart\(|<canvas\b", html, re.I)),
        "tables": len(re.findall(r"<table\b", html, re.I)),
        "buttons": len(re.findall(r"<button\b", html, re.I)),
        "inputs": len(re.findall(r"<input\b|<select\b|<textarea\b", html, re.I)),
        "api_endpoints": sorted(set(re.findall(r'["\'`](/api/[A-Za-z0-9_\-/]+)', html))),
    }


UX_CHECKS = [
    ("Loading states", r"spinner|skeleton|loading|aria-busy"),
    ("Empty states", r"empty|no data|nothing|abhi tak|koi[^<]{0,20}nahi"),
    ("Error handling", r"\.catch\(|onerror|catch\s*\(|error"),
    ("Action feedback (toast)", r"toast|notify|snackbar|alert\("),
    ("ARIA / screen-reader", r"aria-label|aria-[a-z]+="),
    ("Responsive (@media/viewport)", r'@media|name="viewport"'),
    ("Keyboard focus", r":focus|tabindex"),
    ("Semantic landmarks", r"<nav\b|<header\b|<main\b|<aside\b|<footer\b"),
]


def ux_eval(html: str):
    out = []
    for label, pat in UX_CHECKS:
        out.append((label, bool(re.search(pat, html, re.I))))
    passed = sum(1 for _, ok in out if ok)
    return out, passed, len(out)


def md_table(headers, rows):
    s = "| " + " | ".join(headers) + " |\n"
    s += "| " + " | ".join("---" for _ in headers) + " |\n"
    for r in rows:
        s += "| " + " | ".join(str(c) for c in r) + " |\n"
    return s


def main():
    today = datetime.date.today().isoformat()
    parts = [
        "# Dashboard Assessment Report (Lean)",
        "",
        f"**Generated:** {today} · **Tool:** `scripts/dashboard_audit.py` (single-file static heuristic scan)",
        "",
        "> **Why lean, not the framework:** the design doc proposed 7 Python modules + parser + "
        "regression-detector + CI to audit two static HTML files. That is over-engineered for files "
        "that change rarely, and LeadGen AI already hand-writes gap docs effectively. This script is "
        "the pragmatic substitute. **Caveat:** heuristics detect *presence* of patterns, not runtime "
        "correctness — treat as a checklist.",
        "",
        "## Scoreboard",
        "",
    ]
    score_rows = []
    detail_blocks = []
    for name, path in DASHBOARDS.items():
        if not path.exists():
            score_rows.append([name, "MISSING", "-", "-", "-", "-"])
            continue
        html = path.read_text(encoding="utf-8", errors="ignore")
        inv = inventory(html)
        ux, passed, total = ux_eval(html)
        pct = round(passed / total * 100)
        score_rows.append(
            [
                name,
                f"{inv['size_kb']} KB",
                inv["sections"],
                inv["charts"],
                inv["tables"],
                f"{passed}/{total} ({pct}%)",
            ]
        )
        b = [
            f"## {name} Dashboard",
            "",
            "**Inventory**",
            "",
            md_table(
                ["Metric", "Count"],
                [
                    ["File size", f"{inv['size_kb']} KB"],
                    ["Sections", inv["sections"]],
                    ["KPI / stat cards", inv["kpi_cards"]],
                    ["Charts (Chart.js/canvas)", inv["charts"]],
                    ["Tables", inv["tables"]],
                    ["Buttons", inv["buttons"]],
                    ["Form inputs", inv["inputs"]],
                    ["Distinct /api endpoints", len(inv["api_endpoints"])],
                ],
            ),
            "",
            "**UX heuristics**",
            "",
            md_table(["Check", "Present?"], [[lbl, "✅" if ok else "⚠️ missing"] for lbl, ok in ux]),
            "",
            "**Discovered API endpoints**",
            "",
            (
                ("- " + "\n- ".join(inv["api_endpoints"]))
                if inv["api_endpoints"]
                else "_none detected_"
            ),
            "",
        ]
        detail_blocks.append("\n".join(b))
    parts.append(
        md_table(["Dashboard", "Size", "Sections", "Charts", "Tables", "UX heuristics"], score_rows)
    )
    parts.append("")
    parts.extend(detail_blocks)
    parts += [
        "## Recommendations (tie to existing backlog)",
        "",
        "These map to gaps already tracked in `docs/Competitor_Top20_Feature_Gap_2026.md` — "
        "do not spin up new tracking:",
        "",
        "1. **Speed-to-lead SLA badge** (P0 #7) — surface inquiry→first-touch time on the "
        'customer dashboard ("2-min me jawab"). Marketing gold, infra already exists.',
        "2. **Lead-distribution round-robin** (P0 #10) — admin dashboard view to auto-assign "
        "leads to client staff.",
        "3. **AI-search / GEO visibility score** (P1 #11) — new lead-magnet card after audit/site-audit.",
        "4. **UX polish** — address any ⚠️ rows above (loading/empty/error states) before scaling paid signups.",
        "",
        "_Report regenerated by re-running `python scripts/dashboard_audit.py`._",
    ]
    out = DOCS / "DASHBOARD_ASSESSMENT_REPORT.md"
    out.write_text("\n".join(parts), encoding="utf-8")
    print("WROTE", out)
    print("\n".join(parts[:14]))


if __name__ == "__main__":
    main()
