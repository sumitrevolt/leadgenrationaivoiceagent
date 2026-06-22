"""Pure-python tests for spam-complaint-rate tracking + auto-pause in email_warmup.

Covers the #1 2026 Gmail/Yahoo deliverability gate (<0.3% spam-complaint rate):
  - complaint_rate_7d math (rolling-7d complaints / sent denominator)
  - record_complaint auto-pause at >= COMPLAINT_PAUSE_PCT (0.25%) with min-sample guard
  - status() surfaces complaint_rate_7d_pct

No network/DB/LLM — state file redirected to a tmp path, alert email stubbed out.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def warmup(tmp_path, monkeypatch):
    """Fresh module instance with state + alert isolated to tmp."""
    import app.platform.email_warmup as ew

    ew = importlib.reload(ew)
    # Redirect state file into tmp dir so tests never touch real data/.
    monkeypatch.setattr(ew, "_STATE", str(tmp_path / "warmup.json"), raising=True)
    # Neutralise the alert side-effect (no SMTP / event loop in pure tests).
    monkeypatch.setattr(ew, "_alert", lambda reason: None, raising=True)
    # Ensure deterministic flag state (flag-independence not under test here).
    monkeypatch.delenv("NOTIFY_EMAIL", raising=False)
    return ew


def _seed_sent(ew, n: int) -> None:
    """Record n sends (single batch event keeps the math simple)."""
    ew.record_sent(n)


def test_complaint_rate_zero_when_no_sends(warmup):
    rate, sent, complaints = warmup.complaint_rate_7d()
    assert rate == 0.0
    assert sent == 0
    assert complaints == 0


def test_complaint_rate_math(warmup):
    ew = warmup
    _seed_sent(ew, 1000)
    # 3 complaints over 1000 sends => 0.3%
    for _ in range(3):
        ew.record_complaint("x@example.com", "unsubscribe")
    rate, sent, complaints = ew.complaint_rate_7d()
    assert sent == 1000
    assert complaints == 3
    assert rate == pytest.approx(0.3, abs=1e-6)


def test_no_pause_below_threshold(warmup):
    ew = warmup
    _seed_sent(ew, 1000)
    # 2 / 1000 = 0.2% < 0.25% pause threshold => no pause.
    for _ in range(2):
        out = ew.record_complaint("a@b.com", "spam")
    assert out["recorded"] is True
    assert out["paused"] is False
    assert ew.is_paused() is False


def test_pause_at_threshold(warmup):
    ew = warmup
    _seed_sent(ew, 1000)
    # 3 / 1000 = 0.3% >= 0.25% => pause on the 3rd complaint.
    out = {}
    for _ in range(3):
        out = ew.record_complaint("c@d.com", "spam")
    assert out["paused"] is True
    assert ew.is_paused() is True
    st = ew._load()
    assert "complaint rate" in st.get("paused_reason", "")


def test_min_sample_guard_blocks_premature_pause(warmup):
    ew = warmup
    # Only 50 sends (< _MIN_SENDS_FOR_COMPLAINT_RATE=100). Even 5 complaints (10%)
    # must NOT pause — small-sample noise guard.
    _seed_sent(ew, 50)
    out = {}
    for _ in range(5):
        out = ew.record_complaint("e@f.com", "spam")
    assert out["recorded"] is True
    assert out["paused"] is False
    assert ew.is_paused() is False


def test_status_surfaces_complaint_fields(warmup):
    ew = warmup
    _seed_sent(ew, 400)
    ew.record_complaint("g@h.com", "unsubscribe")
    s = ew.status()
    assert "complaint_rate_7d_pct" in s
    assert "complaints_7d" in s
    assert s["complaints_7d"] == 1
    assert s["complaint_pause_threshold_pct"] == ew.COMPLAINT_PAUSE_PCT
    # 1 / 400 = 0.25% -> rounded to 3 places.
    assert s["complaint_rate_7d_pct"] == pytest.approx(0.25, abs=1e-6)


def test_record_complaint_never_raises_on_bad_state(warmup, monkeypatch):
    ew = warmup
    monkeypatch.setattr(
        ew, "_load", lambda: (_ for _ in ()).throw(RuntimeError("boom")), raising=True
    )
    out = ew.record_complaint("z@z.com", "spam")
    assert out["recorded"] is False
    assert out["paused"] is False
