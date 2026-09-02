"""ops_alerts — threshold/cooldown/disabled behaviour matrix.

ntfy.push_bg is monkey-patched to capture pushes — no network. Each test
gets its own tmp DATA_DIR so the cooldown ledger doesn't leak across tests.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from app.platform import ops_alerts


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[tuple[str, str, str]]:
    """Redirect storage + capture ntfy pushes into a list."""
    monkeypatch.setattr(ops_alerts, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(ops_alerts, "_STATE_PATH", tmp_path / "ops_alerts_state.jsonl")
    pushes: list[tuple[str, str, str]] = []

    def _capture(
        title: str, message: str, priority: str = "default", tags: list[str] | None = None
    ) -> None:
        pushes.append((title, message, priority))

    monkeypatch.setattr(ops_alerts, "_ntfy", _capture)
    monkeypatch.setenv("OPS_ALERTS", "1")
    return pushes


# --------------------------------------------------------------------------- #
# Master flag
# --------------------------------------------------------------------------- #
def test_disabled_master_flag_silences_all(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ops_alerts, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(ops_alerts, "_STATE_PATH", tmp_path / "ops_alerts_state.jsonl")
    pushes: list = []
    monkeypatch.setattr(ops_alerts, "_ntfy", lambda *a, **kw: pushes.append(a))
    monkeypatch.delenv("OPS_ALERTS", raising=False)

    assert ops_alerts.maybe_alert_engineer_score("sre", 10.0)["reason"] == "disabled"
    assert ops_alerts.daily_readiness_digest()["reason"] == "disabled"
    assert pushes == []


# --------------------------------------------------------------------------- #
# Engineer-score alert
# --------------------------------------------------------------------------- #
def test_engineer_above_threshold_no_alert(captured: list) -> None:
    out = ops_alerts.maybe_alert_engineer_score("sre", 85.0)
    assert out["alerted"] is False
    assert out["reason"] == "above_threshold"
    assert captured == []


def test_engineer_below_threshold_alerts_once(captured: list) -> None:
    out1 = ops_alerts.maybe_alert_engineer_score("sre", 30.0, summary="all backups stale")
    out2 = ops_alerts.maybe_alert_engineer_score("sre", 25.0)  # still bad
    assert out1["alerted"] is True
    # Cooldown prevents the second push
    assert out2["alerted"] is False
    assert out2["reason"] == "cooldown"
    assert len(captured) == 1
    assert "30" in captured[0][0]
    assert "stale" in captured[0][1]


def test_engineer_no_score_skipped(captured: list) -> None:
    out = ops_alerts.maybe_alert_engineer_score("sre", None)
    assert out["alerted"] is False
    assert out["reason"] == "no_score"


def test_engineer_threshold_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The threshold MUST be env-controllable so the operator can tune signal noise."""
    monkeypatch.setenv("OPS_ALERT_ENGINEER_THRESHOLD", "90")
    # Force re-import of the threshold (module-level)
    import importlib

    importlib.reload(ops_alerts)
    monkeypatch.setenv("OPS_ALERTS", "1")
    # Re-stub after reload (reload wipes the prior monkeypatch on _ntfy)
    monkeypatch.setattr(ops_alerts, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(ops_alerts, "_STATE_PATH", tmp_path / "ops_alerts_state.jsonl")
    pushes: list = []
    monkeypatch.setattr(ops_alerts, "_ntfy", lambda *a, **kw: pushes.append(a))
    # 85 is now BELOW the bumped-up bar of 90
    out = ops_alerts.maybe_alert_engineer_score("sre", 85.0)
    assert out["alerted"] is True
    assert len(pushes) == 1


# --------------------------------------------------------------------------- #
# eval_gate burst alert
# --------------------------------------------------------------------------- #
def test_eval_reject_below_burst_no_alert(
    captured: list, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A single isolated reject must NOT page (audit insight: one bad run is noise)."""
    # Empty history -> 0 recent rejects -> below burst (3)
    from app.agents import eval_gate

    monkeypatch.setattr(eval_gate, "_HISTORY_PATH", tmp_path / "empty.jsonl")
    out = ops_alerts.maybe_alert_eval_reject(
        "rag",
        "faithfulness",
        {"decision": "reject", "current": 0.3, "baseline": 0.9},
    )
    assert out["alerted"] is False
    assert out["reason"] == "below_burst"


def test_eval_reject_burst_alerts(
    captured: list, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """3 rejects in window -> page."""
    from app.agents import eval_gate

    monkeypatch.setattr(eval_gate, "_HISTORY_PATH", tmp_path / "history.jsonl")
    monkeypatch.setattr(eval_gate, "_DATA_DIR", tmp_path)
    monkeypatch.setenv("EVAL_GATE", "1")
    # Plant 3 rejects in recent history
    for _ in range(3):
        eval_gate.record_score(
            "rag",
            "faithfulness",
            0.2,
            agent="ci",
            extra={"decision": "reject", "ratio": 0.2},
        )
    out = ops_alerts.maybe_alert_eval_reject(
        "rag",
        "faithfulness",
        {"decision": "reject", "current": 0.2, "baseline": 0.9},
    )
    assert out["alerted"] is True
    assert out["recent_rejects"] >= 3
    assert len(captured) == 1


def test_eval_accept_decision_never_alerts(captured: list) -> None:
    out = ops_alerts.maybe_alert_eval_reject(
        "rag",
        "faithfulness",
        {"decision": "accept", "current": 0.95, "baseline": 0.9},
    )
    assert out["alerted"] is False
    assert out["reason"] == "not_reject"


# --------------------------------------------------------------------------- #
# Daily readiness digest
# --------------------------------------------------------------------------- #
def test_digest_silent_when_no_blockers(monkeypatch: pytest.MonkeyPatch, captured: list) -> None:
    """No BLOCKER -> no push (quiet-by-design)."""
    from app.api import activation as ax

    monkeypatch.setattr(
        ax,
        "_PROBES",
        (lambda: {"status": "OK", "label": "all good"},),
    )
    out = ops_alerts.daily_readiness_digest()
    assert out["alerted"] is False
    assert out["reason"] == "no_blockers"


def test_digest_pages_on_blocker(monkeypatch: pytest.MonkeyPatch, captured: list) -> None:
    from app.api import activation as ax

    monkeypatch.setattr(
        ax,
        "_PROBES",
        (
            lambda: {"status": "BLOCKER", "label": "Razorpay live", "action": "set keys"},
            lambda: {"status": "OK", "label": "Sentry"},
        ),
    )
    out = ops_alerts.daily_readiness_digest()
    assert out["alerted"] is True
    assert out["blockers"] == 1
    assert len(captured) == 1
    assert "Razorpay" in captured[0][1]


def test_digest_cooldown_blocks_repeat(monkeypatch: pytest.MonkeyPatch, captured: list) -> None:
    from app.api import activation as ax

    monkeypatch.setattr(
        ax,
        "_PROBES",
        (lambda: {"status": "BLOCKER", "label": "X", "action": "y"},),
    )
    ops_alerts.daily_readiness_digest()  # first call: alerts
    out2 = ops_alerts.daily_readiness_digest()
    assert out2["alerted"] is False
    assert out2["reason"] == "cooldown"
    assert len(captured) == 1  # only the first push went out
