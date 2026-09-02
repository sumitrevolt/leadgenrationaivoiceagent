"""Hermetic tests for app.marketing.content_assurance — read-only content /
approval assurance aggregator.

All external readers (approval store, content queue, social publish queue,
clients store) and the team activity log are monkeypatched, so these tests
touch NO real data files, DB, or network. They verify:
  - stuck-approval detection (approved-not-published + awaiting-client-too-long)
  - stale / empty content-queue detection for paid clients
  - read-only guarantee (write/publish funcs raise -> scan still succeeds AND is
    never called)
  - never-raises (every reader raising -> scan returns a shaped dict, no throw)
  - AgentRunResult-shaped structured output + summary
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.marketing import content_assurance as ca


def _iso_ago(hours: int = 0, days: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours, days=days)).isoformat()


@pytest.fixture
def stub(monkeypatch):
    """Patch every reader to a benign empty default + capture team.log_event.

    Returns a dict the test can mutate to override individual readers before
    calling scan_content_assurance().
    """
    from app.marketing import auto_content, clients_store, content_approval, customer_delivery
    from app.platform import team
    from app.social_engine import store as social_store

    state: dict = {
        "clients": [],
        "approvals": [],
        "queues": {},  # cid -> list[item]
        "jobs": {},  # status -> list[job]
        "events": [],  # captured team.log_event calls
    }

    # --- clients_store: tenant map + paid filter ---------------------------- #
    def fake_list_clients(status=None, product=None):
        return list(state["clients"])

    monkeypatch.setattr(clients_store, "list_clients", fake_list_clients)
    monkeypatch.setattr(clients_store, "canonical_client_id", lambda cid: str(cid or "").strip())
    # all returned clients count as paid (list_clients is the control point)
    monkeypatch.setattr(customer_delivery, "has_paid_evidence", lambda c: True)

    # --- content_approval: approval store ----------------------------------- #
    def fake_list_all(client_id="", limit=100):
        return list(state["approvals"])

    monkeypatch.setattr(content_approval, "list_all", fake_list_all)

    # --- auto_content: per-client content queue ----------------------------- #
    def fake_list_queue(cid, status=None, limit=60):
        return list(state["queues"].get(str(cid), []))

    monkeypatch.setattr(auto_content, "list_queue", fake_list_queue)

    # --- social_engine.store: publish job queue ----------------------------- #
    def fake_list_jobs(client_id="", status="", limit=100):
        return list(state["jobs"].get(str(status), []))

    monkeypatch.setattr(social_store, "list_jobs", fake_list_jobs)

    # --- team.log_event: capture (no DB) ------------------------------------ #
    def fake_log_event(member, action, detail="", status="ok", meta=None):
        state["events"].append(
            {"member": member, "action": action, "detail": detail, "status": status, "meta": meta}
        )

    monkeypatch.setattr(team, "log_event", fake_log_event)

    return state


# --------------------------------------------------------------------------- #
# 1) stuck-approval detection
# --------------------------------------------------------------------------- #
def test_stuck_approval_detection(stub):
    stub["approvals"] = [
        # approved 30h ago (> 24h grace) -> stuck (approved_not_published)
        {
            "id": "a1",
            "client_id": "c1",
            "status": "approved",
            "decided_at": _iso_ago(hours=30),
            "content": {"title": "Diwali post"},
        },
        # pending 60h ago (> 48h threshold) -> stuck (awaiting_client_over_threshold)
        {
            "id": "a2",
            "client_id": "c2",
            "status": "pending",
            "created_at": _iso_ago(hours=60),
            "content": {"title": "Offer post"},
        },
        # published -> terminal, ignored
        {
            "id": "a3",
            "client_id": "c1",
            "status": "published",
            "created_at": _iso_ago(hours=100),
            "content": {"title": "Old"},
        },
        # approved 1h ago (< grace) -> fresh, NOT stuck
        {
            "id": "a4",
            "client_id": "c3",
            "status": "approved",
            "decided_at": _iso_ago(hours=1),
            "content": {"title": "Fresh"},
        },
    ]

    res = ca.scan_content_assurance()

    assert res["status"] == "success"
    assert res["counts"]["stuck_approvals"] == 2
    stuck_issue = next(i for i in res["issues"] if i["type"] == "stuck_approval")
    assert stuck_issue["count"] == 2
    ids = {s["id"] for s in stuck_issue["sample"]}
    assert ids == {"a1", "a2"}
    reasons = {s["reason"] for s in stuck_issue["sample"]}
    assert "approved_not_published" in reasons
    assert "awaiting_client_over_threshold" in reasons


def test_scheduled_time_passed_is_stuck(stub):
    stub["approvals"] = [
        {
            "id": "s1",
            "client_id": "c1",
            "status": "scheduled",
            "decided_at": _iso_ago(hours=200),
            "scheduled_time": _iso_ago(hours=48),
            "content": {"title": "Late schedule"},
        },
    ]
    res = ca.scan_content_assurance()
    assert res["counts"]["stuck_approvals"] == 1
    assert res["issues"][0]["sample"][0]["reason"] == "scheduled_time_passed"


# --------------------------------------------------------------------------- #
# 2) stale / empty content-queue detection
# --------------------------------------------------------------------------- #
def test_stale_queue_detection(stub):
    stub["clients"] = [
        {"id": "c1", "business_name": "Alpha", "plan": "main", "status": "active"},
        {"id": "c2", "business_name": "Beta", "plan": "main", "status": "active"},
        {"id": "c3", "business_name": "Gamma", "plan": "main", "status": "active"},
    ]
    stub["queues"] = {
        "c1": [],  # empty -> flagged
        "c2": [{"id": "x", "created_at": _iso_ago(days=20)}],  # 20d stale (>7) -> flagged
        "c3": [{"id": "y", "created_at": _iso_ago(days=1)}],  # fresh -> NOT flagged
    }

    res = ca.scan_content_assurance()

    assert res["status"] == "success"
    assert res["counts"]["stale_content_queues"] == 2
    stale_issue = next(i for i in res["issues"] if i["type"] == "stale_content_queue")
    flagged = {s["client_id"]: s for s in stale_issue["sample"]}
    assert set(flagged) == {"c1", "c2"}
    assert flagged["c1"]["empty"] is True
    assert flagged["c1"]["reason"] == "empty_queue"
    assert flagged["c2"]["reason"] == "stale_queue"
    assert flagged["c2"]["days_stale"] >= 7
    assert res["counts"]["checked_clients"] == 3


def test_publish_failure_detection(stub):
    stub["jobs"] = {
        "failed": [
            {
                "id": "j1",
                "client_id": "c1",
                "platform": "instagram",
                "status": "failed",
                "attempts": 2,
                "last_error": "token expired",
            }
        ],
        "dead": [
            {
                "id": "j2",
                "client_id": "c2",
                "platform": "facebook",
                "status": "dead",
                "attempts": 4,
                "last_error": "max attempts",
            }
        ],
    }
    res = ca.scan_content_assurance()
    assert res["counts"]["publish_failures"] == 2
    fail_issue = next(i for i in res["issues"] if i["type"] == "publish_failure")
    assert {s["id"] for s in fail_issue["sample"]} == {"j1", "j2"}


# --------------------------------------------------------------------------- #
# 3) read-only guarantee: mutation funcs raise -> scan still succeeds AND the
#    mutation funcs are never called.
# --------------------------------------------------------------------------- #
def test_read_only_guarantee(stub, monkeypatch):
    from app.marketing import auto_content, clients_store, content_approval
    from app.social_engine import store as social_store

    calls: list[str] = []

    def boom(name):
        def _f(*a, **k):
            calls.append(name)
            raise AssertionError(f"content_assurance must not call {name} (read-only)")

        return _f

    for mod, fn in [
        (content_approval, "submit"),
        (content_approval, "approve"),
        (content_approval, "reject"),
        (content_approval, "mark_published"),
        (content_approval, "transition"),
        (auto_content, "mark_item"),
        (auto_content, "enqueue_approved"),
        (social_store, "enqueue"),
        (social_store, "mark"),
        (clients_store, "update_client"),
        (clients_store, "set_status"),
    ]:
        monkeypatch.setattr(mod, fn, boom(f"{mod.__name__}.{fn}"))

    # give it real (readable) data so all three categories actually run
    stub["approvals"] = [
        {"id": "a1", "client_id": "c1", "status": "approved", "decided_at": _iso_ago(hours=48)},
    ]
    stub["clients"] = [{"id": "c1", "business_name": "Alpha", "plan": "main", "status": "active"}]
    stub["queues"] = {"c1": []}
    stub["jobs"] = {"failed": [{"id": "j1", "client_id": "c1", "status": "failed"}]}

    res = ca.scan_content_assurance()

    assert res["status"] == "success"
    assert calls == []  # no mutation function was ever invoked


# --------------------------------------------------------------------------- #
# 4) never-raises: every reader raising -> scan returns shaped dict, no throw
# --------------------------------------------------------------------------- #
def test_never_raises_when_readers_explode(stub, monkeypatch):
    from app.marketing import auto_content, clients_store, content_approval
    from app.social_engine import store as social_store

    def explode(*a, **k):
        raise RuntimeError("reader blew up")

    monkeypatch.setattr(content_approval, "list_all", explode)
    monkeypatch.setattr(auto_content, "list_queue", explode)
    monkeypatch.setattr(social_store, "list_jobs", explode)
    monkeypatch.setattr(clients_store, "list_clients", explode)

    res = ca.scan_content_assurance()  # must not raise

    assert isinstance(res, dict)
    assert res["agent_id"] == "content_assurance"
    assert res["status"] in ("success", "error")
    assert isinstance(res["issues"], list)
    assert isinstance(res["counts"], dict)
    assert res["completed_at"] is not None


# --------------------------------------------------------------------------- #
# 5) structured AgentRunResult shape + summary + observability
# --------------------------------------------------------------------------- #
def test_structured_shape_and_summary(stub):
    stub["approvals"] = [
        {"id": "a1", "client_id": "c1", "status": "approved", "decided_at": _iso_ago(hours=48)},
    ]

    res = ca.scan_content_assurance()

    for key in (
        "run_id",
        "agent_id",
        "domain",
        "lane",
        "status",
        "started_at",
        "completed_at",
        "latency_ms",
        "checked",
        "issues",
        "counts",
        "error",
    ):
        assert key in res, f"missing {key}"
    assert res["agent_id"] == "content_assurance"
    assert res["domain"] == "content_publishing"
    assert res["lane"] == "GREEN"
    assert isinstance(res["latency_ms"], int)
    assert isinstance(res["checked"], int)
    assert isinstance(res["issues"], list)
    for issue in res["issues"]:
        assert set(issue) >= {"type", "count", "sample"}

    # exactly one observability event, under the content owner
    assert len(stub["events"]) == 1
    ev = stub["events"][0]
    assert ev["member"] == "isha"
    assert ev["action"] == "content_assurance_scan"
    assert ev["status"] in ("ok", "warn", "error")

    # summary is a compact, shaped view
    summary = ca.content_assurance_summary()
    for key in (
        "generated_at",
        "status",
        "checked",
        "stuck_approvals",
        "stale_content_queues",
        "publish_failures",
        "issues",
    ):
        assert key in summary, f"summary missing {key}"
    assert summary["stuck_approvals"] == 1


def test_no_voice_imports_in_source():
    """Guard: the module must never IMPORT the voice / telephony stack. Checks
    import lines only (the docstring may legitimately say it is voice-free)."""
    import inspect

    import_lines = "\n".join(
        line for line in inspect.getsource(ca).splitlines() if "import" in line
    ).lower()
    for banned in ("telephony", "voice_agent", "swara", "freeswitch", "app.stt", "app.tts"):
        assert banned not in import_lines, f"content_assurance must not import {banned!r}"
