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
    monkeypatch.setattr(
        app.niches, "NICHES", {"gym": {"name": "Gym & Fitness"}, "salon": {"name": "Salon"}}
    )
    assert co._guess_niche("mujhe apne gym ke liye leads chahiye") == "gym"  # key hit
    assert co._guess_niche("Salon marketing help chahiye") == "salon"  # name hit
    assert co._guess_niche("kuch bhi random baat") == "general"  # no match → fallback


def test_extract_list_salvages_json_list():
    assert co._extract_list('prefix ["a","b"] suffix') == ["a", "b"]
    assert co._extract_list("[1, 2, 3]") == [1, 2, 3]
    assert co._extract_list("no list at all") == []
    assert co._extract_list('{"not": "a list"}') == []  # dict, not list
    assert co._extract_list("") == []


def test_build_handoff_meta_bounded_and_redacted():
    meta = co._build_handoff_meta(
        "dev",
        2,
        {"tool": "hashtags.research", "research": "call 9876543210 for details"},
    )
    assert meta["from_agent"] == "dev"
    assert meta["seq"] == 2
    # PII redacted in handoff preview (Item B — no raw phone across handoff)
    assert "9876543210" not in meta["context_preview"]
    assert "[REDACTED_PHONE]" in meta["context_preview"]
    assert len(meta["context_preview"]) <= 600


def test_build_handoff_meta_fails_open():
    def boom(*a, **k):
        raise RuntimeError("guardrails down")

    import app.voice_agent.guardrails as grd

    monkeypatch = None  # avoid import in signature — use direct call below
    # Simulate failure by patching the imported module fn.
    orig = grd.get_guardrails

    def fake_get_guardrails(**kwargs):
        class _Broken:
            def redact_pii(self, t):
                raise RuntimeError("nope")

        return _Broken()

    grd.get_guardrails = fake_get_guardrails
    try:
        meta = co._build_handoff_meta("isha", 0, {"x": "abc"})
    finally:
        grd.get_guardrails = orig
    assert meta["from_agent"] == "isha"
    assert meta["seq"] == 0
    assert meta["context_preview"] == ""
