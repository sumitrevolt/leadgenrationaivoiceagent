"""W3.3 — coordinator (Boss planner, 1043 lines) core pure-logic coverage.

The coordinator had zero tests. Its two deterministic building blocks feed the whole
planning flow: `_guess_niche` (route a goal to a configured niche) and `_extract_list`
(salvage a JSON list from noisy LLM output). Both are pure — cover them so a regression
in routing or plan-parsing is caught.
"""
from __future__ import annotations

import app.niches
from app.agents import coordinator as co


def test_guess_niche_matches_key_name_and_falls_back(monkeypatch):
    monkeypatch.setattr(app.niches, "NICHES", {"gym": {"name": "Gym & Fitness"}, "salon": {"name": "Salon"}})
    assert co._guess_niche("mujhe apne gym ke liye leads chahiye") == "gym"  # key hit
    assert co._guess_niche("Salon marketing help chahiye") == "salon"  # name hit
    assert co._guess_niche("kuch bhi random baat") == "general"  # no match → fallback


def test_extract_list_salvages_json_list():
    assert co._extract_list('prefix ["a","b"] suffix') == ["a", "b"]
    assert co._extract_list("[1, 2, 3]") == [1, 2, 3]
    assert co._extract_list("no list at all") == []
    assert co._extract_list('{"not": "a list"}') == []  # dict, not list
    assert co._extract_list("") == []
