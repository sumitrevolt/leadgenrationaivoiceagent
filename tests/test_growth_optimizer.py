"""Tests — self-healing growth optimizer + channel experiments + city rotation.
Sync + asyncio.run pattern, tmp stores monkeypatch. No network/DB needed.
"""

from __future__ import annotations

import asyncio
import random

from tests._api_helpers import iter_mounted_routes


# ----------------------------- channel experiments ----------------------------- #
def test_experiments_stats_and_bandit(tmp_path, monkeypatch):
    from app.marketing import channel_experiments as ce

    monkeypatch.setattr(ce, "_RUNS", str(tmp_path / "runs.jsonl"))
    monkeypatch.setattr(ce, "_OUTCOMES", str(tmp_path / "out.jsonl"))

    # fresh: sab scores equal (Laplace 1/2)
    st = ce.stats()
    assert set(st.keys()) == set(ce.CHANNELS)
    assert all(d["score"] == 0.5 for d in st.values())

    # seo_page pe 2 assets + 3 outcomes -> score sabse upar
    ce._append(ce._RUNS, {"channel": "seo_page", "assets": 2})
    ce.record_outcome("seo_page", "inquiry", 3)
    st = ce.stats()
    assert st["seo_page"]["score"] > 0.5

    # exploit pick (epsilon ko 0 jaisa banane ke liye rng with high values)
    class FakeRng(random.Random):
        def random(self):
            return 0.99  # > EPSILON -> exploit

    picked = ce.pick_channels(2, rng=FakeRng())
    assert picked[0] == "seo_page"  # best score exploit
    assert len(set(picked)) == 2

    # unknown channel outcome -> graceful
    assert ce.record_outcome("instagram_ads")["ok"] is False


def test_experiments_gated_off(tmp_path, monkeypatch):
    from app.marketing import channel_experiments as ce

    monkeypatch.delenv("CHANNEL_EXPERIMENTS", raising=False)
    assert asyncio.run(ce.run_daily()) == {"enabled": False}


def test_experiments_run_daily_launches(tmp_path, monkeypatch):
    from app.marketing import channel_experiments as ce

    monkeypatch.setattr(ce, "_RUNS", str(tmp_path / "runs.jsonl"))
    monkeypatch.setattr(ce, "_OUTCOMES", str(tmp_path / "out.jsonl"))
    monkeypatch.setenv("CHANNEL_EXPERIMENTS", "1")

    out = asyncio.run(ce.run_daily(2))
    assert out["enabled"] is True
    # generators free-LLM fallback templates use karte — kuch launch hona chahiye
    assert len(out.get("launched") or []) >= 1
    assert ce.recent(5)


# ----------------------------- growth optimizer ----------------------------- #
def test_weakest_stage_rules():
    from app.agents import growth_optimizer as go

    # thin pipeline -> lead_supply
    w = go.weakest_stage({"prospects": {"ready": 3}, "emails": {}, "inquiries": {}})
    assert w["stage"] == "lead_supply"

    # leads theek, replies kam -> outreach_quality
    w = go.weakest_stage(
        {
            "prospects": {"ready": 50, "replied": 0},
            "emails": {"emailed": 100},
            "inquiries": {"total": 20},
            "seo_pages": 50,
        }
    )
    assert w["stage"] == "outreach_quality"

    # inbound kamzor
    w = go.weakest_stage(
        {
            "prospects": {"ready": 50, "replied": 5},
            "emails": {"emailed": 50},
            "inquiries": {"total": 2},
            "seo_pages": 3,
        }
    )
    assert w["stage"] == "inbound"

    # sab theek + dunning open -> retention
    w = go.weakest_stage(
        {
            "prospects": {"ready": 50, "replied": 5},
            "emails": {"emailed": 50},
            "inquiries": {"total": 20},
            "seo_pages": 50,
            "clients_active": 3,
            "nurture": {"finished": 0, "converted": 1},
            "dunning_open": 2,
        }
    )
    assert w["stage"] == "retention"

    # koi bottleneck nahi -> scale
    w = go.weakest_stage(
        {
            "prospects": {"ready": 50, "replied": 5},
            "emails": {"emailed": 50},
            "inquiries": {"total": 20},
            "seo_pages": 50,
            "clients_active": 3,
            "nurture": {"finished": 0, "converted": 1},
            "dunning_open": 0,
        }
    )
    assert w["stage"] == "scale"


def test_optimizer_gated_off(monkeypatch):
    from app.agents import growth_optimizer as go

    monkeypatch.delenv("GROWTH_OPTIMIZER", raising=False)
    assert asyncio.run(go.optimize()) == {"enabled": False}


def test_optimizer_snapshot_defensive():
    from app.agents import growth_optimizer as go

    snap = asyncio.run(go.funnel_snapshot())
    assert "at" in snap  # har source fail bhi ho to dict milta
    w = go.weakest_stage(snap)
    assert w["stage"] in go.STAGES


def test_suggest_new_ways_fallback(tmp_path, monkeypatch):
    from app.agents import growth_optimizer as go

    monkeypatch.setattr(go, "_IDEAS", str(tmp_path / "ideas.jsonl"))
    ideas = asyncio.run(go.suggest_new_ways("solar"))
    assert len(ideas) == 5  # LLM fail -> static fallback, phir bhi 5 ideas
    # ideas _IDEAS ledger me persist hote hain (recent_ideas helper removed)
    import os

    assert os.path.isfile(go._IDEAS)
    with open(go._IDEAS, encoding="utf-8") as f:
        assert len([ln for ln in f if ln.strip()]) >= 1


# ----------------------------- city rotation ----------------------------- #
def test_city_rotation_deterministic(monkeypatch):
    from app.platform import niche_prospector as np_

    monkeypatch.delenv("PROSPECT_CITIES", raising=False)
    a = np_.city_rotation(4, day_ordinal=100)
    b = np_.city_rotation(4, day_ordinal=100)
    c = np_.city_rotation(4, day_ordinal=101)
    assert a == b and len(a) == 4
    assert a != c  # agle din window aage badhti
    # env override
    monkeypatch.setenv("PROSPECT_CITIES", "Delhi, Goa")
    assert set(np_.city_rotation(4)) == {"Delhi", "Goa"}


def test_growth_router_has_optimizer_routes():
    from app.api.growth import router

    paths = {r.path for r in iter_mounted_routes(router)}
    for p in (
        "/growth/optimizer/analysis",
        "/growth/optimizer/run",
        "/growth/experiments/run",
        "/growth/experiments/outcome",
    ):
        assert p in paths, f"route missing: {p}"
