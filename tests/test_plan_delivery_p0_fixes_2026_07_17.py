"""Regression tests for 2026-07-17 customer plan delivery P0 fixes."""

from __future__ import annotations

from pathlib import Path


def test_branded_posters_count_excludes_festival(monkeypatch, tmp_path):
    """Festival SVG/text must NOT pad the '4 branded posters' entitlement."""
    monkeypatch.setattr(
        "app.marketing.clients_store._CLIENTS_FILE",
        lambda: str(tmp_path / "clients.jsonl"),
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.auto_content._QUEUE_DIR",
        lambda: str(tmp_path / "content_queue"),
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.content_approval._FILE",
        lambda: str(tmp_path / "approvals.jsonl"),
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.delivery_ledger._LEDGER_DIR",
        lambda: str(tmp_path / "delivery_ledger"),
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.delivery_ledger._CONTENT_QUEUE_DIR",
        lambda: str(tmp_path / "content_queue"),
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.product_one_delivery._DELIVERY_DIR",
        str(tmp_path / "product_one_delivery"),
        raising=False,
    )

    from app.marketing import auto_content, product_one_delivery

    c = {
        "id": "c1",
        "business_name": "Jiya Test",
        "plan": "starter",
        "product": "marketing",
        "status": "active",
        "city": "Nagpur",
        "phone": "9359984977",
        "services": "Makeup",
        "target_area": "Nagpur",
        "approval_preference": "manual",
        "brand": {"primary": "#111", "logo_text": "Jiya"},
        "socials": {"instagram": "x", "facebook": "", "gbp": ""},
        "created_at": "2026-07-07T00:00:00+00:00",
    }
    items = [
        {
            "id": "p1",
            "client_id": "c1",
            "date": "2026-07-01",
            "type": "poster",
            "title": "P",
            "status": "draft",
            "created_at": "2026-07-01T00:00:00+00:00",
        },
        {
            "id": "f1",
            "client_id": "c1",
            "date": "2026-07-02",
            "type": "festival",
            "title": "F1",
            "status": "draft",
            "created_at": "2026-07-02T00:00:00+00:00",
        },
        {
            "id": "f2",
            "client_id": "c1",
            "date": "2026-07-03",
            "type": "festival",
            "title": "F2",
            "status": "draft",
            "created_at": "2026-07-03T00:00:00+00:00",
        },
        {
            "id": "f3",
            "client_id": "c1",
            "date": "2026-07-04",
            "type": "festival",
            "title": "F3",
            "status": "draft",
            "created_at": "2026-07-04T00:00:00+00:00",
        },
    ]
    assert auto_content._append_items("c1", items) == 4
    state = product_one_delivery.customer_delivery_status("c1", c)
    by_id = {d["id"]: d for d in state["deliverables"]}
    assert by_id["branded_posters"]["status"] == "in_progress"
    assert "1/4" in by_id["branded_posters"]["proof_note"]


def test_safe_client_phone_rejects_placeholder():
    from app.marketing.auto_content import _safe_client_phone

    assert _safe_client_phone({"phone": "+919876543210"}) == ""
    assert _safe_client_phone({"phone": "9876543210"}) == ""
    assert _safe_client_phone({"phone": "9359984977"}) == "9359984977"


def test_resolve_client_by_billing_alias(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.marketing.clients_store._CLIENTS_FILE",
        lambda: str(tmp_path / "clients.jsonl"),
        raising=False,
    )
    from app.marketing import clients_store

    clients_store.add_client(
        "Jiya Makeover Studio",
        "beauty_makeover",
        city="Nagpur",
        phone="9359984977",
        plan="starter",
    )
    # Force known id + billing alias like prod
    rows = clients_store.list_clients()
    assert rows
    cid = rows[0]["id"]
    clients_store.update_client(cid, billing_client_ids=["d79d690f61b3"])

    resolved = clients_store.resolve_client("d79d690f61b3")
    assert resolved is not None
    assert resolved["id"] == cid
    assert clients_store.canonical_client_id("d79d690f61b3") == cid


def test_build_report_uses_marketing_id_not_billing_alias(monkeypatch, tmp_path):
    """Sync + asyncio.run — pytest-asyncio session loop ke baad asyncio.run loop todta hai."""
    import asyncio

    monkeypatch.setattr(
        "app.marketing.clients_store._CLIENTS_FILE",
        lambda: str(tmp_path / "clients.jsonl"),
        raising=False,
    )
    monkeypatch.setattr(
        "app.marketing.client_report._OUT_DIR", str(tmp_path / "client_reports"), raising=False
    )
    monkeypatch.setattr(
        "app.marketing.delivery_ledger._LEDGER_DIR",
        lambda: str(tmp_path / "delivery_ledger"),
        raising=False,
    )

    from app.marketing import client_report, clients_store, delivery_ledger

    clients_store.add_client(
        "Jiya Makeover Studio",
        "beauty_makeover",
        city="Nagpur",
        phone="9359984977",
        plan="starter",
    )
    cid = clients_store.list_clients()[0]["id"]
    clients_store.update_client(cid, billing_client_ids=["d79d690f61b3"], email="")

    r = asyncio.run(client_report.build_report("d79d690f61b3", month="2026-07", send=False))
    assert r.get("ok") is True
    assert r.get("client_id") == cid
    assert Path(r["path"]).name == f"{cid}_2026-07.html"
    assert Path(r["path"]).is_file()
    summary = delivery_ledger.summary(cid)
    assert int(summary.get("reports") or 0) >= 1


def test_append_items_detailed_returns_only_new_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.marketing.auto_content._QUEUE_DIR",
        lambda: str(tmp_path / "content_queue"),
        raising=False,
    )
    from app.marketing import auto_content

    items = [
        {
            "id": "a",
            "date": "2026-07-17",
            "type": "post",
            "caption": "Hello world caption ok",
            "status": "draft",
        },
        {
            "id": "b",
            "date": "2026-07-17",
            "type": "whatsapp",
            "caption": "WA promo caption ok",
            "status": "draft",
        },
    ]
    n1, added1 = auto_content._append_items_detailed("c1", items)
    assert n1 == 2 and len(added1) == 2
    n2, added2 = auto_content._append_items_detailed("c1", items)
    assert n2 == 0 and added2 == []
