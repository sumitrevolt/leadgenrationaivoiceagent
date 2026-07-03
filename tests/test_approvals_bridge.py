"""approvals_bridge — sidecar status, read-adapters, risk-tiered decide.

The bars (sub-project D V1):
- Status sidecar collapses to latest; never mutates source files.
- Each read-adapter tolerates a missing file (one bad stream != broken cockpit).
- decide() is idempotent and fires the correct BOUNDED action per source.
- Sales approve NEVER triggers a real send or another stream's action
  (risky real-send stays draft-only / must-stay-manual).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.platform import approvals_bridge as ab


def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ab, "_DECISIONS", str(tmp_path / "decisions.jsonl"))
    monkeypatch.setattr(ab, "_COORD_RUNS", str(tmp_path / "coord.jsonl"))
    monkeypatch.setattr(ab, "_FDE_DEPLOYS", str(tmp_path / "fde.jsonl"))


def _write(path: str, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


# --------------------------------------------------------------------------- #
# Status sidecar
# --------------------------------------------------------------------------- #
def test_status_sidecar_collapse_to_latest(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    ab._set_status("sales", "L1", "approved", by="a")
    ab._set_status("sales", "L1", "rejected", by="b")  # later wins
    assert ab._status_for("sales", "L1") == "rejected"
    assert ab._status_for("sales", "UNKNOWN") == "pending"


def test_set_status_does_not_mutate_sources(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _write(
        ab._COORD_RUNS, [{"run_id": "r1", "execute": False, "goal": "g", "summary": "s", "at": "t"}]
    )
    before = Path(ab._COORD_RUNS).read_text(encoding="utf-8")
    ab.decide("coordinator", "r1", "reject", by="a")
    after = Path(ab._COORD_RUNS).read_text(encoding="utf-8")
    assert before == after  # source file untouched; status lives in sidecar


# --------------------------------------------------------------------------- #
# Read adapters
# --------------------------------------------------------------------------- #
def test_adapters_tolerate_missing_files(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(ab, "_drafts_sales", lambda smap: [])  # avoid real sales_team
    out = ab.list_drafts()
    assert out["drafts"] == []
    assert out["counts"]["pending"] == 0


def test_coordinator_adapter_excludes_executed_includes_engineering(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _write(
        ab._COORD_RUNS,
        [
            {"run_id": "exec1", "execute": True, "goal": "did-it", "summary": "ran", "at": "t1"},
            {
                "run_id": "draft1",
                "execute": False,
                "goal": "plan-it",
                "summary": "proposal",
                "at": "t2",
            },
            # engineering_crew carries design/implementation_plan (NOT summary) + key `pattern`
            {
                "run_id": "eng1",
                "execute": False,
                "pattern": "engineering_crew",
                "goal": "build X",
                "design": "ASCII arch",
                "at": "t4",
            },
            {"run_id": "nosum", "execute": False, "at": "t3"},  # no substance -> excluded
        ],
    )
    by_id = {r["id"]: r for r in ab._drafts_coordinator(ab._status_map())}
    assert set(by_id) == {"draft1", "eng1"}  # executed + empty filtered; engineering surfaces
    assert by_id["eng1"]["meta"]["mode"] == "engineering_crew"  # reads `pattern`, not 'sequential'
    assert by_id["eng1"]["body"]  # `design` used as body fallback


def test_sales_adapter_reads_md_body(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    md = tmp_path / "p1.md"
    md.write_text("Full deep-dive playbook here", encoding="utf-8")
    import app.agents.sales_team as st

    monkeypatch.setattr(
        st,
        "list_analyses",
        lambda limit=20: [
            {
                "pid": "p1",
                "name": "Acme",
                "grade": "A",
                "score": 88,
                "niche": "gym",
                "city": "Pune",
                "phone": "+91",
                "ts": 1700000000,
                "md": str(md),
            },
        ],
    )
    rows = ab._drafts_sales(ab._status_map())
    assert len(rows) == 1 and rows[0]["id"] == "p1"
    assert "deep-dive playbook" in rows[0]["body"]
    assert "Acme" in rows[0]["title"]


def test_sales_adapter_missing_md_falls_back(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    import app.agents.sales_team as st

    monkeypatch.setattr(
        st,
        "list_analyses",
        lambda limit=20: [
            {
                "pid": "p2",
                "name": "Beta",
                "grade": "B",
                "score": 50,
                "niche": "spa",
                "city": "Goa",
                "phone": "+92",
                "ts": 0,
                "md": str(tmp_path / "missing.md"),
            },
        ],
    )
    rows = ab._drafts_sales(ab._status_map())
    assert rows[0]["id"] == "p2"
    assert rows[0]["body"]  # falls back to niche/city/phone line


def test_fde_adapter_reads_persisted_report(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _write(
        ab._FDE_DEPLOYS,
        [
            {
                "id": "fde1",
                "agent": "Neo",
                "client": {"business_name": "Acme"},
                "deployed": 2,
                "total": 3,
                "at": "t",
                "steps": [
                    {
                        "skill": "drip_journey",
                        "title": "Drip",
                        "summary": "made",
                        "data": {"journey_id": "j9"},
                    }
                ],
            }
        ],
    )
    rows = ab._drafts_fde(ab._status_map())
    assert len(rows) == 1 and rows[0]["id"] == "fde1"
    assert "Acme" in rows[0]["title"]


# --------------------------------------------------------------------------- #
# decide() — validation + idempotency
# --------------------------------------------------------------------------- #
def test_decide_rejects_bad_args(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    assert ab.decide("nope", "x", "approve")["ok"] is False
    assert ab.decide("sales", "", "approve")["ok"] is False
    assert ab.decide("sales", "x", "maybe")["ok"] is False


def test_decide_idempotent(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    first = ab.decide("sales", "L1", "approve", by="a")
    assert first["status"] == "approved" and not first.get("noop")
    second = ab.decide("sales", "L1", "reject", by="b")  # already decided -> no-op
    assert second.get("noop") is True
    assert second["status"] == "approved"  # unchanged


# --------------------------------------------------------------------------- #
# Bounded SAFE actions (risk-tiered)
# --------------------------------------------------------------------------- #
def test_approve_fde_enables_drip_journey(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _write(
        ab._FDE_DEPLOYS,
        [
            {
                "id": "fde1",
                "agent": "Neo",
                "client": {"business_name": "Acme"},
                "deployed": 1,
                "total": 1,
                "at": "t",
                "steps": [{"skill": "drip_journey", "title": "Drip", "data": {"journey_id": "j9"}}],
            }
        ],
    )
    calls = []
    import app.marketing.journeys as jr

    monkeypatch.setattr(jr, "set_enabled", lambda jid, en: calls.append((jid, en)) or True)
    out = ab.decide("fde", "fde1", "approve", by="t")
    assert out["status"] == "approved"
    assert calls == [("j9", True)]  # exactly the disabled drip got enabled


def test_approve_coordinator_queues_self_improve(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    _write(
        ab._COORD_RUNS,
        [
            {
                "run_id": "r1",
                "execute": False,
                "goal": "scale outreach",
                "summary": "plan",
                "at": "t",
            }
        ],
    )
    tasks = []
    import app.agents.self_improve as si

    monkeypatch.setattr(si, "add_task", lambda task, **k: tasks.append(task) or {"ok": True})
    out = ab.decide("coordinator", "r1", "approve", by="t")
    assert out["status"] == "approved"
    assert len(tasks) == 1 and "scale outreach" in tasks[0]


def test_approve_sales_never_triggers_send_or_other_actions(monkeypatch, tmp_path):
    """Risk-tier guarantee: sales approve = mark-reviewed only. No real send,
    no coordinator/fde side-action."""
    _isolate(monkeypatch, tmp_path)
    fired = {"si": False, "drip": False}
    import app.agents.self_improve as si
    import app.marketing.journeys as jr

    monkeypatch.setattr(
        si, "add_task", lambda *a, **k: fired.__setitem__("si", True) or {"ok": True}
    )
    monkeypatch.setattr(jr, "set_enabled", lambda *a, **k: fired.__setitem__("drip", True) or True)
    out = ab.decide("sales", "lead_1", "approve", by="t")
    assert out["status"] == "approved"
    assert "manual" in (out.get("action") or "")
    assert fired["si"] is False and fired["drip"] is False


# --------------------------------------------------------------------------- #
# list_drafts merge + pending filter
# --------------------------------------------------------------------------- #
def test_list_drafts_pending_filter_and_counts(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(ab, "_drafts_sales", lambda smap: [])
    _write(
        ab._COORD_RUNS,
        [
            {"run_id": "r1", "execute": False, "goal": "a", "summary": "s1", "at": "t1"},
            {"run_id": "r2", "execute": False, "goal": "b", "summary": "s2", "at": "t2"},
        ],
    )
    assert ab.list_drafts()["counts"]["pending"] == 2
    ab.decide("coordinator", "r1", "reject", by="x")
    out = ab.list_drafts()  # pending-only by default
    assert out["counts"]["pending"] == 1
    assert {d["id"] for d in out["drafts"]} == {"r2"}
    assert len(ab.list_drafts(include_decided=True)["drafts"]) == 2


# --------------------------------------------------------------------------- #
# 2026-07-03 fixes: epoch-ts -> ISO at the bridge + dedupe dup pids (latest wins)
# --------------------------------------------------------------------------- #
def test_sales_adapter_epoch_ts_to_iso_and_dedupe(monkeypatch, tmp_path):
    """(1) sales index stores ts as epoch-SECONDS; the UI got the raw int and JS
    new Date(int) read it as ms -> every draft showed "20616 din pehle" (1970).
    Bridge must emit ISO. (2) index has dup pids (re-analyzed) -> dedupe."""
    _isolate(monkeypatch, tmp_path)
    from app.agents import sales_team

    rows = [  # list_analyses returns newest-first
        {"pid": "111", "name": "", "grade": "C", "score": 53, "ts": 1782984616, "md": ""},
        {"pid": "111", "name": "", "grade": "C", "score": 53, "ts": 1782900000, "md": ""},
        {"pid": "222", "name": "Shop", "grade": "B", "score": 70, "ts": "2026-07-01T10:00:00", "md": ""},
    ]
    monkeypatch.setattr(sales_team, "list_analyses", lambda limit=20: rows)
    out = ab._drafts_sales(ab._status_map())
    ids = [d["id"] for d in out]
    assert ids.count("111") == 1  # deduped, latest-first wins
    d111 = next(d for d in out if d["id"] == "111")
    assert d111["created_at"].startswith("2026-")  # ISO string, not raw epoch int
    d222 = next(d for d in out if d["id"] == "222")
    assert d222["created_at"] == "2026-07-01T10:00:00"  # strings pass through


def test_ts_to_iso_never_raises():
    assert ab._ts_to_iso(None) == ""
    assert ab._ts_to_iso("") == ""
    assert ab._ts_to_iso("2026-01-01T00:00:00") == "2026-01-01T00:00:00"
    assert ab._ts_to_iso(1782984616).startswith("2026-")
    assert ab._ts_to_iso(-5) == "-5" or ab._ts_to_iso(-5) == ""  # weird input, no crash
