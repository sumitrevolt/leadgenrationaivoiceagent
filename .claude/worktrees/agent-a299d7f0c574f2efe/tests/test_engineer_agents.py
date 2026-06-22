"""F.5 engineer agents — disabled / signal-based / disabled-vs-data behaviour.

Audit Section H said: "add an engineer agent only if it creates MEASURABLE
operational leverage." These tests assert each agent's score actually MOVES
in response to its signals — a score that always returns 100 is no signal at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.platform import engineer_agents as ea


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ea, "_DATA_DIR", tmp_path)
    # Default: all three flags off (lets the disabled-case tests start clean)
    monkeypatch.delenv("SRE_AGENT", raising=False)
    monkeypatch.delenv("FINOPS_AGENT", raising=False)
    monkeypatch.delenv("SECURITY_AGENT", raising=False)


# --------------------------------------------------------------------------- #
# Disabled state (project ethos: INERT when flag unset)
# --------------------------------------------------------------------------- #
def test_sre_disabled_when_flag_unset() -> None:
    out = ea.run_sre()
    assert out["status"] == "disabled"
    assert out["score"] is None


def test_finops_disabled_when_flag_unset() -> None:
    out = ea.run_finops()
    assert out["status"] == "disabled"


def test_security_disabled_when_flag_unset() -> None:
    out = ea.run_security()
    assert out["status"] == "disabled"


# --------------------------------------------------------------------------- #
# Pranav — SRE / Reliability
# --------------------------------------------------------------------------- #
def _stub_psutil_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the capacity sub-score to neutral-50 so other signals are testable
    deterministically. Without this the test-host CPU load contaminates the
    expected score (test flakes under parallel test runs / high system load).

    Implementation: drop a sentinel into sys.modules that raises on attribute
    access — `import psutil` succeeds but `psutil.cpu_percent(...)` blows up,
    landing in the agent's `except Exception` -> neutral-50 fallback."""
    import sys

    class _BombPsutil:
        def __getattr__(self, _name: str):  # noqa: ANN001
            raise RuntimeError("psutil pinned-out for test isolation")

    monkeypatch.setitem(sys.modules, "psutil", _BombPsutil())


def test_sre_no_signals_returns_neutral(monkeypatch: pytest.MonkeyPatch) -> None:
    """No backup log, no heartbeat -> three neutral-50 sub-scores, NOT zero."""
    monkeypatch.setenv("SRE_AGENT", "1")
    _stub_psutil_unavailable(monkeypatch)
    out = ea.run_sre()
    assert out["status"] == "ok"
    assert out["score"] is not None
    # All three signals neutral (50/50/50) -> exactly 50
    assert out["score"] == pytest.approx(50.0)
    assert any("backup log" in a.lower() for a in out["actions"])


def test_sre_score_lifts_on_fresh_backup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Fresh backup log SHOULD lift the score vs no-signals baseline."""
    monkeypatch.setenv("SRE_AGENT", "1")
    _stub_psutil_unavailable(monkeypatch)
    base = ea.run_sre()["score"]
    (tmp_path / "pg_backup.log").write_text("ok\n", encoding="utf-8")
    after = ea.run_sre()["score"]
    # Fresh backup contributes 100, others stay neutral 50 -> (100+50+50)/3 ≈ 66.7
    assert after > base
    assert after > 60  # fresh backup is a real positive signal


def test_sre_score_drops_on_stale_backup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Stale (>48h) backup should NOT score the same as fresh one."""
    import os
    import time

    monkeypatch.setenv("SRE_AGENT", "1")
    _stub_psutil_unavailable(monkeypatch)
    p = tmp_path / "pg_backup.log"
    p.write_text("ok\n", encoding="utf-8")
    fresh = ea.run_sre()["score"]
    # Backdate the file 72h to trigger the stale branch
    old = time.time() - 72 * 3600
    os.utime(p, (old, old))
    stale = ea.run_sre()["score"]
    assert stale < fresh  # measurable signal — score actually moves


# --------------------------------------------------------------------------- #
# Vidya — FinOps / Cost
# --------------------------------------------------------------------------- #
def test_finops_zero_load_high_score(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINOPS_AGENT", "1")
    out = ea.run_finops()
    assert out["score"] is not None
    assert out["kpis"]["today_llm_calls"] == 0
    assert out["score"] >= 80  # no spend = max margin score


def test_finops_runaway_tokens_drop_score(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """5M+ tokens/day should drop the margin score (TPD-eating signal)."""
    import time as _t

    monkeypatch.setenv("FINOPS_AGENT", "1")
    today = _t.strftime("%Y-%m-%d")
    log = tmp_path / "llm_metrics.jsonl"
    # 6M tokens across 6000 calls, all today
    log.write_text(
        "\n".join(
            json.dumps({"ts": today + "T12:00:00", "tokens": 1000, "provider": "groq"})
            for _ in range(6000)
        ),
        encoding="utf-8",
    )
    out = ea.run_finops()
    assert out["kpis"]["today_llm_tokens"] >= 5_000_000
    assert out["score"] < 50  # runaway throughput penalized
    assert any("token throughput" in a.lower() or "tpd" in a.lower() for a in out["actions"])


def test_finops_flags_litellm_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINOPS_AGENT", "1")
    monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
    out = ea.run_finops()
    assert out["kpis"]["litellm_active"] is False
    assert any("litellm" in a.lower() for a in out["actions"])


# --------------------------------------------------------------------------- #
# Arnav — Security / Compliance
# --------------------------------------------------------------------------- #
def test_security_unarmed_secrets_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECURITY_AGENT", "1")
    # All webhook secrets unset (Razorpay removed 2026-06-18 — twilio+whatsapp only)
    for k in (
        "TWILIO_AUTH_TOKEN",
        "WHATSAPP_APP_SECRET",
        "TURNSTILE_SECRET_KEY",
        "GRIEVANCE_OFFICER_EMAIL",
    ):
        monkeypatch.delenv(k, raising=False)
    out = ea.run_security()
    assert out["kpis"]["webhook_secrets_armed"] == {
        "twilio": False,
        "whatsapp": False,
    }
    actions = " ".join(out["actions"]).lower()
    assert "twilio" in actions
    assert "turnstile" in actions


def test_security_armed_secrets_lift_score(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECURITY_AGENT", "1")
    base = ea.run_security()["score"]
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "x")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "x")
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "x")
    monkeypatch.setenv("GRIEVANCE_OFFICER_EMAIL", "office@leadsgenai.in")
    armed = ea.run_security()["score"]
    assert armed > base  # measurable signal


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #
def test_unknown_role_returns_structured_error() -> None:
    out = ea.run("metaverse_engineer")
    assert out["status"] == "unknown_role"
    assert out["score"] is None


def test_run_all_returns_all_three(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SRE_AGENT", "1")
    monkeypatch.setenv("FINOPS_AGENT", "1")
    monkeypatch.setenv("SECURITY_AGENT", "1")
    out = ea.run_all()
    assert set(out) == {"sre", "finops", "security"}
    assert out["sre"]["agent"] == "pranav"
    assert out["finops"]["agent"] == "vidya"
    assert out["security"]["agent"] == "arnav"
