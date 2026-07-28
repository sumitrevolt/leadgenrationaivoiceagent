"""Contract: Product One `generate_content` ab gbp_suggestions + review_replies
deliverables ko REAL content se poora karta hai (audit 2026-07-19 / Jiya 60%).

- generate_gbp_pack     -> ek `gbp` content item (prioritised profile fixes)
- generate_review_reply_pack -> ek `review_reply` item (3 reply drafts)
Dono self-guarding (dobara chalane pe dupe nahi), aur customer_delivery_status
inhe dekh kar dono deliverables ko "done" karta hai. External LLM test me OFF —
deterministic fallback guarantee karta hai content kabhi empty na ho.
"""

import asyncio

from app.marketing import (
    auto_content,
    clients_store,
    content_approval,
    delivery_ledger,
    product_one_delivery,
)

CLIENT = {
    "id": "gr-test",
    "business_name": "Glow Salon",
    "niche": "beauty",
    "plan": "starter",
    "city": "Nagpur",
}


def _iso(monkeypatch, tmp_path):
    monkeypatch.setattr(auto_content, "_QUEUE_DIR", lambda: str(tmp_path / "content_queue"))
    monkeypatch.setattr(clients_store, "_CLIENTS_FILE", lambda: str(tmp_path / "clients.jsonl"))
    monkeypatch.setattr(delivery_ledger, "_LEDGER_DIR", lambda: str(tmp_path / "ledger"))
    monkeypatch.setattr(
        delivery_ledger, "_CONTENT_QUEUE_DIR", lambda: str(tmp_path / "content_queue")
    )
    monkeypatch.setattr(product_one_delivery, "_DELIVERY_DIR", str(tmp_path / "p1"))
    monkeypatch.setattr(product_one_delivery, "_REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setattr(product_one_delivery, "_GBP_AUDIT_DIR", str(tmp_path / "gbp"))
    monkeypatch.setattr(content_approval, "submit", lambda *a, **k: {"ok": True}, raising=False)
    monkeypatch.setattr(content_approval, "list_all", lambda *a, **k: [], raising=False)
    monkeypatch.setattr(content_approval, "pending", lambda *a, **k: [], raising=False)
    monkeypatch.setattr(
        product_one_delivery, "sync_customer_deliverable_status", lambda *a, **k: False
    )

    async def _boom(*a, **k):
        raise RuntimeError("no external LLM in tests")

    monkeypatch.setattr("app.voice_agent.free_ai.chat", _boom, raising=False)


def _types(cid):
    return [str(i.get("type") or "").lower() for i in auto_content.list_queue(cid, limit=200)]


def test_generate_gbp_pack_creates_gbp_item_and_self_guards(monkeypatch, tmp_path):
    _iso(monkeypatch, tmp_path)
    n = asyncio.run(auto_content.generate_gbp_pack(CLIENT))
    assert n == 1
    gbp = [
        i
        for i in auto_content.list_queue("gr-test", limit=50)
        if str(i.get("type")).lower() == "gbp"
    ]
    assert len(gbp) == 1
    assert len(gbp[0]["caption"]) >= 10  # passes _caption_ok min length
    # self-guard: second run must not duplicate
    assert asyncio.run(auto_content.generate_gbp_pack(CLIENT)) == 0
    assert _types("gr-test").count("gbp") == 1


def test_generate_review_reply_pack_creates_item_and_self_guards(monkeypatch, tmp_path):
    _iso(monkeypatch, tmp_path)
    n = asyncio.run(auto_content.generate_review_reply_pack(CLIENT))
    assert n == 1
    rr = [
        i
        for i in auto_content.list_queue("gr-test", limit=50)
        if str(i.get("type")).lower() == "review_reply"
    ]
    assert len(rr) == 1
    # deterministic fallback personalizes with the business name
    assert "Glow Salon" in rr[0]["caption"]
    assert asyncio.run(auto_content.generate_review_reply_pack(CLIENT)) == 0
    assert _types("gr-test").count("review_reply") == 1


def test_delivery_status_marks_gbp_and_review_done(monkeypatch, tmp_path):
    _iso(monkeypatch, tmp_path)
    asyncio.run(auto_content.generate_gbp_pack(CLIENT))
    asyncio.run(auto_content.generate_review_reply_pack(CLIENT))
    st = product_one_delivery.customer_delivery_status("gr-test", CLIENT)
    dels = {d["id"]: d["status"] for d in (st.get("deliverables") or [])}
    assert dels.get("gbp_suggestions") == "done"
    assert dels.get("review_replies") == "done"


def test_seed_client_content_covers_gbp_and_review(monkeypatch, tmp_path):
    """The canonical generate_content path (seed_client_content) now produces
    both new deliverables end-to-end."""
    _iso(monkeypatch, tmp_path)
    asyncio.run(auto_content.seed_client_content(CLIENT))
    types = set(_types("gr-test"))
    assert "gbp" in types
    assert "review_reply" in types


def test_generate_poster_pack_reaches_target_and_self_guards(monkeypatch, tmp_path):
    _iso(monkeypatch, tmp_path)
    n = asyncio.run(auto_content.generate_poster_pack(CLIENT, target=4))
    assert n == 4  # started with 0
    posters = [
        i
        for i in auto_content.list_queue("gr-test", limit=200)
        if str(i.get("type")).lower() == "poster"
    ]
    assert len(posters) == 4
    assert all(str(p.get("svg") or "").strip() for p in posters)  # real SVG only
    # self-guard: already at target -> nothing more
    assert asyncio.run(auto_content.generate_poster_pack(CLIENT, target=4)) == 0
    assert _types("gr-test").count("poster") == 4


def test_delivery_status_marks_posters_done(monkeypatch, tmp_path):
    _iso(monkeypatch, tmp_path)
    asyncio.run(auto_content.generate_poster_pack(CLIENT, target=4))
    st = product_one_delivery.customer_delivery_status("gr-test", CLIENT)
    dels = {d["id"]: d["status"] for d in (st.get("deliverables") or [])}
    assert dels.get("branded_posters") == "done"
