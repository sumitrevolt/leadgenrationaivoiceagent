"""eval_gate — close-the-loop reward signal for self_improve.

Guards the decision logic precisely so a regression cannot bootstrap-pollute
its own baseline, and so cold start is correctly recognized as `no_baseline`.
Storage is redirected to a tmp dir per test (no global jsonl pollution).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents import eval_gate


@pytest.fixture(autouse=True)
def _isolated_storage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Each test gets its own data dir + history file."""
    monkeypatch.setattr(eval_gate, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(eval_gate, "_HISTORY_PATH", tmp_path / "eval_history.jsonl")
    # Default ON so record_score actually writes — individual tests can flip OFF.
    monkeypatch.setenv("EVAL_GATE", "1")
    monkeypatch.delenv("EVAL_GATE_HARD", raising=False)


# --------------------------------------------------------------------------- #
# Flag wiring
# --------------------------------------------------------------------------- #
def test_inert_when_flag_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """EVAL_GATE unset -> record_score is a no-op (no file write)."""
    monkeypatch.delenv("EVAL_GATE", raising=False)
    assert eval_gate.enabled() is False
    eval_gate.record_score("rag", "faithfulness", 0.9)
    assert not eval_gate._HISTORY_PATH.exists()


def test_hard_mode_flag() -> None:
    assert eval_gate.hard_mode() is False  # OFF by default in fixture


def test_hard_mode_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_GATE_HARD", "1")
    assert eval_gate.hard_mode() is True


# --------------------------------------------------------------------------- #
# Storage round-trip
# --------------------------------------------------------------------------- #
def test_record_and_read_roundtrip() -> None:
    for s in (0.80, 0.82, 0.85, 0.78, 0.83):
        eval_gate.record_score("rag", "faithfulness", s, agent="ci")
    scores = eval_gate.recent_scores("rag", "faithfulness", n=20)
    assert scores == [0.80, 0.82, 0.85, 0.78, 0.83]


def test_recent_scores_filters_by_suite_and_metric() -> None:
    eval_gate.record_score("rag", "faithfulness", 0.9)
    eval_gate.record_score("rag", "answer_relevancy", 0.1)
    eval_gate.record_score("other_suite", "faithfulness", 0.5)
    out = eval_gate.recent_scores("rag", "faithfulness", n=20)
    assert out == [0.9]


def test_recent_scores_exclude_last() -> None:
    for s in (0.8, 0.85, 0.9):
        eval_gate.record_score("rag", "faithfulness", s)
    assert eval_gate.recent_scores("rag", "faithfulness", n=20, exclude_last=1) == [0.8, 0.85]


# --------------------------------------------------------------------------- #
# Baseline
# --------------------------------------------------------------------------- #
def test_baseline_returns_none_below_min_history() -> None:
    """4 samples < _MIN_HISTORY_FOR_BASELINE = 5 -> None (cold start)."""
    for s in (0.8, 0.85, 0.9, 0.82):
        eval_gate.record_score("rag", "faithfulness", s)
    assert eval_gate.baseline("rag", "faithfulness") is None


def test_baseline_is_median_not_mean() -> None:
    """Median resists a single anomalous spike — that's the whole point."""
    for s in (0.80, 0.81, 0.82, 0.83, 0.84, 99.0):
        eval_gate.record_score("rag", "faithfulness", s)
    base = eval_gate.baseline("rag", "faithfulness")
    assert base is not None
    assert 0.80 < base < 0.90  # not pulled to mean (~16)


# --------------------------------------------------------------------------- #
# Decisions
# --------------------------------------------------------------------------- #
def test_no_baseline_decision_on_cold_start() -> None:
    eval_gate.record_score("rag", "faithfulness", 0.9)  # only 1 sample
    v = eval_gate.gate_decision("rag", "faithfulness", current_score=0.91)
    assert v["decision"] == "no_baseline"
    assert v["baseline"] is None
    assert v["ratio"] is None


def test_accept_when_current_at_or_above_baseline() -> None:
    for s in (0.80, 0.82, 0.81, 0.83, 0.80):  # median = 0.81
        eval_gate.record_score("rag", "faithfulness", s)
    v = eval_gate.gate_decision("rag", "faithfulness", current_score=0.82)
    assert v["decision"] == "accept"
    assert v["baseline"] == pytest.approx(0.81)


def test_reject_when_current_below_tolerance() -> None:
    for s in (0.85, 0.86, 0.85, 0.87, 0.86):  # median = 0.86
        eval_gate.record_score("rag", "faithfulness", s)
    # 0.50 / 0.86 = 0.58 << 0.95 tolerance
    v = eval_gate.gate_decision("rag", "faithfulness", current_score=0.50)
    assert v["decision"] == "reject"
    assert v["ratio"] < 0.95


def test_accept_within_tolerance_band() -> None:
    """Tiny dip (within tolerance) is NOT a regression."""
    for s in (0.80, 0.80, 0.80, 0.80, 0.80):
        eval_gate.record_score("rag", "faithfulness", s)
    # 0.77 / 0.80 = 0.9625 >= 0.95 -> accept
    v = eval_gate.gate_decision("rag", "faithfulness", current_score=0.77)
    assert v["decision"] == "accept"


# --------------------------------------------------------------------------- #
# score_and_gate convenience — records WITH decision tag
# --------------------------------------------------------------------------- #
def test_score_and_gate_persists_decision_in_extra() -> None:
    for s in (0.85, 0.86, 0.85, 0.87, 0.86):
        eval_gate.record_score("rag", "faithfulness", s)
    verdict = eval_gate.score_and_gate(
        "rag",
        "faithfulness",
        0.50,
        agent="self_improve",
        artifact="task-42",
    )
    assert verdict["decision"] == "reject"
    # The history row must carry the decision for downstream observability
    rows = eval_gate._read_history()
    last = rows[-1]
    assert last["agent"] == "self_improve"
    assert last["artifact"] == "task-42"
    assert last["extra"]["decision"] == "reject"


# --------------------------------------------------------------------------- #
# summary rollup
# --------------------------------------------------------------------------- #
def test_summary_with_no_history() -> None:
    s = eval_gate.summary()
    assert s["total_records"] == 0
    assert s["suites"] == {}


def test_summary_rolls_up_decisions_and_baselines() -> None:
    for v in (0.80, 0.85, 0.82, 0.83, 0.81):
        eval_gate.record_score("rag", "faithfulness", v)
    eval_gate.score_and_gate("rag", "faithfulness", 0.84, agent="ci")
    eval_gate.score_and_gate("rag", "faithfulness", 0.30, agent="ci")  # reject
    summary = eval_gate.summary()
    assert summary["total_records"] >= 7
    assert "rag" in summary["suites"]
    assert "faithfulness" in summary["suites"]["rag"]
    rec = summary["recent_decisions"]
    assert rec["accept"] >= 1
    assert rec["reject"] >= 1
