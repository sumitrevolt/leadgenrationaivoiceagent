"""Tests: email-outreach last-run summaries (app/platform/auto_outreach.py).

ISSUE-11: scheduler email_outreach ka run-outcome (sent/failed/cap/...) ab
Schedule tab me dikhta hai. Data already AgentEvent meta me hota hai
(_log_event -> team.log_event) — humaara function sirf filtered read karta hai,
koi naya persistence nahi. Hermetic: team.recent_events monkeypatch se stub,
koi DB / network nahi."""

from app.platform import auto_outreach


def _fake_events():
    # recent_events() newest-first returns karta hai (created_at desc)
    return [
        {
            "at": "2026-08-02T06:31:00+00:00",
            "action": "email_followup_run",
            "status": "ok",
            "detail": "20 follow-ups bheje",
            "meta": {"sent": 20, "failed": 0, "cap": 50, "by_step": {"1": 15, "2": 5}},
        },
        {
            "at": "2026-08-02T06:30:00+00:00",
            "action": "email_outreach_run",
            "status": "ok",
            "detail": "19 emails bheje, 0 fail, cap 50",
            "meta": {"sent": 19, "failed": 0, "cap": 50, "skipped_no_email": 12},
        },
        {
            "at": "2026-08-01T06:30:00+00:00",
            "action": "some_other_event",
            "status": "ok",
            "detail": "ignore me",
            "meta": {},
        },
    ]


def test_last_run_summaries_filters_and_normalizes(monkeypatch):
    from app.platform import team

    monkeypatch.setattr(team, "recent_events", lambda limit=400: list(_fake_events()))

    runs = auto_outreach.last_run_summaries(limit=5)

    assert len(runs) == 2
    assert runs[0]["kind"] == "email_followup_run"
    assert runs[0]["meta"]["sent"] == 20
    assert runs[0]["at"] == "2026-08-02T06:31:00+00:00"
    assert runs[1]["kind"] == "email_outreach_run"
    assert runs[1]["meta"]["skipped_no_email"] == 12
    assert runs[1]["summary"] == "19 emails bheje, 0 fail, cap 50"


def test_last_run_summaries_respects_limit(monkeypatch):
    from app.platform import team

    monkeypatch.setattr(team, "recent_events", lambda limit=400: list(_fake_events()))

    runs = auto_outreach.last_run_summaries(limit=1)
    assert len(runs) == 1
    assert runs[0]["kind"] == "email_followup_run"


def test_last_run_summaries_empty_when_no_matching_events(monkeypatch):
    from app.platform import team

    monkeypatch.setattr(
        team,
        "recent_events",
        lambda limit=400: [{"action": "qa_run", "at": "2026-08-01T00:00:00+00:00"}],
    )

    assert auto_outreach.last_run_summaries(limit=5) == []


def test_last_run_summaries_never_raises_on_team_failure(monkeypatch):
    from app.platform import team

    def _boom(limit=400):
        raise RuntimeError("db down")

    monkeypatch.setattr(team, "recent_events", _boom)

    assert auto_outreach.last_run_summaries(limit=5) == []


def test_email_outreach_runs_endpoint(monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.auth_deps import require_admin
    from app.main import app

    app.dependency_overrides[require_admin] = lambda: {"username": "test"}
    fake = [
        {
            "at": "2026-08-02T06:30:00+00:00",
            "kind": "email_outreach_run",
            "status": "ok",
            "summary": "19 emails bheje, 0 fail, cap 50",
            "meta": {"sent": 19, "failed": 0, "cap": 50},
        }
    ]
    monkeypatch.setattr(auto_outreach, "last_run_summaries", lambda limit=5: list(fake))

    try:
        with TestClient(app) as c:
            resp = c.get("/api/platform/team/email-outreach/runs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_returned"] == 1
        assert body["runs"][0]["meta"]["sent"] == 19
        assert body["runs"][0]["kind"] == "email_outreach_run"
    finally:
        app.dependency_overrides.clear()
