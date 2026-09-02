"""Contract tests — Goal Hierarchy (Paperclip ADOPT #1).

Covers: module CRUD + status lifecycle + parent linkage + task linking +
reverse lookup, and the /api/goals admin-gated router surface.

DB pattern (repo standard): tmp sqlite engine + monkeypatched
``app.models.base.get_db_session`` (same as tests/test_memory_dispatch_idempotency.py).
Sync tests run async module fns via ``asyncio.run`` (tests/test_2026_features.py
convention) — no pytest-asyncio dependency.
"""

import asyncio
import json
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.agent_goal import AgentGoal
from app.platform import goals as goals_mod


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    """One sqlite file shared by module + API tests (same authority)."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'goals.db'}",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    AgentGoal.__table__.create(bind=engine, checkfirst=True)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def _session():
        db = Session()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    import app.models.base as base

    monkeypatch.setattr(base, "get_db_session", _session)

    yield type("W", (), {"session": staticmethod(_session)})
    engine.dispose()


def test_create_goal_roundtrip(wired):
    g = asyncio.run(
        goals_mod.create_goal(
            "Onboard 2 naye paid customers",
            level="company",
            description="GTM 0→1 — jiya makeover ke baad 2 aur",
            target_metric="2 customers/quarter",
        )
    )
    assert g["ok"] is True
    assert g["level"] == "company"
    assert g["status"] == "planned"
    assert g["target_metric"] == "2 customers/quarter"
    assert g["linked_task_ids"] == []
    assert g["achieved_at"] is None

    got = asyncio.run(goals_mod.get_goal(g["id"]))
    assert got is not None
    assert got["title"] == "Onboard 2 naye paid customers"


def test_create_goal_validation(wired):
    bad = asyncio.run(goals_mod.create_goal("   "))
    assert bad["ok"] is False
    assert "title" in bad["error"]

    bad_level = asyncio.run(goals_mod.create_goal("x", level="galaxy"))
    assert bad_level["ok"] is False
    assert "level" in bad_level["error"]

    bad_status = asyncio.run(goals_mod.create_goal("x", status="warp"))
    assert bad_status["ok"] is False
    assert "status" in bad_status["error"]

    orphan = asyncio.run(goals_mod.create_goal("x", parent_goal_id="does-not-exist"))
    assert orphan["ok"] is False
    assert "parent" in orphan["error"]


def test_status_lifecycle_forward_only(wired):
    g = asyncio.run(goals_mod.create_goal("Q3 marketing goal", level="team"))
    assert g["status"] == "planned"

    out = asyncio.run(goals_mod.update_goal(g["id"], status="active"))
    assert out["ok"] is True and out["status"] == "active"

    out = asyncio.run(goals_mod.update_goal(g["id"], status="achieved"))
    assert out["ok"] is True and out["status"] == "achieved"
    assert out["achieved_at"] is not None

    # achieved is terminal
    out = asyncio.run(goals_mod.update_goal(g["id"], status="active"))
    assert out["ok"] is False
    assert "cannot move" in out["error"]

    out = asyncio.run(goals_mod.update_goal(g["id"], status="cancelled"))
    assert out["ok"] is False


def test_parent_linkage(wired):
    parent = asyncio.run(goals_mod.create_goal("Company goal", level="company"))
    child = asyncio.run(
        goals_mod.create_goal("Team goal", level="team", parent_goal_id=parent["id"])
    )
    assert child["ok"] is True
    assert child["parent_goal_id"] == parent["id"]

    rows = asyncio.run(goals_mod.list_goals(parent_goal_id=parent["id"]))
    assert any(r["id"] == child["id"] for r in rows)


def test_link_task_dedupe_and_relink(wired):
    g1 = asyncio.run(goals_mod.create_goal("Goal A"))
    g2 = asyncio.run(goals_mod.create_goal("Goal B"))

    out = asyncio.run(goals_mod.link_task(g1["id"], "task-111"))
    assert out["ok"] is True and out["already"] is False

    # dedupe
    out = asyncio.run(goals_mod.link_task(g1["id"], "task-111"))
    assert out["ok"] is True and out["already"] is True

    # relink to g2 moves the task (one "why" per task)
    out = asyncio.run(goals_mod.link_task(g2["id"], "task-111"))
    assert out["ok"] is True

    got1 = asyncio.run(goals_mod.get_goal(g1["id"]))
    got2 = asyncio.run(goals_mod.get_goal(g2["id"]))
    assert "task-111" not in got1["linked_task_ids"]
    assert "task-111" in got2["linked_task_ids"]

    # reverse lookup
    found = asyncio.run(goals_mod.task_goal_lookup("task-111"))
    assert found is not None and found["id"] == g2["id"]


def test_progress_notes_append(wired):
    g = asyncio.run(goals_mod.create_goal("Note goal"))
    out = asyncio.run(goals_mod.add_progress_note(g["id"], "pehla update"))
    assert out["ok"] is True
    out = asyncio.run(goals_mod.add_progress_note(g["id"], "dusra update"))
    assert out["ok"] is True
    notes = out["progress_notes"]
    assert "pehla update" in notes and "dusra update" in notes
    assert notes.index("pehla update") < notes.index("dusra update")


def test_list_filters_and_client_isolation(wired):
    a = asyncio.run(goals_mod.create_goal("Client A goal", level="agent", client_id="c-a"))
    asyncio.run(goals_mod.create_goal("Client B goal", level="agent", client_id="c-b"))
    asyncio.run(goals_mod.create_goal("Free goal", level="company"))

    rows = asyncio.run(goals_mod.list_goals(client_id="c-a"))
    assert len(rows) == 1 and rows[0]["id"] == a["id"]

    rows = asyncio.run(goals_mod.list_goals(level="company", status="planned"))
    assert len(rows) == 1 and rows[0]["title"] == "Free goal"


def test_model_to_dict_linked_json(wired):
    """Model-level JSON column roundtrip stays valid after DB commit/refresh."""
    g = asyncio.run(goals_mod.create_goal("JSON goal"))
    asyncio.run(goals_mod.link_task(g["id"], "t-1"))
    with wired.session() as db:
        row = db.query(AgentGoal).filter(AgentGoal.id == g["id"]).first()
        assert json.loads(row.linked_task_ids) == ["t-1"]
        d = row.to_dict()
        assert d["linked_task_ids"] == ["t-1"]
        assert d["status"] == "planned"


def test_router_mounted_admin_gated(wired):
    """/api/goals CRUD surface works via TestClient (conftest globally mocks
    require_admin → authenticated admin)."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        # list
        r = c.get("/api/goals")
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # create
        r = c.post("/api/goals", json={"title": "API goal", "level": "team"})
        assert r.status_code == 200, r.text
        gid = r.json()["id"]

        # get
        r = c.get(f"/api/goals/{gid}")
        assert r.status_code == 200 and r.json()["goal"]["id"] == gid

        # patch status
        r = c.patch(f"/api/goals/{gid}", json={"status": "active"})
        assert r.status_code == 200 and r.json()["status"] == "active"

        # invalid status → 400
        r = c.patch(f"/api/goals/{gid}", json={"status": "warp"})
        assert r.status_code == 400

        # link task
        r = c.post(f"/api/goals/{gid}/tasks", json={"task_id": "task-abc"})
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # unknown goal → 404
        r = c.get("/api/goals/nope")
        assert r.status_code == 404


def test_goals_router_no_duplicate_routes():
    """First-route-wins guard: /api/goals must be registered EXACTLY once."""
    from app.main import app

    def _collect(routes, out):
        for r in routes:
            path = getattr(r, "path", None)
            if path and path.startswith("/api/goals"):
                out.append(path)
            # FastAPI >=0.115 lazy _IncludedRouter wrapper: descend into it,
            # re-adding the include prefix to inner (prefix-stripped) paths
            # (same handling as app/main.py's _first_path).
            wrapped = getattr(r, "original_router", None)
            if wrapped is not None:
                ctx = getattr(r, "include_context", None)
                prefix = getattr(ctx, "prefix", "") if ctx is not None else ""
                for x in getattr(wrapped, "routes", None) or []:
                    p = getattr(x, "path", None)
                    if p and (prefix + p).startswith("/api/goals"):
                        out.append(prefix + p)

    paths: list = []
    _collect(getattr(app, "routes", None) or [], paths)
    # 5 routes: GET list, POST create, GET {id}, PATCH {id}, POST {id}/tasks
    assert len(paths) == 5, paths
