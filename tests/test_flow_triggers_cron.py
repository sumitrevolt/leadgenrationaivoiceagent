from datetime import datetime

import app.automation.flow_store as fs
from app.automation import flow_triggers

_IST = flow_triggers._IST


def _now(h, m, y=2026, mo=6, d=20):
    return datetime(y, mo, d, h, m, tzinfo=_IST)


# ---------------- _cron_due unit matrix ----------------


def test_hhmm_fires_its_slot_once_daily():
    t = {"type": "cron", "cron": "09:30"}
    assert flow_triggers._cron_due(t, _now(9, 30)) == "2026-06-20"
    assert flow_triggers._cron_due(t, _now(9, 33)) == "2026-06-20"  # same 30-35 slot
    assert flow_triggers._cron_due(t, _now(10, 0)) is None
    assert flow_triggers._cron_due(t, _now(9, 36)) is None  # next slot


def test_interval_cron_aligned_slots_only():
    t = {"type": "cron", "cron": "*/15 * * * *"}
    assert (flow_triggers._cron_due(t, _now(0, 0)) or "").endswith("00:00")
    assert (flow_triggers._cron_due(t, _now(0, 15)) or "").endswith("00:15")
    assert flow_triggers._cron_due(t, _now(0, 5)) is None  # slot 5 has no */15 minute
    assert (flow_triggers._cron_due(t, _now(0, 30)) or "").endswith("00:30")


def test_star_minute_every_slot():
    t = {"type": "cron", "cron": "* * * * *"}
    assert flow_triggers._cron_due(t, _now(3, 7)) is not None  # slot 5


def test_comma_hour_list():
    t = {"type": "cron", "cron": "0 9,17 * * *"}
    assert flow_triggers._cron_due(t, _now(9, 0)) is not None
    assert flow_triggers._cron_due(t, _now(17, 0)) is not None
    assert flow_triggers._cron_due(t, _now(10, 0)) is None


def test_unparseable_inert():
    assert flow_triggers._cron_due({"type": "cron", "cron": "garbage cron x"}, _now(9, 0)) is None
    assert flow_triggers._cron_due({"type": "cron", "cron": ""}, _now(9, 0)) is None


# ---------------- run_cron_due integration ----------------


def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_DIR", str(tmp_path / "fr"))
    monkeypatch.setattr(fs, "_PATH", str(tmp_path / "fr" / "flows.jsonl"))
    monkeypatch.setattr(flow_triggers, "_STATE", str(tmp_path / "fr" / "cron_state.json"))


def test_run_cron_due_fires_then_dedupes(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    monkeypatch.setenv("FLOW_RUNNER", "1")
    monkeypatch.setenv("FLOW_AUTO_TRIGGERS", "1")
    calls = []
    monkeypatch.setattr(flow_triggers, "_fire", lambda fid, inp: calls.append(fid) or True)
    fs.save_flow(
        {
            "id": "cronf",
            "name": "c",
            "nodes": [{"id": "a", "action": "scrape"}],
            "edges": [],
            "trigger": {"type": "cron", "cron": "* * * * *"},
        }
    )
    r1 = flow_triggers.run_cron_due(now=_now(9, 0))
    assert r1["started"] == 1 and calls == ["cronf"]
    r2 = flow_triggers.run_cron_due(now=_now(9, 0))  # same slot -> dedupe
    assert r2["started"] == 0 and calls == ["cronf"]


def test_run_cron_gated_off(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    monkeypatch.setenv("FLOW_RUNNER", "1")
    monkeypatch.delenv("FLOW_AUTO_TRIGGERS", raising=False)
    called = []
    monkeypatch.setattr(flow_triggers, "_fire", lambda fid, inp: called.append(fid))
    fs.save_flow(
        {
            "id": "c2",
            "name": "c",
            "nodes": [{"id": "a", "action": "scrape"}],
            "edges": [],
            "trigger": {"type": "cron", "cron": "* * * * *"},
        }
    )
    r = flow_triggers.run_cron_due(now=_now(9, 0))
    assert r.get("skipped") == "gated" and called == []


def test_max_starts_per_tick_cap(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    monkeypatch.setenv("FLOW_RUNNER", "1")
    monkeypatch.setenv("FLOW_AUTO_TRIGGERS", "1")
    calls = []
    monkeypatch.setattr(flow_triggers, "_fire", lambda fid, inp: calls.append(fid) or True)
    for i in range(5):
        fs.save_flow(
            {
                "id": f"cf{i}",
                "name": "c",
                "nodes": [{"id": "a", "action": "scrape"}],
                "edges": [],
                "trigger": {"type": "cron", "cron": "* * * * *"},
            }
        )
    r = flow_triggers.run_cron_due(now=_now(9, 0))
    assert r["started"] == flow_triggers._MAX_STARTS_PER_TICK == 3 and len(calls) == 3


def test_manual_and_event_flows_not_cron_fired(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    monkeypatch.setenv("FLOW_RUNNER", "1")
    monkeypatch.setenv("FLOW_AUTO_TRIGGERS", "1")
    calls = []
    monkeypatch.setattr(flow_triggers, "_fire", lambda fid, inp: calls.append(fid) or True)
    fs.save_flow({"id": "m", "name": "m", "nodes": [{"id": "a", "action": "scrape"}], "edges": []})
    fs.save_flow(
        {
            "id": "e",
            "name": "e",
            "nodes": [{"id": "a", "action": "scrape"}],
            "edges": [],
            "trigger": {"type": "event", "event": "lead.created"},
        }
    )
    r = flow_triggers.run_cron_due(now=_now(9, 0))
    assert r["started"] == 0 and calls == []
