"""POST /api/customer/campaigns/generate-first-week — Setup Wizard ka customer-
triggerable first-campaign path (CDOS spec: "First 7-day campaign generation").

Contract yahan prove hota hai:
(1) IDOR/auth-safe — require_customer ke bina 401/403;
(2) upcoming items pehle se hon to ENQUEUE hi nahi (seed re-run =
    content_approval me duplicate submissions — isliye guard load-bearing hai);
(3) khali queue → Celery worker task enqueue hota hai (seed multi-LLM-call hai,
    web process me kabhi inline nahi — CLAUDE.md);
(4) worker task khud bhi guard RE-check karta hai (double-click race window).
"""

import json
import os
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.marketing import auto_content, clients_store
from app.tasks import staff_jobs


def _patch_seed_task(monkeypatch, calls: list):
    """seed_first_week ek celery shared_task PROXY hai — woh har access pe current
    Celery-app registry se resolve hota hai, isliye `.delay` attribute patch
    unreliable hai. Module attribute ko hi fake se replace karo: endpoint
    request-time par `from app.tasks.staff_jobs import seed_first_week` karta
    hai, to use yahi fake milta hai."""
    monkeypatch.setattr(
        staff_jobs, "seed_first_week", SimpleNamespace(delay=lambda cid: calls.append(cid))
    )


def _override_customer(app, cid):
    from app.api.customer_auth import require_customer

    app.dependency_overrides[require_customer] = lambda: cid


def _redirect_stores(monkeypatch, tmp_path):
    monkeypatch.setattr(
        clients_store, "_CLIENTS_FILE", lambda: os.path.join(str(tmp_path), "clients.jsonl")
    )
    monkeypatch.setattr(
        auto_content, "_QUEUE_DIR", lambda: os.path.join(str(tmp_path), "content_queue")
    )


def _write_queue(cid: str, items: list[dict]):
    path = auto_content._queue_path(cid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


def test_endpoint_requires_customer_auth(monkeypatch, tmp_path):
    from app.main import app

    _redirect_stores(monkeypatch, tmp_path)
    app.dependency_overrides.clear()
    with TestClient(app) as c:
        resp = c.post("/api/customer/campaigns/generate-first-week")
    assert resp.status_code in (401, 403)


def test_unknown_client_404(monkeypatch, tmp_path):
    from app.main import app

    _redirect_stores(monkeypatch, tmp_path)
    _override_customer(app, "no-such-client")
    try:
        with TestClient(app) as c:
            resp = c.post("/api/customer/campaigns/generate-first-week")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_upcoming_items_skip_enqueue(monkeypatch, tmp_path):
    """Plan pehle se ho to already=True aur worker task KABHI enqueue na ho."""
    from datetime import date

    from app.main import app

    _redirect_stores(monkeypatch, tmp_path)
    rec = clients_store.add_client("Guard Biz", "general", phone="9000000011")
    today_s = date.today().strftime("%Y-%m-%d")
    _write_queue(
        rec["id"],
        [
            {
                "id": "a1",
                "client_id": rec["id"],
                "date": today_s,
                "type": "post",
                "title": "T",
                "caption": "Aaj ka post — dandruff-free hair offer!",
                "status": "draft",
            },
        ],
    )
    calls: list[str] = []
    _patch_seed_task(monkeypatch, calls)
    _override_customer(app, rec["id"])
    try:
        with TestClient(app) as c:
            resp = c.post("/api/customer/campaigns/generate-first-week")
        body = resp.json()
        assert resp.status_code == 200
        assert body["ok"] is True
        assert body["already"] is True
        assert body["queued"] is False
        assert body["upcoming_items"] >= 1
        assert calls == []  # guard load-bearing: enqueue hua hi nahi
    finally:
        app.dependency_overrides.clear()


def test_empty_queue_enqueues_worker_task(monkeypatch, tmp_path):
    from app.main import app

    _redirect_stores(monkeypatch, tmp_path)
    rec = clients_store.add_client("Fresh Biz", "general", phone="9000000012")
    calls: list[str] = []
    _patch_seed_task(monkeypatch, calls)
    _override_customer(app, rec["id"])
    try:
        with TestClient(app) as c:
            resp = c.post("/api/customer/campaigns/generate-first-week")
        body = resp.json()
        assert resp.status_code == 200
        assert body["ok"] is True
        assert body["queued"] is True
        assert body["already"] is False
        assert calls == [rec["id"]]  # worker task exactly once, sahi client pe
    finally:
        app.dependency_overrides.clear()


def test_upcoming_item_count_counts_only_future_nonskipped(monkeypatch, tmp_path):
    from datetime import date, timedelta

    _redirect_stores(monkeypatch, tmp_path)
    cid = "count-test"
    today = date.today()
    y = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    t = today.strftime("%Y-%m-%d")
    tm = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    _write_queue(
        cid,
        [
            {
                "id": "p1",
                "client_id": cid,
                "date": y,
                "type": "post",
                "status": "draft",
            },  # past → nahi
            {
                "id": "p2",
                "client_id": cid,
                "date": t,
                "type": "poster",
                "status": "skipped",
            },  # skipped → nahi
            {"id": "p3", "client_id": cid, "date": t, "type": "post", "status": "draft"},  # haan
            {
                "id": "p4",
                "client_id": cid,
                "date": tm,
                "type": "reel",
                "status": "approved",
            },  # haan
        ],
    )
    assert auto_content.upcoming_item_count(cid) == 2
    assert auto_content.upcoming_item_count("missing-client") == 0


def test_worker_task_recheck_skips_when_upcoming_exists(monkeypatch):
    """Double-click race: enqueue ke waqt queue khali thi par task chalne tak
    pehla seed complete — task khud guard re-check karke seed skip kare."""
    monkeypatch.setattr(clients_store, "get_client", lambda cid: {"id": cid, "business_name": "X"})
    monkeypatch.setattr(auto_content, "upcoming_item_count", lambda cid: 7)

    def _boom(client):  # seed call hona hi nahi chahiye
        raise AssertionError("seed_client_content called despite upcoming items")

    monkeypatch.setattr(auto_content, "seed_client_content", _boom)
    res = staff_jobs.seed_first_week("cid-race")
    assert res["ok"] is True
    assert res["skipped"] == "already_has_upcoming"
    assert res["upcoming"] == 7


def test_worker_task_seeds_when_queue_empty(monkeypatch):
    monkeypatch.setattr(clients_store, "get_client", lambda cid: {"id": cid, "business_name": "X"})
    monkeypatch.setattr(auto_content, "upcoming_item_count", lambda cid: 0)

    async def _fake_seed(client):
        return 9

    monkeypatch.setattr(auto_content, "seed_client_content", _fake_seed)
    res = staff_jobs.seed_first_week("cid-fresh")
    assert res["ok"] is True
    assert res["items_created"] == 9


def test_worker_task_unknown_client(monkeypatch):
    monkeypatch.setattr(clients_store, "get_client", lambda cid: None)
    res = staff_jobs.seed_first_week("ghost")
    assert res["ok"] is False
