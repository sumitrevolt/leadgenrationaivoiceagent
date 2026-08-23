"""ADR-104 Phase F (2026-07-15) -- Control Center frontend DLQ truth.

Live discovery during the Phase F walkthrough: /app/control-center's header
"QUEUE / DLQ" tile and its "DLQ / Queue" detail tab both showed "DLQ 0" /
"Queue clean" while the Reliability Console (same underlying
automation_health.health() snapshot) correctly showed 4 dead/exhausted
tasks. Root cause was three separate frontend read gaps in
frontend/control_center.html, all ignoring q.dead even where the source
object already carried it -- fixed alongside the backend gap in
app/api/control_center.py (see tests/test_control_center.py).

Same test convention as test_delivery_cockpit_dlq_truth.py /
test_office_system_health_dlq_truth.py: pure text/structure assertions
against the shipped HTML/JS (no JS runtime assumed on PATH).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGE = REPO_ROOT / "frontend" / "control_center.html"


def _text() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_page_exists():
    assert PAGE.exists()


def test_client_side_adapter_path_carries_dead_through():
    """The autoh.queue -> o.metrics.queue adapter (used when composing from
    raw sub-fetches) must not drop q.dead like it used to."""
    t = _text()
    start = t.index("// queue / dlq")
    end = t.index(";", t.index("o.metrics.queue = {", start))
    block = t[start:end]
    assert "q.dead" in block


def test_dlq_tab_shows_dead_count_and_gates_clean_message_on_both():
    t = _text()
    start = t.index("} else if (BOT === 'dlq') {")
    end = t.index("} else {", start)
    block = t[start:end]
    assert "deadCount" in block
    assert "dlqCount" in block
    assert "anyBad" in block
    # "Queue clean" must only be reachable through the anyBad-false branch of
    # the rendered ternary -- use rindex since the explanatory comment above
    # the code also mentions the phrase "Queue clean" in prose.
    clean_idx = block.rindex("Queue clean")
    anybad_ternary_idx = block.index("anyBad ?")
    assert anybad_ternary_idx < clean_idx


def test_header_tile_reflects_dead_count_in_status_and_label():
    t = _text()
    start = t.index("// Queue / DLQ")
    end = t.index("setBadge('m-queue'", start)
    block = t[start:end]
    assert "qDead" in block
    assert "m.queue.dead" in block
    # status class must go 'bad' when dead alone is nonzero, not just dlq.
    qcls_line = block[block.index("var qcls") : block.index(";", block.index("var qcls"))]
    assert "qDead > 0" in qcls_line
