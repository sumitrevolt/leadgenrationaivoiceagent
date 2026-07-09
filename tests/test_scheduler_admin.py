"""Agent Scheduler (scheduler_config) — admin toggle + run-due contract.

Pins:
- FAIL-OPEN default: bina override file ke har job enabled.
- set_enabled persist + unknown-job reject.
- team_scheduler._run_job gate: admin-paused job _run_job_inner ko call NAHI
  karta, heartbeat "admin_paused" note ke saath record hota (dead-man silent).
- run_due: RUN_DUE_EXCLUDE (outbound jobs) kabhi auto-recover nahi + disabled skip.
- /scheduler/run-due endpoint: secret unset = 503 fail-CLOSED, galat token = 401.
"""

from __future__ import annotations

import asyncio
import importlib
from typing import Any

import pytest


@pytest.fixture()
def sc(tmp_path, monkeypatch):
    from app.platform import scheduler_config

    importlib.reload(scheduler_config)
    monkeypatch.setattr(scheduler_config, "_OVERRIDES", str(tmp_path / "scheduler_overrides.json"))
    return scheduler_config


def test_default_enabled_fail_open(sc):
    assert sc.is_enabled("growth") is True
    assert sc.is_enabled("qa") is True
    # unknown job bhi FAIL-OPEN (gate kabhi legitimate run block na kare)
    assert sc.is_enabled("does_not_exist") is True


def test_set_enabled_persists_and_rejects_unknown(sc):
    res = sc.set_enabled("blog", False, by="tester")
    assert res["ok"] is True and res["enabled"] is False
    assert sc.is_enabled("blog") is False
    # wapas ON
    assert sc.set_enabled("blog", True)["ok"] is True
    assert sc.is_enabled("blog") is True
    # unknown reject
    assert sc.set_enabled("nope_job", False)["ok"] is False


def test_list_jobs_marks_admin_paused(sc, monkeypatch):
    from app.platform import automation_health

    monkeypatch.setattr(automation_health, "health", lambda: {"status": "healthy", "jobs": []})
    sc.set_enabled("content", False, by="tester")
    out = sc.list_jobs()
    by_job = {j["job"]: j for j in out["jobs"]}
    assert by_job["content"]["enabled"] is False
    assert by_job["content"]["status"] == "admin_paused"
    assert by_job["growth"]["enabled"] is True
    # registry metadata present (UI contract)
    assert by_job["growth"]["cadence"] and by_job["growth"]["label"]


def test_run_job_gate_skips_paused(sc, monkeypatch):
    from app.platform import automation_health, team_scheduler

    calls: list[str] = []
    beats: list[dict[str, Any]] = []
    logs: list[dict[str, Any]] = []

    async def _fake_inner(job: str) -> None:
        calls.append(job)

    def _fake_record(job, ok=True, seconds=0.0, note=""):
        beats.append({"job": job, "ok": ok, "note": note})

    def _fake_log_event(**kw):
        logs.append(kw)
        return f"log-{len(logs)}"

    monkeypatch.setattr(team_scheduler, "_run_job_inner", _fake_inner)
    monkeypatch.setattr(automation_health, "record_run", _fake_record)
    monkeypatch.setattr("app.platform.automation_log_service.log_event", _fake_log_event)

    sc.set_enabled("digest", False, by="tester")
    asyncio.run(team_scheduler._run_job("digest"))
    assert calls == []  # inner skip
    assert beats and beats[-1]["note"] == "admin_paused" and beats[-1]["ok"] is True
    assert [l["status"] for l in logs] == ["skipped"]
    assert logs[-1]["meta_json"] == {"phase": "skipped", "reason": "admin_paused"}

    # enabled job normal chalta hai
    asyncio.run(team_scheduler._run_job("growth"))
    assert calls == ["growth"]
    assert [l["status"] for l in logs] == ["skipped", "running", "success"]
    assert logs[-2]["meta_json"] == {"phase": "start"}
    assert logs[-1]["meta_json"] == {"phase": "finish", "start_log_id": "log-2"}


def test_run_due_excludes_outbound_and_disabled(sc, monkeypatch):
    from app.platform import automation_health

    monkeypatch.setattr(
        automation_health,
        "health",
        lambda: {"overdue": ["qa", "email_outreach", "platform_dial", "blog"], "never_ran": []},
    )
    dispatched: list[str] = []
    monkeypatch.setattr(sc, "_dispatch", lambda j: (dispatched.append(j), "celery")[1])
    sc.set_enabled("blog", False, by="tester")

    out = sc.run_due(max_jobs=5)
    assert out["ok"] is True
    assert dispatched == ["qa"]  # outbound excluded, blog disabled
    assert set(out["skipped_excluded"]) == {"email_outreach", "platform_dial"}


def test_run_due_endpoint_auth(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.team import router

    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)
    url = "/api/platform/team/scheduler/run-due"

    # secret unset => 503 fail-CLOSED
    monkeypatch.delenv("LEADGEN_SCHEDULER_SECRET", raising=False)
    assert client.post(url).status_code == 503

    # galat token => 401
    monkeypatch.setenv("LEADGEN_SCHEDULER_SECRET", "s3cret-token")
    assert client.post(url, headers={"Authorization": "Bearer wrong"}).status_code == 401

    # sahi token => 200 (run_due stubbed — koi real dispatch nahi)
    from app.platform import scheduler_config

    monkeypatch.setattr(scheduler_config, "run_due", lambda max_jobs=3: {"ok": True, "due": []})
    r = client.post(url, headers={"Authorization": "Bearer s3cret-token"})
    assert r.status_code == 200 and r.json()["ok"] is True
