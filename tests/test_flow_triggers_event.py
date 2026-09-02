import app.automation.flow_store as fs
from app.automation import flow_triggers


def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_DIR", str(tmp_path / "fr"))
    monkeypatch.setattr(fs, "_PATH", str(tmp_path / "fr" / "flows.jsonl"))
    monkeypatch.setattr(flow_triggers, "_EVENT_FIRED", {})  # reset in-memory dedupe ring
    monkeypatch.setenv("FLOW_RUNNER", "1")
    monkeypatch.setenv("FLOW_AUTO_TRIGGERS", "1")


def _save_event_flow(fid="ev", event="lead.qualified"):
    fs.save_flow(
        {
            "id": fid,
            "name": fid,
            "nodes": [{"id": "a", "action": "scrape"}],
            "edges": [],
            "trigger": {"type": "event", "event": event},
        }
    )


def test_fire_event_matches_and_injects_inputs(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    seen = []
    monkeypatch.setattr(flow_triggers, "_fire", lambda fid, inp: seen.append((fid, inp)) or True)
    _save_event_flow()
    r = flow_triggers.fire_event("lead.qualified", {"lead_id": "L1"}, "c1")
    assert r["fired"] == 1 and len(seen) == 1
    fid, inp = seen[0]
    assert fid == "ev"
    assert inp["_trigger"] == "event" and inp["_event"] == "lead.qualified"
    assert inp["_flow_origin"] == "ev" and inp["lead_id"] == "L1"


def test_fire_event_loop_guard_skips_flow_origin(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    seen = []
    monkeypatch.setattr(flow_triggers, "_fire", lambda fid, inp: seen.append(fid) or True)
    _save_event_flow()
    r = flow_triggers.fire_event("lead.qualified", {"lead_id": "L1", "_flow_origin": "ev"}, "c1")
    assert r.get("skipped") == "loop_guard" and seen == []


def test_fire_event_short_window_dedupe(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    seen = []
    monkeypatch.setattr(flow_triggers, "_fire", lambda fid, inp: seen.append(fid) or True)
    _save_event_flow()
    r1 = flow_triggers.fire_event("lead.qualified", {"lead_id": "L9"}, "c1")
    r2 = flow_triggers.fire_event(
        "lead.qualified", {"lead_id": "L9"}, "c1"
    )  # same payload, < window
    assert r1["fired"] == 1 and r2["fired"] == 0 and seen == ["ev"]


def test_fire_event_wrong_event_no_fire(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    seen = []
    monkeypatch.setattr(flow_triggers, "_fire", lambda fid, inp: seen.append(fid) or True)
    _save_event_flow(event="lead.created")
    r = flow_triggers.fire_event("lead.qualified", {"lead_id": "L1"}, "c1")
    assert r["fired"] == 0 and seen == []


def test_fire_event_gated_off_no_fire(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    monkeypatch.delenv("FLOW_AUTO_TRIGGERS", raising=False)
    seen = []
    monkeypatch.setattr(flow_triggers, "_fire", lambda fid, inp: seen.append(fid) or True)
    _save_event_flow()
    r = flow_triggers.fire_event("lead.qualified", {"lead_id": "L1"}, "c1")
    assert r.get("skipped") == "gated" and seen == []
