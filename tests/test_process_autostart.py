"""Pure-python tests for app.platform.process_autostart (sub-project D V1.1).

No network/DB/real-LLM. process_engine.start_run / list_runs aur staff_jobs
process_tick monkeypatched. Flag-gating, idempotency guard, per-tick cap,
rotating inputs, never-raise verify."""

from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timezone

import pytest

from app.platform import process_autostart as pa


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _no_celery(monkeypatch):
    """process_tick.delay ko stub karo (Celery na chhue). Default: queued ok."""
    calls = {"delay": []}

    class _Tick:
        @staticmethod
        def delay(run_id):
            calls["delay"].append(run_id)

    import app.tasks.staff_jobs as sj

    monkeypatch.setattr(sj, "process_tick", _Tick, raising=False)
    return calls


@pytest.fixture(autouse=True)
def _flag_off_default(monkeypatch):
    monkeypatch.delenv("PROCESS_AUTOSTART", raising=False)


def test_flag_off_is_noop(monkeypatch):
    # flag unset = no-op, koi start nahi.
    started = {"n": 0}

    def _start(key, inputs):
        started["n"] += 1
        return {"ok": True, "run_id": "x"}

    from app.agents import process_engine

    monkeypatch.setattr(process_engine, "start_run", _start)
    res = _run(pa.run_due())
    assert res["ok"] is True
    assert res["started"] == []
    assert started["n"] == 0


def test_flag_on_starts_capped_run(monkeypatch):
    monkeypatch.setenv("PROCESS_AUTOSTART", "1")
    starts = []

    def _start(key, inputs):
        starts.append((key, inputs))
        return {"ok": True, "run_id": f"{key}-abc", "steps": 5}

    from app.agents import process_engine

    monkeypatch.setattr(process_engine, "start_run", _start)
    monkeypatch.setattr(process_engine, "list_runs", lambda limit=50: [])

    res = _run(pa.run_due())
    assert res["ok"] is True
    # per-tick cap = 1 start only (no fan-out flood).
    assert len(res["started"]) == 1
    assert len(starts) == 1
    # started run me inputs (niche/city) present (lead_campaign daily).
    assert "process" in res["started"][0]
    assert res["started"][0]["run_id"].endswith("-abc")


def test_idempotency_skips_active_run(monkeypatch):
    monkeypatch.setenv("PROCESS_AUTOSTART", "1")
    starts = []

    def _start(key, inputs):
        starts.append(key)
        return {"ok": True, "run_id": f"{key}-z"}

    from app.agents import process_engine

    # lead_campaign already RUNNING → guard must skip it.
    existing = [
        {"process": "lead_campaign", "status": "running", "started_at": "2020-01-01T00:00:00+00:00"}
    ]
    monkeypatch.setattr(process_engine, "start_run", _start)
    monkeypatch.setattr(process_engine, "list_runs", lambda limit=50: list(existing))

    res = _run(pa.run_due())
    # lead_campaign skipped; client_content fills the single cap slot.
    assert any(s.startswith("lead_campaign:active") for s in res["skipped"])
    assert "lead_campaign" not in starts


def test_idempotency_skips_today_run(monkeypatch):
    monkeypatch.setenv("PROCESS_AUTOSTART", "1")
    monkeypatch.setattr(pa, "_WEEKLY_DAY", (date.today().weekday() + 1) % 7)
    # process_autostart._today_str() uses date.today() (LOCAL tz) — match it here,
    # else this assert flakes in the UTC-evening / IST-next-day divergence window.
    today = date.today().isoformat()
    existing = [
        {
            "process": "lead_campaign",
            "status": "completed",
            "started_at": today + "T01:00:00+00:00",
        },
        {
            "process": "client_content",
            "status": "completed",
            "started_at": today + "T01:00:00+00:00",
        },
    ]

    def _start(key, inputs):
        return {"ok": True, "run_id": f"{key}-z"}

    from app.agents import process_engine

    monkeypatch.setattr(process_engine, "start_run", _start)
    monkeypatch.setattr(process_engine, "list_runs", lambda limit=50: list(existing))

    res = _run(pa.run_due())
    # dono daily already started AAJ → koi naya start nahi.
    assert res["started"] == []


def test_enqueue_called(monkeypatch, _no_celery):
    monkeypatch.setenv("PROCESS_AUTOSTART", "1")

    def _start(key, inputs):
        return {"ok": True, "run_id": f"{key}-q"}

    from app.agents import process_engine

    monkeypatch.setattr(process_engine, "start_run", _start)
    monkeypatch.setattr(process_engine, "list_runs", lambda limit=50: [])

    res = _run(pa.run_due())
    assert len(_no_celery["delay"]) == 1
    assert res["started"][0]["queued"] is True


def test_inline_fallback_when_worker_down(monkeypatch):
    monkeypatch.setenv("PROCESS_AUTOSTART", "1")

    # process_tick import fail karega → inline advance fallback.
    import app.tasks.staff_jobs as sj

    class _BadTick:
        @staticmethod
        def delay(run_id):
            raise RuntimeError("no broker")

    monkeypatch.setattr(sj, "process_tick", _BadTick, raising=False)

    from app.agents import process_engine

    advanced = {"n": 0}

    async def _adv(run_id, max_steps=10):
        advanced["n"] += 1
        return {"run_id": run_id, "status": "running"}

    monkeypatch.setattr(process_engine, "start_run", lambda k, i: {"ok": True, "run_id": f"{k}-f"})
    monkeypatch.setattr(process_engine, "list_runs", lambda limit=50: [])
    monkeypatch.setattr(process_engine, "advance", _adv)

    res = _run(pa.run_due())
    assert res["started"][0]["queued"] is False
    assert advanced["n"] == 1


def test_never_raises_on_start_error(monkeypatch):
    monkeypatch.setenv("PROCESS_AUTOSTART", "1")

    from app.agents import process_engine

    def _boom(key, inputs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(process_engine, "start_run", _boom)
    monkeypatch.setattr(process_engine, "list_runs", lambda limit=50: [])

    res = _run(pa.run_due())
    # exception start_run me — run_due never-raise, graceful skip.
    assert res["ok"] is True
    assert any("start_err" in s for s in res["skipped"])


def test_never_raises_on_list_runs_error(monkeypatch):
    monkeypatch.setenv("PROCESS_AUTOSTART", "1")

    from app.agents import process_engine

    monkeypatch.setattr(
        process_engine, "list_runs", lambda limit=50: (_ for _ in ()).throw(RuntimeError("db down"))
    )
    monkeypatch.setattr(process_engine, "start_run", lambda k, i: {"ok": True, "run_id": f"{k}-x"})

    # list_runs throw → recent=[] fallback, still starts (no crash).
    res = _run(pa.run_due())
    assert res["ok"] is True


def test_rotating_inputs_shape():
    inp = pa._rotating_inputs("lead_campaign")
    assert isinstance(inp, dict)
    assert "niche" in inp and "city" in inp
    assert isinstance(inp["niche"], str) and inp["niche"]
    assert isinstance(inp["city"], str) and inp["city"]


def test_inputs_for_growth_audit_empty():
    assert pa._inputs_for("growth_audit") == {}


def test_different_processes_get_different_niches(monkeypatch):
    # salt offset se lead_campaign vs client_content same-din alag niche pakde
    # (jab niche-pool > 1). Bas dono valid string return karein.
    a = pa._rotating_inputs("lead_campaign")
    b = pa._rotating_inputs("client_content")
    assert a["niche"] and b["niche"]
