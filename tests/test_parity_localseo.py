"""Tests — local SEO batch (geo_visibility, grid_rank, listings_presence + router).

Offline + isolated: koi network/DB nahi. Stores tmp_path pe monkeypatch,
free_ai.chat + Places search mocked. Style: tests/test_parity_memory.py jaisa.
"""

import asyncio
import json
import os


# --------------------------------------------------------------------------- #
# geo_visibility — fuzzy mention, probes, score+cache, LLM-down fallback
# --------------------------------------------------------------------------- #
def _setup_geo(tmp_path, monkeypatch):
    from app.marketing import geo_visibility as gv

    monkeypatch.setattr(gv, "_LOG_FILE", str(tmp_path / "geo_checks.jsonl"))
    monkeypatch.setattr(gv, "_CACHE", {})
    return gv


def test_mentions_fuzzy():
    from app.marketing.geo_visibility import _mentions

    # direct substring (case-insensitive)
    assert _mentions("Aap Sharma Solar Solutions try karo, badhiya hai.", "Sharma Solar Solutions")
    # token overlap >= 60% (order/extra words tolerant)
    assert _mentions("Top picks: Solar Sharma (Pune) aur Patel Energy.", "Sharma Solar")
    # negative — alag business
    assert not _mentions("Patel Energy aur GreenVolt best hain.", "Sharma Solar Solutions")
    # empty-safe
    assert not _mentions("", "Sharma Solar")
    assert not _mentions("kuch bhi", "")


def test_build_probes():
    from app.marketing.geo_visibility import build_probes

    probes = build_probes("dentist", "Pune")
    assert 3 <= len(probes) <= 4
    assert all("Pune" in p for p in probes)
    assert any("dentist" in p for p in probes)


def test_geo_check_score_cache_and_log(tmp_path, monkeypatch):
    gv = _setup_geo(tmp_path, monkeypatch)
    from app.voice_agent import free_ai

    calls = {"n": 0}

    async def fake_chat(system=None, messages=None, **kw):
        calls["n"] += 1
        # pehli 2 probes me business mention, baaki me competitor
        if calls["n"] <= 2:
            return ("Sharma Solar Solutions sabse accha hai, phir Patel Energy.", "stub")
        return ("Patel Energy aur GreenVolt try karo.", "stub")

    monkeypatch.setattr(free_ai, "chat", fake_chat)

    rep = asyncio.run(gv.check("Sharma Solar Solutions", "solar", "Pune"))
    assert rep["ok"] is True
    assert rep["answered"] == 4 and rep["mentioned"] == 2
    assert rep["score"] == 50
    assert rep["verdict"] and rep["tips"] and rep["cta"]["audit"] == "/audit"
    assert len(rep["probes"]) == 4

    # jsonl log likha gaya
    rows = [json.loads(ln) for ln in open(tmp_path / "geo_checks.jsonl", encoding="utf-8")]
    assert len(rows) == 1 and rows[0]["score"] == 50

    # cache-hit: dobara call = LLM dobara NAHI (calls["n"] same)
    n_before = calls["n"]
    rep2 = asyncio.run(gv.check("sharma solar solutions", "solar", "PUNE"))
    assert rep2.get("cached") is True and rep2["score"] == 50
    assert calls["n"] == n_before

    # recent() admin view
    assert gv.recent(5)[0]["business_name"] == "Sharma Solar Solutions"


def test_geo_check_ai_unavailable(tmp_path, monkeypatch):
    gv = _setup_geo(tmp_path, monkeypatch)
    from app.voice_agent import free_ai

    async def dead_chat(system=None, messages=None, **kw):
        raise RuntimeError("all providers down")

    monkeypatch.setattr(free_ai, "chat", dead_chat)
    rep = asyncio.run(gv.check("Sharma Solar", "solar", "Pune"))
    assert rep["ok"] is False and rep["error"] == "ai_unavailable"
    # failure cache NAHI hota + log nahi
    assert gv._CACHE == {}
    assert not os.path.isfile(tmp_path / "geo_checks.jsonl")


def test_geo_check_missing_inputs(tmp_path, monkeypatch):
    gv = _setup_geo(tmp_path, monkeypatch)
    assert asyncio.run(gv.check("", "solar", "Pune"))["ok"] is False
    assert asyncio.run(gv.check("Sharma Solar", "solar", ""))["ok"] is False


# --------------------------------------------------------------------------- #
# grid_rank — geometry, key/cap gates, mocked grid run
# --------------------------------------------------------------------------- #
def _setup_grid(tmp_path, monkeypatch):
    from app.platform import grid_rank as gr

    monkeypatch.setattr(gr, "_RUNS_FILE", str(tmp_path / "grid_rank_runs.jsonl"))
    return gr


def test_grid_points_geometry():
    from app.platform.grid_rank import grid_points, point_label

    pts = grid_points(18.52, 73.85, radius_km=2.0)
    assert len(pts) == 9
    center = [p for p in pts if p["row"] == 0 and p["col"] == 0][0]
    assert center["lat"] == 18.52 and center["lng"] == 73.85
    assert center["label"] == "Center"
    # symmetric offsets
    north = [p for p in pts if p["row"] == -1 and p["col"] == 0][0]
    south = [p for p in pts if p["row"] == 1 and p["col"] == 0][0]
    assert abs((18.52 - north["lat"]) - (south["lat"] - 18.52)) < 1e-6
    assert north["lat"] < 18.52 < south["lat"]
    assert point_label(-1, -1) == "North-West" and point_label(1, 1) == "South-East"


def test_grid_missing_key_and_inputs(tmp_path, monkeypatch):
    gr = _setup_grid(tmp_path, monkeypatch)
    monkeypatch.setattr(gr, "_api_key", lambda: "")
    res = asyncio.run(gr.grid_check("solar installer", 18.52, 73.85, "Sharma Solar"))
    assert res["ok"] is False and res["reason"] == "maps_key_missing"
    assert asyncio.run(gr.grid_check("", 18.52, 73.85, "X"))["ok"] is False
    assert asyncio.run(gr.grid_check("kw", "bad", "lng", "X"))["ok"] is False


def test_grid_daily_cap(tmp_path, monkeypatch):
    gr = _setup_grid(tmp_path, monkeypatch)
    monkeypatch.setattr(gr, "_api_key", lambda: "test-key")
    today = gr._today()
    for i in range(3):
        gr._append_jsonl(
            gr._RUNS_FILE, {"keyword": f"k{i}", "checked_at": f"{today}T0{i}:00:00+00:00"}
        )
    assert gr.runs_today() == 3
    res = asyncio.run(gr.grid_check("solar", 18.52, 73.85, "Sharma Solar"))
    assert res["ok"] is False and res["reason"] == "daily_cap_reached"


def test_grid_check_ranks_and_summary(tmp_path, monkeypatch):
    gr = _setup_grid(tmp_path, monkeypatch)
    monkeypatch.setattr(gr, "_api_key", lambda: "test-key")

    lookups = {"n": 0}

    async def fake_search(keyword, lat, lng, radius_m, api_key):
        lookups["n"] += 1
        if lookups["n"] == 1:
            return []  # ek point pe no results
        if lookups["n"] == 2:
            return [{"name": "Other Biz"}] * 20  # top-20 ke bahar
        # baaki points: rank = 2
        return [{"name": "Patel Energy"}, {"name": "Sharma Solar Solutions"}, {"name": "GreenVolt"}]

    monkeypatch.setattr(gr, "_places_search_at", fake_search)

    res = asyncio.run(gr.grid_check("solar installer", 18.52, 73.85, "Sharma Solar Solutions", 2.0))
    assert res["ok"] is True
    assert res["lookups_used"] == 9 and lookups["n"] == 9  # cost cap: exactly 9
    assert len(res["grid"]) == 9
    assert res["found_points"] == 7 and res["avg_rank"] == 2.0
    notes = [g.get("note") for g in res["grid"]]
    assert "no_results" in notes and ">20" in notes
    assert "rank 2" in res["summary"]
    # run jsonl me gaya + recent_runs/runs_today
    assert gr.runs_today() == 1
    assert gr.recent_runs(5)[0]["keyword"] == "solar installer"


def test_grid_summarize_empty():
    from app.platform.grid_rank import summarize

    s = summarize([{"label": "Center", "rank": None}] * 9)
    assert "top-20" in s and "/audit" in s


# --------------------------------------------------------------------------- #
# listings_presence — checklist (NO fetch), score, status round-trip
# --------------------------------------------------------------------------- #
def _setup_listings(tmp_path, monkeypatch):
    from app.marketing import listings_presence as lp

    monkeypatch.setattr(lp, "_STATUS_FILE", str(tmp_path / "listings_status.jsonl"))
    return lp


def test_listings_checklist_links(tmp_path, monkeypatch):
    lp = _setup_listings(tmp_path, monkeypatch)
    res = lp.checklist("Sharma Solar Solutions", "Pune", "solar")
    assert res["ok"] is True
    dirs = res["directories"]
    assert len(dirs) == 10
    keys = {d["key"] for d in dirs}
    assert {
        "google_business",
        "justdial",
        "sulekha",
        "indiamart",
        "tradeindia",
        "facebook",
        "instagram",
        "apple_maps",
        "bing_places",
        "mapmyindia",
    } == keys
    jd = [d for d in dirs if d["key"] == "justdial"][0]
    # quoted business name + city deep-link me (LINK only — koi fetch nahi)
    assert "justdial.com" in jd["search_url"] and "Sharma+Solar" in jd["search_url"]
    assert all(d["why"] and d["listing_url"] for d in dirs)
    assert lp.checklist("")["ok"] is False


def test_listings_score():
    from app.marketing.listings_presence import directories, score

    all_keys = {d["key"]: True for d in directories()}
    assert score(all_keys)["score"] == 100
    none = score({})
    assert none["score"] == 0 and len(none["tips"]) == 5 and len(none["missing"]) == 10
    partial = score({"google_business": True})
    assert partial["score"] == 30 and "google_business" in partial["present"]
    # weights sum exactly 100
    assert sum(d["weight"] for d in directories()) == 100
    # garbage-safe
    assert score(None)["score"] == 0


def test_listings_status_roundtrip(tmp_path, monkeypatch):
    lp = _setup_listings(tmp_path, monkeypatch)
    # empty pehle
    assert lp.get_status("client-1")["status"] is None
    r = lp.save_status("client-1", {"google_business": True, "justdial": True, "hacker_key": True})
    assert r["ok"] is True and r["saved"]["score"] == 42
    assert "hacker_key" not in r["saved"]["present"]  # unknown keys filtered
    # update → latest jeet-ta hai
    lp.save_status("client-1", {"google_business": True})
    got = lp.get_status("client-1")
    assert got["ok"] is True and got["score"] == 30
    assert lp.save_status("", {})["ok"] is False


# --------------------------------------------------------------------------- #
# router — importable + exact paths (mount /api ke saath /api/localseo/*)
# --------------------------------------------------------------------------- #
def test_localseo_router_paths():
    from app.api.localseo import router

    paths = {r.path for r in router.routes}
    assert paths == {
        "/localseo/geo-check",
        "/localseo/geo-checks",
        "/localseo/grid-rank",
        "/localseo/grid-runs",
        "/localseo/listings-checklist",
        "/localseo/listings-status",
    }
