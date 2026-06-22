"""Pure-python tests for app.agents.judge_calibration.

No network/DB/LLM — we seed temp jsonl files and monkeypatch the module's path
constants. Covers: empty/sparse -> insufficient-data, kappa math edge cases,
reliable vs advisory verdicts, collapse-to-latest, malformed lines.
"""

from __future__ import annotations

import json

import pytest

from app.agents import judge_calibration as jc


def _write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


# --------------------------------------------------------------------------- #
# cohens_kappa unit math
# --------------------------------------------------------------------------- #
def test_kappa_none_when_empty():
    assert jc.cohens_kappa([]) is None


def test_kappa_perfect_agreement():
    pairs = [(1, 1), (0, 0), (1, 1), (0, 0)]
    assert jc.cohens_kappa(pairs) == pytest.approx(1.0)


def test_kappa_perfect_disagreement_negative():
    pairs = [(1, 0), (0, 1), (1, 0), (0, 1)]
    assert jc.cohens_kappa(pairs) == pytest.approx(-1.0)


def test_kappa_both_constant_identical_returns_one():
    # Degenerate: both raters always 1, always agree -> conventionally 1.0
    pairs = [(1, 1), (1, 1), (1, 1)]
    assert jc.cohens_kappa(pairs) == pytest.approx(1.0)


def test_kappa_judge_constant_human_mixed():
    # Judge always 1, human disagrees half the time -> kappa 0 (no chance-corrected skill)
    pairs = [(1, 1), (1, 0), (1, 1), (1, 0)]
    k = jc.cohens_kappa(pairs)
    assert k == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# calibrate() — sparse / empty
# --------------------------------------------------------------------------- #
def test_calibrate_empty_all_insufficient(tmp_path, monkeypatch):
    monkeypatch.setattr(jc, "_DECISIONS", str(tmp_path / "approval_decisions.jsonl"))
    monkeypatch.setattr(jc, "_CODE_PATCHES", str(tmp_path / "code_patches.jsonl"))
    monkeypatch.setattr(jc, "_COORD_RUNS", str(tmp_path / "coordination_runs.jsonl"))

    res = jc.calibrate()
    assert res["ok"] is True
    sources = {j["source"] for j in res["judges"]}
    assert sources == {"code_upgrader", "coordinator", "sales", "fde"}
    assert all(j["verdict"] == "insufficient-data" for j in res["judges"])
    assert set(res["summary"]["insufficient"]) == sources


# --------------------------------------------------------------------------- #
# calibrate() — code_upgrader reliable path + collapse-to-latest
# --------------------------------------------------------------------------- #
def test_code_patches_reliable_and_collapse(tmp_path, monkeypatch):
    cp = tmp_path / "code_patches.jsonl"
    rows = []
    # 6 patches humans approved
    for i in range(6):
        rows.append({"id": f"p{i}", "status": "proposed", "title": "t"})
        rows.append({"id": f"p{i}", "status": "approved"})
    # 4 patches humans rejected -> judge said yes (1), human said no (0)
    for i in range(6, 10):
        rows.append({"id": f"p{i}", "status": "proposed"})
        rows.append({"id": f"p{i}", "status": "rejected"})
    _write_jsonl(cp, rows)

    monkeypatch.setattr(jc, "_DECISIONS", str(tmp_path / "nope.jsonl"))
    monkeypatch.setattr(jc, "_CODE_PATCHES", str(cp))
    monkeypatch.setattr(jc, "_COORD_RUNS", str(tmp_path / "nope2.jsonl"))

    res = jc.calibrate()
    cu = next(j for j in res["judges"] if j["source"] == "code_upgrader")
    # 10 decided pairs (collapse-to-latest: 10 unique ids, not 20)
    assert cu["n_pairs"] == 10
    # Judge always 1; humans mostly 1 -> agreement 0.6 ; kappa 0 (constant judge)
    assert cu["agreement"] == pytest.approx(0.6)
    # constant judge -> kappa 0 -> advisory (>= MIN_PAIRS but kappa < 0.41)
    assert cu["verdict"] == "advisory"


# --------------------------------------------------------------------------- #
# calibrate() — coordinator judge matches human via approval_decisions
# --------------------------------------------------------------------------- #
def test_coordinator_reliable(tmp_path, monkeypatch):
    coord = tmp_path / "coordination_runs.jsonl"
    dec = tmp_path / "approval_decisions.jsonl"

    runs = []
    decisions = []
    # 6 substantive runs the human approved (judge 1, human 1)
    for i in range(6):
        runs.append({"run_id": f"r{i}", "summary": "real plan", "execute": False})
        decisions.append(
            {"source": "coordinator", "item_id": f"r{i}", "status": "approved", "by": "admin"}
        )
    # 4 empty runs the human rejected (judge 0, human 0)
    for i in range(6, 10):
        runs.append({"run_id": f"r{i}", "execute": False})  # no substance
        decisions.append(
            {"source": "coordinator", "item_id": f"r{i}", "status": "rejected", "by": "admin"}
        )
    _write_jsonl(coord, runs)
    _write_jsonl(dec, decisions)

    monkeypatch.setattr(jc, "_DECISIONS", str(dec))
    monkeypatch.setattr(jc, "_CODE_PATCHES", str(tmp_path / "nope.jsonl"))
    monkeypatch.setattr(jc, "_COORD_RUNS", str(coord))

    res = jc.calibrate()
    co = next(j for j in res["judges"] if j["source"] == "coordinator")
    assert co["n_pairs"] == 10
    assert co["agreement"] == pytest.approx(1.0)
    assert co["kappa"] == pytest.approx(1.0)
    assert co["verdict"] == "reliable"
    assert "coordinator" in res["summary"]["reliable"]


def test_decisions_collapse_to_latest(tmp_path, monkeypatch):
    dec = tmp_path / "approval_decisions.jsonl"
    # same item decided twice; latest (approved) should win
    rows = [
        {"source": "sales", "item_id": "s1", "status": "rejected", "by": "a"},
        {"source": "sales", "item_id": "s1", "status": "approved", "by": "a"},
    ]
    _write_jsonl(dec, rows)
    monkeypatch.setattr(jc, "_DECISIONS", str(dec))
    monkeypatch.setattr(jc, "_CODE_PATCHES", str(tmp_path / "n.jsonl"))
    monkeypatch.setattr(jc, "_COORD_RUNS", str(tmp_path / "n2.jsonl"))

    res = jc.calibrate()
    sales = next(j for j in res["judges"] if j["source"] == "sales")
    assert sales["n_pairs"] == 1  # collapsed to one
    # only 1 pair -> below MIN_PAIRS -> insufficient
    assert sales["verdict"] == "insufficient-data"


def test_malformed_lines_ignored(tmp_path, monkeypatch):
    cp = tmp_path / "code_patches.jsonl"
    with open(cp, "w", encoding="utf-8") as f:
        f.write("{not json}\n")
        f.write("\n")
        f.write(json.dumps({"id": "p1", "status": "approved"}) + "\n")
        f.write("[1,2,3]\n")  # valid json but not a dict -> ignored
    monkeypatch.setattr(jc, "_DECISIONS", str(tmp_path / "n.jsonl"))
    monkeypatch.setattr(jc, "_CODE_PATCHES", str(cp))
    monkeypatch.setattr(jc, "_COORD_RUNS", str(tmp_path / "n2.jsonl"))

    res = jc.calibrate()
    assert res["ok"] is True
    cu = next(j for j in res["judges"] if j["source"] == "code_upgrader")
    assert cu["n_pairs"] == 1


def test_never_raises_on_bad_path(monkeypatch):
    # Point at a directory-as-file style nonsense; must still return ok.
    monkeypatch.setattr(jc, "_DECISIONS", "\x00bad\x00path")
    monkeypatch.setattr(jc, "_CODE_PATCHES", "\x00bad\x00path")
    monkeypatch.setattr(jc, "_COORD_RUNS", "\x00bad\x00path")
    res = jc.calibrate()
    assert res["ok"] is True
    assert len(res["judges"]) == 4
