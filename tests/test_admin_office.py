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


def test_admin_office_content_why_uses_business_names(monkeypatch):
    """Pending content hint should prefer business_name over raw client ids."""
    import app.api.admin_ops as admin_ops

    class _CA:
        @staticmethod
        def pending(_cid):
            return [
                {"client_id": "jiya-makeover"},
                {"client_id": "jiya-makeover"},
                {"client_id": "deadbeefdead"},
            ]

    class _SI:
        @staticmethod
        def approval_status():
            return {"pending_count": 0}

    class _CU:
        @staticmethod
        def list_patches(_st, _n):
            return []

    def _get_client(cid):
        if cid == "jiya-makeover":
            return {"business_name": "Jiya Makeover Studio", "slug": "jiya-makeover"}
        return None

    monkeypatch.setattr("app.marketing.content_approval.pending", _CA.pending)
    monkeypatch.setattr("app.agents.self_improve.approval_status", _SI.approval_status)
    monkeypatch.setattr("app.agents.code_upgrader.list_patches", _CU.list_patches)
    monkeypatch.setattr(admin_ops, "_pending_upi_queue", lambda _n: [])
    monkeypatch.setattr("app.marketing.clients_store.get_client", _get_client)
    monkeypatch.setattr("app.marketing.clients_store.get_by_slug", lambda _s: None)
    monkeypatch.setattr("app.platform.reply_agent.hot_queue", lambda **_kw: [])

    o = admin_ops._admin_office()
    content = next((t for t in o["your_tasks"] if t.get("id") == "content"), None)
    assert content, o["your_tasks"]
    assert "Jiya Makeover Studio" in content["why"]
    assert "jiya-makeover(" not in content["why"]


def test_admin_office_hot_queue_is_first_high_task(monkeypatch):
    """GTM bottleneck: Hot Queue must surface in Aapke kaam with /app/inbox CTA."""
    import app.api.admin_ops as admin_ops

    monkeypatch.setattr(
        "app.platform.reply_agent.hot_queue",
        lambda **_kw: [{"hq_id": "a"}, {"hq_id": "b"}, {"hq_id": "c"}],
    )
    monkeypatch.setattr(
        "app.agents.self_improve.approval_status",
        lambda: {"pending_count": 0},
    )
    monkeypatch.setattr("app.marketing.content_approval.pending", lambda _cid: [])
    monkeypatch.setattr("app.agents.code_upgrader.list_patches", lambda _st, _n: [])
    monkeypatch.setattr(admin_ops, "_pending_upi_queue", lambda _n: [])

    o = admin_ops._admin_office()
    hq = next((t for t in o["your_tasks"] if t.get("id") == "hot_queue"), None)
    assert hq, o["your_tasks"]
    assert hq["count"] == 3
    assert hq["severity"] == "high"
    assert hq["cta_href"] == "/app/inbox"
    assert hq["cta_action"] == "open_href"
    assert o["your_tasks"][0]["id"] == "hot_queue"
