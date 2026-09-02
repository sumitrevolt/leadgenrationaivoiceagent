"""Per-run job history — read-side of the (previously write-only) job_runs.jsonl.

Covers three fixes that landed together:
  1. `automation_health.record_run` enriched (error_class/error_message/trigger/
     started_at, keyword-only, additive) — old positional callers must still work
     and old-shape records must stay readable.
  2. `automation_health.run_history` — newest-first reader with job/status filters,
     failures-first ordering, limit cap, missing-file → [], never raises.
  3. `team_scheduler._run_job` — threads real failure detail into record_run
     (error_class="job_reported_failure" when inner returns False; exception
     type/message when an exception reaches the wrapper) WITHOUT changing the
     wrapper's never-raise / heartbeat-on-finally behaviour.
  4. `GET /api/platform/team/scheduler/runs` — admin-gated read endpoint.
"""

from __future__ import annotations

import asyncio
import json

import pytest


@pytest.fixture()
def ah(tmp_path, monkeypatch):
    """automation_health with isolated jsonl + snapshot paths (no real data/ writes)."""
    from app.platform import automation_health as _ah

    monkeypatch.setattr(_ah, "_RUNS", lambda: str(tmp_path / "job_runs.jsonl"))
    monkeypatch.setattr(_ah, "_BEATS", lambda: str(tmp_path / "job_heartbeats.json"))
    return _ah


# ---------------------------------------------------------------------------
# 1. record_run — backward-compat + enriched round-trip
# ---------------------------------------------------------------------------


def test_record_run_old_positional_signature_still_works(ah):
    """Old callers `record_run(job, ok, seconds, note)` must not break and must
    write the OLD shape (no enriched keys) so pre-existing records stay readable."""
    ah.record_run("growth", True, 1.5, "all good")
    lines = open(ah._RUNS(), encoding="utf-8").read().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["job"] == "growth" and rec["ok"] is True and rec["s"] == 1.5
    assert rec["note"] == "all good"
    # enriched keys absent when not supplied (old-shape record)
    for k in ("error_class", "error_message", "trigger", "started_at"):
        assert k not in rec


def test_record_run_enriched_round_trip(ah):
    ah.record_run(
        "content",
        False,
        0.4,
        note="engine boom",
        error_class="ValueError",
        error_message="x" * 500,  # must be capped ~300
        trigger="scheduler",
        started_at="2026-07-07T10:00:00+00:00",
    )
    rec = json.loads(open(ah._RUNS(), encoding="utf-8").read().splitlines()[-1])
    assert rec["job"] == "content" and rec["ok"] is False
    assert rec["error_class"] == "ValueError"
    assert rec["trigger"] == "scheduler"
    assert rec["started_at"] == "2026-07-07T10:00:00+00:00"
    assert len(rec["error_message"]) <= 300  # capped
    # snapshot (latest-per-job) also carries the error_class for free
    beats = json.load(open(ah._BEATS(), encoding="utf-8"))
    assert beats["content"]["error_class"] == "ValueError"


def test_record_run_never_raises_on_bad_input(ah):
    # None job / weird seconds — must swallow, not raise
    ah.record_run(None, True, "not-a-number")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 2. run_history — filters, ordering, caps, missing file
# ---------------------------------------------------------------------------


def test_run_history_missing_file_returns_empty(ah):
    assert ah.run_history() == []


def test_run_history_newest_first_and_job_filter(ah):
    ah.record_run("growth", True, 1.0)
    ah.record_run("content", False, 1.0, error_class="ValueError")
    ah.record_run("growth", True, 2.0)

    all_runs = ah.run_history()
    assert len(all_runs) == 3
    # newest-first: last appended row first
    assert all_runs[0]["job"] == "growth" and all_runs[0]["s"] == 2.0

    only_growth = ah.run_history(job="grow")  # substring, case-insensitive
    assert [r["job"] for r in only_growth] == ["growth", "growth"]


def test_run_history_status_failed_filter(ah):
    ah.record_run("a", True, 1.0)
    ah.record_run("b", False, 1.0, error_class="RuntimeError")
    ah.record_run("c", True, 1.0)

    failed = ah.run_history(status="failed")
    assert len(failed) == 1 and failed[0]["job"] == "b"
    ok_only = ah.run_history(status="ok")
    assert {r["job"] for r in ok_only} == {"a", "c"}


def test_run_history_failures_first_ordering(ah):
    # interleave ok/fail; failures_first must surface the failed ones at the top
    ah.record_run("j1", True, 1.0)
    ah.record_run("j2", False, 1.0, error_class="E2")
    ah.record_run("j3", True, 1.0)
    ah.record_run("j4", False, 1.0, error_class="E4")
    ah.record_run("j5", True, 1.0)

    runs = ah.run_history(failures_first=True)
    # first two must be the failed ones (newest-failed first)
    assert runs[0]["ok"] is False and runs[1]["ok"] is False
    assert runs[0]["job"] == "j4" and runs[1]["job"] == "j2"
    # remaining are the ok ones
    assert all(r["ok"] for r in runs[2:])


def test_run_history_limit_capped_at_500(ah):
    for i in range(20):
        ah.record_run(f"job{i}", True, 1.0)
    # limit cap
    assert len(ah.run_history(limit=5)) == 5
    # absurd limit is clamped to <=500 and never raises
    assert len(ah.run_history(limit=10_000)) == 20


# ---------------------------------------------------------------------------
# 3. _run_job wrapper — threads real failure detail, never changes behaviour
# ---------------------------------------------------------------------------


def test_run_job_records_error_class_on_inner_false(monkeypatch):
    from app.platform import automation_health, scheduler_config, team_scheduler

    records: list[dict] = []

    def _fake_record(job, ok=True, seconds=0.0, note="", **kw):
        records.append({"job": job, "ok": ok, "note": note, **kw})

    async def _inner_false(job):
        return False

    monkeypatch.setattr(scheduler_config, "is_enabled", lambda job: True)
    monkeypatch.setattr(team_scheduler, "_run_job_inner", _inner_false)
    monkeypatch.setattr(automation_health, "record_run", _fake_record)

    asyncio.run(team_scheduler._run_job("growth"))

    assert records, "wrapper must always record a heartbeat (finally)"
    last = records[-1]
    assert last["job"] == "growth" and last["ok"] is False
    assert last["error_class"] == "job_reported_failure"
    assert last["trigger"] == "scheduler" and last["started_at"]


def test_run_job_records_exception_detail_on_raise(monkeypatch):
    from app.platform import automation_health, scheduler_config, team_scheduler

    records: list[dict] = []

    def _fake_record(job, ok=True, seconds=0.0, note="", **kw):
        records.append({"job": job, "ok": ok, "note": note, **kw})

    async def _inner_boom(job):
        raise RuntimeError("kaput")

    monkeypatch.setattr(scheduler_config, "is_enabled", lambda job: True)
    monkeypatch.setattr(team_scheduler, "_run_job_inner", _inner_boom)
    monkeypatch.setattr(automation_health, "record_run", _fake_record)

    # wrapper must NOT re-raise (tick's other jobs keep running)
    asyncio.run(team_scheduler._run_job("qa"))

    last = records[-1]
    assert last["ok"] is False
    assert last["error_class"] == "RuntimeError"
    assert last["error_message"] == "kaput"


def test_run_job_success_records_no_error(monkeypatch):
    from app.platform import automation_health, scheduler_config, team_scheduler

    records: list[dict] = []

    def _fake_record(job, ok=True, seconds=0.0, note="", **kw):
        records.append({"job": job, "ok": ok, "note": note, **kw})

    async def _inner_ok(job):
        return True

    monkeypatch.setattr(scheduler_config, "is_enabled", lambda job: True)
    monkeypatch.setattr(team_scheduler, "_run_job_inner", _inner_ok)
    monkeypatch.setattr(automation_health, "record_run", _fake_record)

    asyncio.run(team_scheduler._run_job("blog"))

    last = records[-1]
    assert last["ok"] is True
    assert last.get("error_class", "") == "" and last.get("error_message", "") == ""


# ---------------------------------------------------------------------------
# 4. GET /scheduler/runs endpoint — admin auth + happy path
# ---------------------------------------------------------------------------


def test_scheduler_runs_endpoint_auth_and_happy_path(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.auth_deps import require_admin
    from app.api.team import router
    from app.models.base import get_async_db
    from app.platform import automation_health

    app = FastAPI()
    app.include_router(router, prefix="/api")
    url = "/api/platform/team/scheduler/runs"

    # (a) bina admin/token ke => 401/403 (require_admin -> get_current_user, no creds).
    # get_async_db ko stub karo taaki bare-app me real DB connect na ho.
    async def _fake_db():
        yield None

    app.dependency_overrides[get_async_db] = _fake_db
    client = TestClient(app)
    assert client.get(url).status_code in (401, 403)

    # (b) admin override => happy path; run_history stubbed (module-attr, patchable)
    app.dependency_overrides[require_admin] = lambda: {"username": "admin"}
    monkeypatch.setattr(
        automation_health,
        "run_history",
        lambda job="", status="", limit=100, failures_first=False: [
            {"job": "content", "ok": False, "error_class": "ValueError"}
        ],
    )
    r = client.get(url + "?status=failed&failures_first=true")
    assert r.status_code == 200
    body = r.json()
    assert body["total_returned"] == 1
    assert body["runs"][0]["job"] == "content"
    app.dependency_overrides.clear()
