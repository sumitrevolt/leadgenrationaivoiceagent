"""W4.1 (Wave-4, SAFE/gated) — warm-lead SLA aging → founder nudge.

Mid-funnel leads that go stale (>24h stuck) or sit warm (score 40-69) had no proactive
signal to the founder. This adds a founder-only ntfy nudge, reusing build_pipeline's
existing per-stage stuckCount / warm_count (no change to the pipeline logic). It is
gated OFF by default (WARM_SLA_NUDGE) and sends ONLY to the founder — zero customer
send, so no §5 ban/deliverability surface.
"""

from __future__ import annotations

import asyncio

from app.platform import office_hq, ops_alerts


def _fake_pipeline(stuck_a=2, warm=5, stuck_b=3):
    async def _p(items_limit=1):
        return [{"stuckCount": stuck_a, "warm_count": warm}, {"stuckCount": stuck_b}]

    return _p


def test_nudge_gated_off_by_default(monkeypatch):
    monkeypatch.delenv("WARM_SLA_NUDGE", raising=False)
    monkeypatch.setattr(office_hq, "build_pipeline", _fake_pipeline())
    fired = []
    monkeypatch.setattr(ops_alerts, "alert_warm_sla", lambda *a: fired.append(a), raising=False)

    res = asyncio.run(office_hq.warm_lead_sla_nudge())
    assert res["nudged"] is False
    assert fired == [], "nudge must be inert unless WARM_SLA_NUDGE is enabled"


def test_nudge_fires_above_threshold(monkeypatch):
    monkeypatch.setenv("WARM_SLA_NUDGE", "1")
    monkeypatch.setattr(office_hq, "build_pipeline", _fake_pipeline(stuck_a=2, warm=5, stuck_b=3))
    fired = []
    monkeypatch.setattr(
        ops_alerts, "alert_warm_sla", lambda stuck, warm: fired.append((stuck, warm)), raising=False
    )

    res = asyncio.run(office_hq.warm_lead_sla_nudge())
    assert res["nudged"] is True
    assert res["stuck"] == 5 and res["warm"] == 5
    assert fired == [(5, 5)]


def test_nudge_below_threshold_silent(monkeypatch):
    monkeypatch.setenv("WARM_SLA_NUDGE", "1")
    monkeypatch.setenv("WARM_SLA_MIN", "5")
    monkeypatch.setattr(office_hq, "build_pipeline", _fake_pipeline(stuck_a=1, warm=0, stuck_b=1))
    fired = []
    monkeypatch.setattr(ops_alerts, "alert_warm_sla", lambda *a: fired.append(1), raising=False)

    res = asyncio.run(office_hq.warm_lead_sla_nudge())
    assert res["nudged"] is False and fired == []
