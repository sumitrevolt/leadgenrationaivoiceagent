"""Unit test for the Admin "Aapke kaam" virtual-office aggregator
(app/api/admin_ops._admin_office) — consolidates 4 pending-approval queues.
Reads real stores best-effort so we assert shape + invariants, not exact counts."""

from app.api.admin_ops import _admin_office


def test_admin_office_shape_and_never_raises():
    o = _admin_office()
    assert isinstance(o, dict)
    for k in ("ok", "enabled", "headline", "your_tasks", "total_pending"):
        assert k in o, k
    assert o["ok"] is True
    assert isinstance(o["your_tasks"], list)
    assert isinstance(o["total_pending"], int)


def test_admin_office_tasks_sorted_and_well_formed():
    o = _admin_office()
    rank = {"high": 0, "medium": 1, "low": 2}
    seq = [rank.get(t.get("severity"), 9) for t in o["your_tasks"]]
    assert seq == sorted(seq), f"tasks not severity-sorted: {seq}"
    for t in o["your_tasks"]:
        assert t.get("title") and t.get("why"), t
        assert t.get("cta_target"), t
        assert t.get("severity") in ("high", "medium", "low"), t
        assert int(t.get("count") or 0) >= 1, t
    # total_pending == sum of per-task counts
    assert o["total_pending"] == sum(int(t.get("count") or 0) for t in o["your_tasks"])
