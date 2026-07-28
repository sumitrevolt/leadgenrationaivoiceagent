"""
Tests: growth engine (app/platform/growth_engine.py) — self-run pulse.
======================================================================

No network / no DB / no LLM:
  - growth_engine._PULSE_FILE / _HISTORY_FILE / _INQUIRIES_FILE  → tmp_path
  - prospector._PROSPECTS_FILE → tmp_path (real data/ na chhue)
  - team._db → None (DB calls silently skip; team_status zeros deta hai)
  - seo_blog.run_daily_blog / prospector.run_prospecting → async no-op stubs
    (self-heal kabhi asli network/LLM/scrape na kare)

Goals:
  - collect_metrics() expected keys ke saath dict deta hai, empty data pe zeros,
    KABHI raise nahi, growth_pulse.json + history.jsonl likhta hai
  - pulse() dict deta hai, pulse file likhta hai, empty data pe KABHI raise nahi
  - latest_pulse()/history() roundtrip
  - pitch-learning: seeded prospects se best_niche detect hota hai
"""

import json
import os

import pytest

from app.platform import growth_engine, prospector, team


@pytest.fixture
def tmp_env(monkeypatch, tmp_path):
    """Saari growth + prospect files tmp_path pe; DB off (team._db→None)."""
    pulse = os.path.join(str(tmp_path), "growth_pulse.json")
    hist = os.path.join(str(tmp_path), "growth_history.jsonl")
    inq = os.path.join(str(tmp_path), "inquiries.jsonl")
    pros = os.path.join(str(tmp_path), "prospects.jsonl")
    monkeypatch.setattr(growth_engine, "_PULSE_FILE", pulse)
    monkeypatch.setattr(growth_engine, "_HISTORY_FILE", hist)
    monkeypatch.setattr(growth_engine, "_INQUIRIES_FILE", inq)
    monkeypatch.setattr(prospector, "_PROSPECTS_FILE", lambda: pros)
    # DB off — team.log_event / team_status silently no-op (no DB needed).
    monkeypatch.setattr(team, "_db", lambda: None)
    # collect_metrics blog/clients/content ko REAL data/ se padhta hai — full-suite me
    # pichle tests ka leftover state "empty -> zeros" assertion ko tod deta tha.
    # In sources ko empty stub karo (yeh tests prospects pe focus karte hain).
    from app.marketing import auto_content, clients_store, seo_blog

    monkeypatch.setattr(seo_blog, "list_articles", lambda *a, **k: [])
    monkeypatch.setattr(clients_store, "list_clients", lambda *a, **k: [])
    monkeypatch.setattr(auto_content, "list_queue", lambda *a, **k: [])
    # collect_metrics ka prospects DB-FALLBACK (get_db_session) shared test-DB ke
    # leftover leads count kar leta tha — docstring "no DB" intent ke against. DB off
    # karo taaki empty-jsonl pe prospects.total sach me 0 rahe (fallback skip ho).
    import app.models.base as _mb

    def _no_db(*_a, **_k):
        raise RuntimeError("DB off in growth_engine unit test")

    monkeypatch.setattr(_mb, "get_db_session", _no_db, raising=False)
    return {"pulse": pulse, "hist": hist, "inq": inq, "pros": pros}


@pytest.fixture
def no_heal_side_effects(monkeypatch):
    """Self-heal kabhi asli blog/scrape/content-gen na kare — async no-op stubs.
    auto_content.run_daily_content() bhi stub: full-suite me pichle tests ke leftover
    active-clients self-heal branch (b) ko trigger karte the → real LLM network call →
    poora pytest hang (test isolation me clients=0 hone se chhupa rehta tha)."""
    from app.marketing import auto_content, seo_blog

    async def _blog(*_a, **_k):
        return {"published": 0, "slugs": []}

    async def _scrape(*_a, **_k):
        return {"new": 0}

    async def _content(*_a, **_k):
        return {"items": 0}

    monkeypatch.setattr(seo_blog, "run_daily_blog", _blog)
    monkeypatch.setattr(prospector, "run_prospecting", _scrape)
    monkeypatch.setattr(auto_content, "run_daily_content", _content)


def _seed_prospect(pfile, rec):
    with open(pfile, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- #
# collect_metrics
# --------------------------------------------------------------------------- #
class TestCollectMetrics:
    def test_empty_returns_zeros_and_keys(self, tmp_env):
        snap = growth_engine.collect_metrics()
        assert isinstance(snap, dict)
        # Expected top-level keys present.
        for k in (
            "at",
            "prospects",
            "inquiries",
            "emails",
            "blog_articles",
            "content_items",
            "marketing_clients_active",
            "actions_today",
            "top_staff",
        ):
            assert k in snap, f"missing key: {k}"
        # Empty data → zeros.
        assert snap["prospects"]["total"] == 0
        assert snap["inquiries"]["total"] == 0
        assert snap["blog_articles"] == 0
        assert snap["actions_today"] == 0
        assert snap["top_staff"] == []

    def test_writes_pulse_and_history(self, tmp_env):
        growth_engine.collect_metrics()
        assert os.path.isfile(tmp_env["pulse"]), "growth_pulse.json not written"
        assert os.path.isfile(tmp_env["hist"]), "growth_history.jsonl not written"
        # pulse file parses to a dict.
        with open(tmp_env["pulse"], encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict) and "prospects" in data

    def test_counts_seeded_prospects(self, tmp_env):
        _seed_prospect(
            tmp_env["pros"],
            {
                "id": "1",
                "niche": "solar",
                "status": "ready",
                "email": "a@b.com",
                "found_at": "2026-06-08T10:00:00Z",
            },
        )
        _seed_prospect(
            tmp_env["pros"],
            {"id": "2", "niche": "solar", "status": "client", "found_at": "2026-06-08T10:00:00Z"},
        )
        snap = growth_engine.collect_metrics()
        assert snap["prospects"]["total"] == 2
        assert snap["prospects"]["ready"] == 1
        assert snap["prospects"]["client"] == 1
        assert snap["prospects"]["with_email"] == 1


# --------------------------------------------------------------------------- #
# pulse
# --------------------------------------------------------------------------- #
class TestPulse:
    @pytest.mark.asyncio
    async def test_empty_never_raises_and_writes(self, tmp_env, no_heal_side_effects):
        res = await growth_engine.pulse()
        assert isinstance(res, dict)
        assert "error" not in res
        # Pulse dict has self-improvement keys merged in.
        for k in ("healed", "insights", "last_pulse_at", "prospects"):
            assert k in res, f"missing key: {k}"
        assert os.path.isfile(tmp_env["pulse"])

    @pytest.mark.asyncio
    async def test_learns_best_niche(self, tmp_env, no_heal_side_effects):
        # 'solar' niche: 4 prospects, 2 converted (replied+client) → ratio 0.5
        # 'dental' niche: 3 prospects, 0 converted → ratio 0.0
        for i in range(2):
            _seed_prospect(
                tmp_env["pros"],
                {
                    "id": f"s{i}",
                    "niche": "solar",
                    "status": "ready",
                    "found_at": "2026-06-08T10:00:00Z",
                },
            )
        _seed_prospect(
            tmp_env["pros"],
            {"id": "s2", "niche": "solar", "status": "replied", "found_at": "2026-06-08T10:00:00Z"},
        )
        _seed_prospect(
            tmp_env["pros"],
            {"id": "s3", "niche": "solar", "status": "client", "found_at": "2026-06-08T10:00:00Z"},
        )
        for i in range(3):
            _seed_prospect(
                tmp_env["pros"],
                {
                    "id": f"d{i}",
                    "niche": "dental",
                    "status": "ready",
                    "found_at": "2026-06-08T10:00:00Z",
                },
            )
        res = await growth_engine.pulse()
        assert res.get("best_niche") == "solar"
        assert res.get("best_niche_ratio") == 0.5
        assert isinstance(res.get("insights"), list) and res["insights"]


# --------------------------------------------------------------------------- #
# latest_pulse / history roundtrip
# --------------------------------------------------------------------------- #
class TestReadHelpers:
    def test_latest_pulse_empty_then_present(self, tmp_env):
        assert growth_engine.latest_pulse() == {}
        growth_engine.collect_metrics()
        latest = growth_engine.latest_pulse()
        assert isinstance(latest, dict) and "prospects" in latest

    def test_history_roundtrip_newest_first(self, tmp_env):
        # Two collects → two history lines.
        growth_engine.collect_metrics()
        growth_engine.collect_metrics()
        hist = growth_engine.history(limit=10)
        assert isinstance(hist, list)
        assert len(hist) >= 2
        # Each line has the compact trend keys.
        assert "prospects_total" in hist[0]
        assert "at" in hist[0]

    def test_history_empty_no_file(self, tmp_env):
        # No collect yet → no history file → empty list, never raises.
        assert growth_engine.history() == []
