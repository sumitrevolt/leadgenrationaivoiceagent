"""ADR-104 Phase B follow-up (2026-07-15) — Delivery Cockpit DLQ truth fix.

Live discovery: /app/delivery-command-center showed "DLQ khaali" (all clear)
while /app/office's Reliability Console (fixed under Phase B) correctly showed
Dead(exhausted)=4. Root cause: this page's loadDlq() only ever fetched ONE
Redis key (whichever tab was selected, defaulting to "failed") instead of
both — so a nonzero dlq:dead count sitting behind the unselected "Dead" tab
was invisible at a glance.

No JS test runner is assumed to be on PATH (same constraint as
test_deploy_vps_retention.py), so these are pure text/structure assertions
against the shipped HTML/JS — cheap, portable, and they still catch the
regressions that matter: summary missing, summary computed from only one
key, or the "all clear" message reachable while dead > 0.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGE = REPO_ROOT / "frontend" / "delivery_command_center.html"


def _text() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_page_exists():
    assert PAGE.exists()


def test_dlq_summary_element_present_in_markup():
    t = _text()
    assert 'id="dlqSummary"' in t


def test_load_dlq_fetches_both_failed_and_dead_keys_for_the_summary():
    """The whole bug was fetching only DLQ_KEY (one tab) for the headline
    summary. The fix must fetch key=failed AND key=dead unconditionally,
    independent of which tab is currently selected."""
    t = _text()
    fn_start = t.index("async function loadDlq()")
    fn_end = t.index("\n  }", fn_start)
    body = t[fn_start:fn_end]
    assert "key=failed" in body
    assert "key=dead" in body
    # Must not be gated behind `DLQ_KEY ===` for the summary fetch specifically
    assert "Promise.allSettled" in body


def test_render_dlq_summary_never_shows_all_clear_when_dead_is_nonzero():
    t = _text()
    fn_start = t.index("function renderDlqSummary")
    fn_end = t.index("\n  }", fn_start)
    body = t[fn_start:fn_end]
    # Locate the dead>0 branch specifically and ensure the all-clear string
    # cannot appear inside it.
    dead_branch_start = body.index("if(dead > 0)")
    dead_branch_end = body.index("else", dead_branch_start)
    dead_branch = body[dead_branch_start:dead_branch_end]
    assert "DLQ khaali" not in dead_branch
    assert "Dead (exhausted)" in dead_branch


def test_render_dlq_summary_shows_all_clear_only_when_both_zero():
    t = _text()
    fn_start = t.index("function renderDlqSummary")
    fn_end = t.index("\n  }", fn_start)
    body = t[fn_start:fn_end]
    assert "DLQ khaali" in body
    # The all-clear branch must be the final else (both failed and dead zero),
    # not the default/first branch.
    all_clear_idx = body.index("DLQ khaali")
    dead_branch_idx = body.index("if(dead > 0)")
    failed_branch_idx = body.index("else if(failed > 0)")
    assert dead_branch_idx < failed_branch_idx < all_clear_idx


def test_dead_nonzero_summary_links_to_reliability_console():
    t = _text()
    fn_start = t.index("function renderDlqSummary")
    fn_end = t.index("\n  }", fn_start)
    body = t[fn_start:fn_end]
    dead_branch_start = body.index("if(dead > 0)")
    dead_branch_end = body.index("else", dead_branch_start)
    dead_branch = body[dead_branch_start:dead_branch_end]
    assert "/app/office#reliability" in dead_branch


def test_summary_render_call_does_not_depend_on_selected_tab():
    """renderDlqSummary must be invoked from loadDlq with values derived from
    the two parallel fetches, not from the tab-scoped `data` object rendered
    by renderDlq()."""
    t = _text()
    fn_start = t.index("async function loadDlq()")
    fn_end = t.index("\n  }", fn_start)
    body = t[fn_start:fn_end]
    assert "renderDlqSummary(" in body
    # Must be called before the tab-scoped renderDlq(data) line, using the
    # allSettled results, not `data`.
    summary_call_idx = body.index("renderDlqSummary(")
    dlq_render_idx = body.index("renderDlq(data)")
    assert summary_call_idx < dlq_render_idx
