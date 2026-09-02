"""Unit tests for the customer "Aapka Office" virtual-office aggregator
(app/api/customer_dashboard_builders.py). Direct builder calls — no app/auth/DB
so they stay fast and deterministic offline."""

from app.api.customer_dashboard_builders import (
    _build_office,
    _office_tasks,
    _rel_time,
)
from app.api.customer_dashboard_models import OnboardingChecklist, OnboardingStep


def _onboarding(done_ids: set[str]) -> OnboardingChecklist:
    ids = ["login", "profile", "setup", "minisite", "content", "leads"]
    steps = [OnboardingStep(id=i, label=i, done=(i in done_ids), hint="") for i in ids]
    done = sum(1 for s in steps if s.done)
    return OnboardingChecklist(
        steps=steps,
        done=done,
        total=len(steps),
        pct=round(done / len(steps) * 100, 1),
        complete=done >= len(steps),
    )


def test_rel_time_buckets():
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    assert _rel_time(now) == "abhi"
    assert "min pehle" in _rel_time(now - timedelta(minutes=10))
    assert "ghante" in _rel_time(now - timedelta(hours=3))
    assert _rel_time(now - timedelta(days=1)) == "kal"
    assert _rel_time(None) == ""


def test_every_task_has_impact_and_severity():
    """Core promise: har manual task me 'why' + automation-impact + severity ho."""
    ob = _onboarding(set())  # nothing done -> max tasks
    tasks = _office_tasks(
        {"plan": "trial"},
        "combo",
        ob,
        approvals_pending=2,
        trial=None,
        routing_set=False,
        hot_leads=3,
    )
    assert tasks, "combo with empty onboarding should yield tasks"
    for t in tasks:
        assert t.get("title") and t.get("why") and t.get("impact"), t
        assert t.get("severity") in ("high", "medium", "low"), t
        assert t.get("cta_target"), t
    # sorted: first task severity must be 'high' when high tasks exist
    assert tasks[0]["severity"] == "high"


def test_product_aware_marketing_vs_voice():
    ob = _onboarding({"login", "profile", "setup"})  # mid setup
    mkt = _office_tasks({}, "marketing", ob, 2, None, False, 0)
    voice = _office_tasks({}, "voice", ob, 2, None, False, 4)
    mkt_ids = {t["id"] for t in mkt}
    voice_ids = {t["id"] for t in voice}
    # marketing-only tasks
    assert "approvals" in mkt_ids and "minisite" in mkt_ids
    assert "approvals" not in voice_ids and "minisite" not in voice_ids
    # voice-only tasks
    assert "routing" in voice_ids and "hotleads" in voice_ids
    assert "routing" not in mkt_ids and "hotleads" not in mkt_ids


def test_no_tasks_when_all_done():
    ob = _onboarding({"login", "profile", "setup", "minisite", "content", "leads"})
    tasks = _office_tasks({}, "marketing", ob, 0, None, True, 0)
    assert tasks == []


def test_build_office_never_raises_and_shape():
    o = _build_office("does-not-exist-client-xyz")
    assert isinstance(o, dict)
    for k in (
        "ok",
        "enabled",
        "product",
        "headline",
        "next_best_action",
        "your_tasks",
        "activity",
        "summary",
    ):
        assert k in o, k
    assert o["product"] in ("marketing", "voice", "combo")
    assert isinstance(o["your_tasks"], list)
    assert isinstance(o["activity"], list)
    # proof-of-work fields present with honest zeros for a client with no data
    for k in (
        "posts_ready",
        "approvals_pending",
        "new_leads",
        "hot_leads",
        "calls_completed",
        "bookings",
    ):
        assert k in o["summary"], k
        assert o["summary"][k] == 0


def test_build_office_next_best_action_reflects_top_task():
    """next_best_action must be the same task '_office_tasks' ranks first (single
    clearest CTA for the top-of-page proof-of-work section), not a separate guess."""
    o = _build_office("does-not-exist-client-xyz")
    if o["your_tasks"]:
        assert o["next_best_action"]["title"] == o["your_tasks"][0]["title"]
        assert o["next_best_action"]["cta_target"] == o["your_tasks"][0]["cta_target"]
    else:
        assert o["next_best_action"]["cta_target"] == ""


# --------------------------------------------------------------------------- #
# _office_call_stats — client-scoped calls/bookings (2026-07-01, Phase 4).
# Uses a dedicated in-memory SQLite bound directly into app.models.base so the
# query really executes (not mocked) — this is the exact regression the fix
# targets: the OLD _calls_from_events helper counted ALL clients' calls
# platform-wide, so two different clients would see the SAME number under
# their own name. These tests assert that can never happen again.
# --------------------------------------------------------------------------- #
def _office_db(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.models.base as base_mod

    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    TestSession = sessionmaker(bind=test_engine)
    base_mod.Base.metadata.create_all(bind=test_engine)
    monkeypatch.setattr(base_mod, "_engine", test_engine)
    monkeypatch.setattr(base_mod, "_SessionLocal", TestSession)
    return TestSession


def test_office_call_stats_no_cross_client_leakage(monkeypatch):
    from app.models.call_log import CallLog
    from app.models.lead import Lead, LeadStatus

    TestSession = _office_db(monkeypatch)
    session = TestSession()
    try:
        session.add_all(
            [
                CallLog(
                    id="call_a1", client_id="client_a", duration_seconds=90, to_number="9990000001"
                ),
                CallLog(
                    id="call_a2", client_id="client_a", duration_seconds=0, to_number="9990000002"
                ),
                CallLog(
                    id="call_b1", client_id="client_b", duration_seconds=60, to_number="9990000003"
                ),
                CallLog(
                    id="call_b2", client_id="client_b", duration_seconds=45, to_number="9990000004"
                ),
                Lead(
                    id="lead_a1",
                    company_name="A Biz",
                    phone="9990000001",
                    assigned_to="client_a",
                    status=LeadStatus.APPOINTMENT,
                ),
                Lead(
                    id="lead_b1",
                    company_name="B Biz",
                    phone="9990000003",
                    assigned_to="client_b",
                    status=LeadStatus.NEW,
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    from app.api.customer_dashboard_builders import _office_call_stats

    calls_a, bookings_a = _office_call_stats("client_a")
    calls_b, bookings_b = _office_call_stats("client_b")
    calls_c, bookings_c = _office_call_stats("client_c_no_data")

    # client_a: 1 connected call (duration>0), 1 appointment booking
    assert calls_a == 1 and bookings_a == 1
    # client_b: 2 connected calls, 0 bookings (lead is NEW not APPOINTMENT) —
    # must NOT inherit client_a's numbers, and vice versa.
    assert calls_b == 2 and bookings_b == 0
    # a client with zero rows gets an honest zero, never someone else's total.
    assert calls_c == 0 and bookings_c == 0


def test_office_call_stats_never_raises_when_db_unavailable(monkeypatch):
    import app.models.base as base_mod

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(base_mod, "_get_sync_engine", _boom)
    monkeypatch.setattr(base_mod, "_SessionLocal", None)

    from app.api.customer_dashboard_builders import _office_call_stats

    assert _office_call_stats("any-client") == (0, 0)


# --------------------------------------------------------------------------- #
# _calls_from_events — client-scoped via meta_json.client_id (2026-07-02).
# The old version counted ALL "swara" call events platform-wide (client_id
# wasn't in meta yet); every customer's file-based dashboard fallback showed
# the SAME inflated number under their own name. Now scoped by the client_id
# now written at the source (vobiz_stream.py / telephony_vobiz.py /
# public_site._auto_callback — see tests/test_call_event_client_id.py).
# --------------------------------------------------------------------------- #
def test_calls_from_events_no_cross_client_leakage(monkeypatch):
    import json

    from app.models.agent_event import AgentEvent

    TestSession = _office_db(monkeypatch)
    session = TestSession()
    try:
        session.add_all(
            [
                AgentEvent(
                    id="ev1",
                    member="swara",
                    action="call_finished",
                    status="ok",
                    meta_json=json.dumps({"client_id": "client_a"}),
                ),
                AgentEvent(
                    id="ev2",
                    member="swara",
                    action="call_placed",
                    status="ok",
                    meta_json=json.dumps({"client_id": "client_a"}),
                ),
                AgentEvent(
                    id="ev3",
                    member="swara",
                    action="auto_callback",
                    status="ok",
                    meta_json=json.dumps({"client_id": "client_b"}),
                ),
                # pre-fix event with no client_id in meta — must NOT count toward
                # anyone (honest exclusion, not attributed to the wrong client).
                AgentEvent(
                    id="ev4",
                    member="swara",
                    action="call_finished",
                    status="ok",
                    meta_json=json.dumps({"duration_s": 12.0}),
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    from app.api.customer_dashboard_builders import _calls_from_events

    calls_a, connected_a, _ = _calls_from_events("client_a", None)
    calls_b, connected_b, _ = _calls_from_events("client_b", None)
    calls_none, connected_none, _ = _calls_from_events("client_unknown", None)

    assert connected_a == 2  # ev1 + ev2, not ev3/ev4
    assert connected_b == 1  # ev3 only
    assert connected_none == 0
    assert calls_a == [] and calls_b == []  # detail rows intentionally empty


def test_calls_from_events_scoped_filter_survives_high_platform_volume(monkeypatch):
    """Regression: an earlier version fetched the latest N=2000 events
    PLATFORM-WIDE and filtered by client_id in Python afterwards — once total
    call volume outpaced that window, a real client's own (older) calls fell
    outside it and silently read as 0. The fix pushes the client_id match into
    the SQL WHERE (meta_json LIKE) before any row limit is applied. Proven
    here by burying our client's one call under >5000 newer noise rows from
    other clients — it must still be found."""
    import json

    from app.models.agent_event import AgentEvent

    TestSession = _office_db(monkeypatch)
    session = TestSession()
    try:
        session.add(
            AgentEvent(
                id="ev_target",
                member="swara",
                action="call_finished",
                status="ok",
                meta_json=json.dumps({"client_id": "client_needle"}),
            )
        )
        session.commit()
        # >5000 noise rows for OTHER clients, all created after ours.
        noise = [
            {
                "id": f"noise_{i}",
                "member": "swara",
                "action": "call_finished",
                "status": "ok",
                "meta_json": json.dumps({"client_id": f"client_noise_{i}"}),
            }
            for i in range(5010)
        ]
        session.bulk_insert_mappings(AgentEvent, noise)
        session.commit()
    finally:
        session.close()

    from app.api.customer_dashboard_builders import _calls_from_events

    _, connected, _ = _calls_from_events("client_needle", None)
    assert connected == 1
    # a client with no rows at all still gets an honest zero, not a crash
    _, connected_none, _ = _calls_from_events("client_totally_absent", None)
    assert connected_none == 0


def test_calls_from_events_empty_client_id_returns_zero_without_query(monkeypatch):
    from app.api.customer_dashboard_builders import _calls_from_events

    # No DB patch at all — if this queried the DB it would hit the real (or
    # unconfigured) engine; the empty-client_id short-circuit must prevent that.
    assert _calls_from_events("", None) == ([], 0, 0)


def test_calls_from_events_never_raises_when_db_unavailable(monkeypatch):
    import app.models.base as base_mod

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(base_mod, "_get_sync_engine", _boom)
    monkeypatch.setattr(base_mod, "_SessionLocal", None)

    from app.api.customer_dashboard_builders import _calls_from_events

    assert _calls_from_events("some-client", None) == ([], 0, 0)
