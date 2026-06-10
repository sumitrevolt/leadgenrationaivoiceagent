"""Tests — sales_team batch (BANT qualify + 5-agent deep-dive), ai-sales-team adapt.
Convention: sync + asyncio.run, monkeypatch, no network/LLM (fallback paths)."""

from __future__ import annotations

import asyncio


def _prospect(**kw):
    base = {"name": "Sharma Solar", "niche": "solar", "city": "Pune", "phone": "+919812345678",
            "rating": 4.5, "reviews": 80, "website": "", "email": "x@sharma.in",
            "status": "interested", "source": "inquiry", "tier": "S"}
    base.update(kw)
    return base


# ----------------------------- BANT ----------------------------- #
def test_bant_dimensions_and_grade():
    from app.platform import sales_qualify as sq

    q = sq.bant_score(_prospect())
    assert 0 <= q["budget"] <= 25 and 0 <= q["authority"] <= 25
    assert 0 <= q["need"] <= 25 and 0 <= q["timeline"] <= 25
    assert q["total"] == q["budget"] + q["authority"] + q["need"] + q["timeline"]
    assert q["grade"] in ("A", "B", "C", "D") and q["action"]
    # strong prospect (busy + inbound + interested) should be A/B
    assert q["grade"] in ("A", "B")


def test_bant_weak_prospect_low_grade():
    from app.platform import sales_qualify as sq

    weak = {"name": "X", "rating": 0, "reviews": 0}
    q = sq.bant_score(weak)
    strong = sq.bant_score(_prospect())
    assert q["total"] < strong["total"]
    assert sq.grade_of(80) == "A" and sq.grade_of(60) == "B" and sq.grade_of(40) == "C" and sq.grade_of(10) == "D"


def test_bant_need_inverts_digital_gap():
    """No website / few reviews = HIGHER need (humara pitch) — US-B2B se ulta."""
    from app.platform import sales_qualify as sq

    no_site, _ = sq.score_need(_prospect(website="", reviews=3))
    has_site, _ = sq.score_need(_prospect(website="https://x.in", reviews=100))
    assert no_site > has_site


def test_bant_never_raises():
    from app.platform import sales_qualify as sq

    assert sq.bant_score({})["grade"] in ("A", "B", "C", "D")
    assert sq.bant_score({"rating": "garbage", "reviews": None})["total"] >= 0


# ----------------------------- sales_team ----------------------------- #
def _no_llm(monkeypatch):
    from app.agents import sales_team as st

    async def _empty(system, user, max_tokens=350):
        return ""

    monkeypatch.setattr(st, "_llm", _empty)
    return st


def test_sequence_fallback_pure():
    from app.agents import sales_team as st

    seq = st.build_sequence_fallback(_prospect())
    assert len(seq) == 5
    assert [s["day"] for s in seq] == ["1", "2", "7", "14", "21"]
    assert any(s["channel"] == "whatsapp" for s in seq)
    assert all("Sharma Solar" in s["draft"] or "ji" in s["draft"] for s in seq[:1])
    assert "audit" in seq[-1]["draft"]  # breakup = soft CTA


def test_objection_playbook_static():
    from app.agents import sales_team as st

    cats = {o["category"] for o in st.OBJECTION_PLAYBOOK}
    assert {"price", "competition", "timing", "trust"}.issubset(cats)
    assert all(o["laer"] for o in st.OBJECTION_PLAYBOOK)


def test_analyze_offline_fallbacks(tmp_path, monkeypatch):
    """LLM down + website nahi → phir bhi poora analysis + md report banta hai."""
    st = _no_llm(monkeypatch)
    monkeypatch.setattr(st, "_DIR", str(tmp_path))
    monkeypatch.setattr(st, "_INDEX", str(tmp_path / "index.jsonl"))
    r = asyncio.run(st.analyze(_prospect()))
    assert r["ok"] and r["grade"] in ("A", "B", "C", "D")
    md = open(r["md"], encoding="utf-8").read()
    assert "Prospect Analysis" in md and "Outreach sequence" in md and "Objection playbook" in md
    assert st.list_analyses(5)[0]["pid"] == r["pid"]
    assert st._already_done("+919812345678", None) is True


def test_run_auto_gate(monkeypatch):
    from app.agents import sales_team as st

    monkeypatch.delenv("SALES_TEAM", raising=False)
    assert asyncio.run(st.run_auto())["skipped"] == "SALES_TEAM off"
