"""Tests — process engine (babysitter-pattern): journal replay, gates, breakpoints,
resume, never-raise. Hermetic: executors monkeypatched, tmp run-dir.
"""

from __future__ import annotations

import asyncio
import os


def _patch_dirs(monkeypatch, tmp_path):
    from app.agents import process_engine as pe

    monkeypatch.setattr(pe, "_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(pe, "_INDEX", str(tmp_path / "runs" / "index.jsonl"))
    return pe


def _fake_process(monkeypatch, steps, results):
    """process_library ko fake def + scripted executor results se patch karo."""
    from app.agents import process_library as pl

    proc = {"name": "test", "steps": steps}
    monkeypatch.setattr(pl, "PROCESSES", {"testproc": proc})
    calls = {"n": 0}

    async def fake_exec(step, inputs):
        i = min(calls["n"], len(results) - 1)
        calls["n"] += 1
        return results[i]

    monkeypatch.setattr(pl, "execute_step", fake_exec)
    return calls


def test_unknown_process_and_run(tmp_path, monkeypatch):
    pe = _patch_dirs(monkeypatch, tmp_path)
    assert pe.start_run("nahi_hai")["ok"] is False
    out = asyncio.run(pe.advance("ghost-run"))
    assert out["status"] == pe.ST_FAILED


def test_happy_path_completes(tmp_path, monkeypatch):
    pe = _patch_dirs(monkeypatch, tmp_path)
    _fake_process(
        monkeypatch,
        [{"id": "a", "action": "x"}, {"id": "b", "action": "y"}],
        [
            {"ok": True, "count": 5, "detail": "a done"},
            {"ok": True, "count": 2, "detail": "b done"},
        ],
    )
    r = pe.start_run("testproc", {"niche": "solar"})
    assert r["ok"] is True
    out = asyncio.run(pe.advance(r["run_id"]))
    assert out["status"] == pe.ST_COMPLETED
    st = pe.replay(r["run_id"])
    assert [s["step"] for s in st["steps_done"]] == ["a", "b"]
    assert st["inputs"]["niche"] == "solar"
    # journal immutable trail
    types = [e["type"] for e in pe.journal(r["run_id"])]
    assert types[0] == "run_started" and types[-1] == "run_completed"


def test_gate_fail_retry_then_failed(tmp_path, monkeypatch):
    pe = _patch_dirs(monkeypatch, tmp_path)
    _fake_process(
        monkeypatch,
        [{"id": "a", "action": "x", "gate": {"min_count": 10}, "max_retries": 1}],
        [{"ok": True, "count": 0, "detail": "kam"}],
    )
    from app.agents import process_library as pl

    # real check_gate use karo (deterministic logic test)
    r = pe.start_run("testproc")
    out = asyncio.run(pe.advance(r["run_id"]))
    assert out["status"] == pe.ST_FAILED
    assert "count" in pe.replay(r["run_id"])["last_error"]


def test_breakpoint_blocks_until_approved(tmp_path, monkeypatch):
    pe = _patch_dirs(monkeypatch, tmp_path)
    _fake_process(
        monkeypatch,
        [
            {"id": "a", "action": "x"},
            {"kind": "breakpoint", "id": "gate", "question": "aage badhau?"},
            {"id": "b", "action": "y"},
        ],
        [{"ok": True, "count": 1, "detail": "a"}, {"ok": True, "count": 1, "detail": "b"}],
    )
    r = pe.start_run("testproc")
    out = asyncio.run(pe.advance(r["run_id"]))
    assert out["status"] == pe.ST_WAITING  # ENFORCED stop
    # bina approve dobara advance = wahi rukta
    assert asyncio.run(pe.advance(r["run_id"]))["status"] == pe.ST_WAITING
    # reject path on a fresh run would fail; yahan approve
    a = pe.approve(r["run_id"], "sumit", "ok hai")
    assert a["ok"] is True
    out2 = asyncio.run(pe.advance(r["run_id"]))
    assert out2["status"] == pe.ST_COMPLETED
    # double-approve guard
    assert pe.approve(r["run_id"])["ok"] is False


def test_reject_fails_run(tmp_path, monkeypatch):
    pe = _patch_dirs(monkeypatch, tmp_path)
    _fake_process(
        monkeypatch,
        [{"kind": "breakpoint", "id": "gate", "question": "?"}],
        [],
    )
    r = pe.start_run("testproc")
    asyncio.run(pe.advance(r["run_id"]))
    rej = pe.reject(r["run_id"], "sumit", "abhi nahi")
    assert rej["ok"] is True
    assert pe.replay(r["run_id"])["status"] == pe.ST_FAILED


def test_crash_resume_from_journal(tmp_path, monkeypatch):
    """Event-sourcing core: advance dobara call (naya 'process' jaise restart) =
    journal se exact wahi se aage."""
    pe = _patch_dirs(monkeypatch, tmp_path)
    calls = _fake_process(
        monkeypatch,
        [{"id": "a", "action": "x"}, {"id": "b", "action": "y"}],
        [{"ok": True, "count": 1, "detail": "a"}, {"ok": True, "count": 1, "detail": "b"}],
    )
    r = pe.start_run("testproc")
    asyncio.run(pe.advance(r["run_id"], max_steps=1))  # sirf step a (simulated cut)
    assert pe.replay(r["run_id"])["step_index"] == 1
    out = asyncio.run(pe.advance(r["run_id"]))  # "restart"
    assert out["status"] == pe.ST_COMPLETED
    assert calls["n"] == 2  # step a dobara NAHI chala (no double-execution)


def test_list_runs_and_real_definitions(tmp_path, monkeypatch):
    pe = _patch_dirs(monkeypatch, tmp_path)
    from app.agents import process_library as pl

    # real library shape
    keys = pl.list_keys()
    assert "lead_campaign" in keys and "client_content" in keys and "growth_audit" in keys
    defs = pl.list_processes()
    lc = next(d for d in defs if d["key"] == "lead_campaign")
    assert any(s["kind"] == "breakpoint" for s in lc["steps"])  # outreach se pehle human gate
    # gate logic deterministic
    ok, _ = pl.check_gate({"gate": {"min_count": 2}}, {"ok": True, "count": 5})
    assert ok is True
    ok, reason = pl.check_gate({"gate": {"min_count": 2}}, {"ok": True, "count": 1})
    assert ok is False and "min" in reason
    ok, _ = pl.check_gate({}, {"ok": False, "detail": "boom"})
    assert ok is False
    # unknown action deterministic fail
    res = asyncio.run(pl.execute_step({"action": "nope"}, {}))
    assert res["ok"] is False
