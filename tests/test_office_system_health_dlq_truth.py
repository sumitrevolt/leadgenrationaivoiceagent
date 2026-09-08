"""ADR-104 Phase F (2026-07-15) -- Operating HQ "System health" widget DLQ truth.

Live discovery during the Phase F walkthrough: /app/office's War Room ->
"System health" panel showed "Queue: celery=0 · dlq=0" with a green dot and
"sab healthy hai", while the SAME page's own Reliability Console (below, on
the same snapshot) correctly showed 4 dead/exhausted tasks. Root cause:
OFFICE.renderSystemHealth() only ever read q.dlq (the retryable-failed
count) and never read q.dead (retry-exhausted, see app/platform/
automation_health.py queue_depth()) even though the backend's normalized
queue object (fixed under ADR-104 Phase B) has carried both fields all
along -- this was a frontend read gap, not a backend/model gap.

Same test convention as test_delivery_cockpit_dlq_truth.py: pure text/
structure assertions against the shipped HTML/JS (no JS runtime assumed on
PATH).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGE = REPO_ROOT / "frontend" / "office_map.html"


def _text() -> str:
    return PAGE.read_text(encoding="utf-8")


def _render_system_health_body() -> str:
    t = _text()
    start = t.index("OFFICE.renderSystemHealth = function(health){")
    brace_start = t.index("{", start)
    depth = 0
    i = brace_start
    while i < len(t):
        ch = t[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return t[start : i + 1]
        i += 1
    raise AssertionError("unbalanced braces in renderSystemHealth")


def test_page_exists():
    assert PAGE.exists()


def test_render_system_health_reads_both_dlq_and_dead():
    body = _render_system_health_body()
    assert "q.dlq" in body
    assert "q.dead" in body


def test_health_dot_is_red_when_dead_nonzero_even_if_dlq_zero():
    """The dot color decision must OR in deadCount, not just retryFailedCount."""
    body = _render_system_health_body()
    dot_expr_idx = body.index("hasDeadOrFailed ?")
    has_dead_or_failed_def_idx = body.index("var hasDeadOrFailed")
    assert has_dead_or_failed_def_idx < dot_expr_idx
    definition_line = body[has_dead_or_failed_def_idx : body.index(";", has_dead_or_failed_def_idx)]
    assert "retryFailedCount > 0" in definition_line
    assert "deadCount > 0" in definition_line


def test_empty_note_never_claims_healthy_when_dead_or_failed_nonzero():
    body = _render_system_health_body()
    healthy_note_idx = body.index("sab healthy hai.</div>")
    warn_note_idx = body.index("dono 0 hon.</div>")
    hasdeadorfailed_ternary_idx = body.index("var emptyNote = hasDeadOrFailed")
    # the ternary must pick the warn note when hasDeadOrFailed, not the
    # healthy note -- i.e. the warn branch is the `?` arm (comes first
    # textually right after the condition), healthy is the `:` (else) arm.
    assert hasdeadorfailed_ternary_idx < warn_note_idx < healthy_note_idx


def test_dead_nonzero_row_is_clickable_to_reliability_console():
    body = _render_system_health_body()
    assert 'data-cta="failureConsoleCard' in body
    assert 'OFFICE.jumpToCta(row.getAttribute("data-cta"))' in body


def test_queue_line_labels_are_unambiguous():
    """Old label was just "dlq=" (ambiguous vs the separate dead concept
    elsewhere on the same page); must now say retry-failed vs dead explicitly."""
    body = _render_system_health_body()
    assert "retry-failed=" in body
    assert "· dead=" in body
