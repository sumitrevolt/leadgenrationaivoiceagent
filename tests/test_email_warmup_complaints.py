"""Pure-python tests for spam-complaint + unsubscribe rate tracking in email_warmup.

Covers the #1 2026 Gmail/Yahoo deliverability gate (<0.3% spam-complaint rate):
  - complaint_rate_7d math (rolling-7d complaints / sent denominator)
  - record_complaint auto-pause at >= COMPLAINT_PAUSE_PCT (0.25%) with min-sample guard
  - status() surfaces complaint_rate_7d_pct

ADR-103: an unsubscribe is NOT a spam complaint. Unsub reasons route to their own bucket
with a much higher ceiling (UNSUB_PAUSE_PCT), because Gmail MANDATES one-click opt-out and
0.2-2% unsub on cold outreach is healthy. The spam gate itself stays at 0.25% (not weakened
— §5); these tests pin BOTH halves so the buckets can't silently re-merge.

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
    # (reason must be a REAL spam report — "unsubscribe" now routes to the unsub bucket.)
    for _ in range(3):
        ew.record_complaint("x@example.com", "spam_report")
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
    ew.record_complaint("g@h.com", "spam_report")
    s = ew.status()
    assert "complaint_rate_7d_pct" in s
    assert "complaints_7d" in s
    assert s["complaints_7d"] == 1
    assert s["complaint_pause_threshold_pct"] == ew.COMPLAINT_PAUSE_PCT
    # 1 / 400 = 0.25% -> rounded to 3 places.
    assert s["complaint_rate_7d_pct"] == pytest.approx(0.25, abs=1e-6)


# --- ADR-103: unsubscribe is not a complaint ---------------------------------------


def test_prod_regression_healthy_unsubs_do_not_pause_outreach(warmup):
    """The exact live numbers that kept the GTM channel paused for 3 days (ADR-103).

    5 one-click unsubs / 854 sends = 0.585%. Under the old code every one of these landed
    in complaint_events and tripped the 0.25% SPAM gate. They are healthy opt-outs.
    """
    ew = warmup
    _seed_sent(ew, 854)
    out = {}
    for _ in range(5):
        out = ew.record_complaint("flanx@example.com", "unsub_one_click")
    assert out["recorded"] is True
    assert out["paused"] is False
    assert ew.is_paused() is False
    # Routed away from the spam bucket entirely.
    c_rate, _, complaints = ew.complaint_rate_7d()
    assert complaints == 0
    assert c_rate == 0.0
    u_rate, u_sent, unsubs = ew.unsub_rate_7d()
    assert (u_sent, unsubs) == (854, 5)
    assert u_rate == pytest.approx(0.585, abs=1e-3)


def test_reply_unsubscribe_reason_also_routes_to_unsub_bucket(warmup):
    """The other real caller: reply_agent -> record_complaint(frm, "reply_unsubscribe")."""
    ew = warmup
    _seed_sent(ew, 1000)
    ew.record_complaint("a@b.com", "reply_unsubscribe")
    assert ew.complaint_rate_7d()[2] == 0
    assert ew.unsub_rate_7d()[2] == 1


def test_spam_gate_not_weakened_real_complaints_still_pause_at_025(warmup):
    """§5: the spam-complaint gate keeps its 0.25% threshold. Splitting != weakening."""
    ew = warmup
    assert ew.COMPLAINT_PAUSE_PCT == 0.25
    _seed_sent(ew, 1000)
    out = {}
    for _ in range(3):  # 3/1000 = 0.3% >= 0.25%
        out = ew.record_complaint("spammed@example.com", "fbl_spam_report")
    assert out["paused"] is True
    assert ew.is_paused() is True
    assert "complaint rate" in ew._load().get("paused_reason", "")


def test_unknown_reason_stays_conservative_and_counts_as_complaint(warmup):
    """Blank/unknown reason must fail toward the STRICTER gate, not the looser one."""
    ew = warmup
    _seed_sent(ew, 1000)
    ew.record_complaint("x@y.com", "")
    assert ew.complaint_rate_7d()[2] == 1
    assert ew.unsub_rate_7d()[2] == 0


def test_mistargeted_list_still_pauses_on_unsub_flood(warmup):
    """Unsub gate is looser, not absent: >= UNSUB_PAUSE_PCT (2%) = list is wrong."""
    ew = warmup
    _seed_sent(ew, 1000)
    out = {}
    for _ in range(20):  # 20/1000 = 2.0% >= 2.0%
        out = ew.record_complaint("bulk@example.com", "unsub_one_click")
    assert out["paused"] is True
    assert ew.is_paused() is True
    assert "unsubscribe rate" in ew._load().get("paused_reason", "")


def test_unsub_min_sample_guard_blocks_premature_pause(warmup):
    ew = warmup
    _seed_sent(ew, 50)  # < _MIN_SENDS_FOR_UNSUB_RATE=100
    out = {}
    for _ in range(5):  # 10% — but sample too small to act on
        out = ew.record_complaint("e@f.com", "unsub_one_click")
    assert out["recorded"] is True
    assert out["paused"] is False
    assert ew.is_paused() is False


def test_status_surfaces_unsub_fields(warmup):
    ew = warmup
    _seed_sent(ew, 400)
    ew.record_complaint("g@h.com", "unsub_one_click")
    s = ew.status()
    assert s["unsubs_7d"] == 1
    assert s["unsub_pause_threshold_pct"] == ew.UNSUB_PAUSE_PCT
    assert s["unsub_rate_7d_pct"] == pytest.approx(0.25, abs=1e-6)
    # Spam bucket untouched by an opt-out.
    assert s["complaints_7d"] == 0


def test_record_unsub_never_raises_on_bad_state(warmup, monkeypatch):
    ew = warmup
    monkeypatch.setattr(
        ew, "_load", lambda: (_ for _ in ()).throw(RuntimeError("boom")), raising=True
    )
    out = ew.record_unsub("z@z.com", "unsub_one_click")
    assert out["recorded"] is False
    assert out["paused"] is False


def test_record_complaint_never_raises_on_bad_state(warmup, monkeypatch):
    ew = warmup
    monkeypatch.setattr(
        ew, "_load", lambda: (_ for _ in ()).throw(RuntimeError("boom")), raising=True
    )
    out = ew.record_complaint("z@z.com", "spam")
    assert out["recorded"] is False
    assert out["paused"] is False
