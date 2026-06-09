"""Tests for the 2026 feature batch (revenue / Expedify / growth modules).

Offline + isolated: koi network/keys nahi chahiye. free_ai keys ke bina ("","")
lautata (graceful), file-stores tmp_path pe monkeypatch hote. Async functions
asyncio.run() se test hote (pytest-asyncio plugin ki zaroorat nahi).
"""

import asyncio


# --------------------------------------------------------------------------- #
# lead_scoring
# --------------------------------------------------------------------------- #
def test_lead_scoring_hot_vs_cold():
    from app.platform import lead_scoring

    cold = {"status": "lost", "source": "import"}
    hot = {
        "status": "qualified",
        "source": "referral",
        "phone_verified": True,
        "email_verified": True,
        "email": "a@b.com",
        "qualification_data": "{}",
        "niche": "solar",
        "call_attempts": 1,
    }
    sc, sh = lead_scoring.score_lead(cold), lead_scoring.score_lead(hot)
    assert 0 <= sc <= 100 and 0 <= sh <= 100
    assert sh > sc
    comp = lead_scoring.score_components(hot)
    for key in ("status", "source", "verification", "recency", "qualification", "niche_fit", "engagement"):
        assert key in comp


def test_lead_scoring_rank_and_defensive():
    from app.platform import lead_scoring

    ranked = lead_scoring.rank([{"status": "new"}, {"status": "appointment", "source": "referral"}])
    assert ranked[0]["lead_score"] >= ranked[1]["lead_score"]
    # garbage input must not raise
    assert lead_scoring.score_lead({"call_attempts": "xx", "status": None}) >= 0
    assert isinstance(lead_scoring.is_hot(80), bool)


# --------------------------------------------------------------------------- #
# call_qualifier
# --------------------------------------------------------------------------- #
def test_qualifier_json_and_coerce():
    from app.voice_agent import call_qualifier

    parsed = call_qualifier._extract_json('junk {"interest_score": 7, "qualified": true} tail')
    assert parsed["interest_score"] == 7
    assert call_qualifier._extract_json("no json here") == {}
    c = call_qualifier._coerce({"interest_score": 99, "budget_signal": "weird", "qualified": "yes"})
    assert c["interest_score"] == 5  # clamped 0..5
    assert c["budget_signal"] == "unknown"
    assert isinstance(c["qualified"], bool)


def test_qualifier_async_fallback():
    from app.voice_agent import call_qualifier

    short = asyncio.run(call_qualifier.qualify_transcript("hi"))
    assert short["ok"] is False
    long = asyncio.run(
        call_qualifier.qualify_transcript("user: mujhe solar chahiye\nagent: budget kya hai?\nuser: 2 lakh")
    )
    assert long["followup_draft"]  # never empty (fallback)
    assert 0 <= long["interest_score"] <= 5


# --------------------------------------------------------------------------- #
# journeys
# --------------------------------------------------------------------------- #
def test_journeys_crud_and_match(tmp_path, monkeypatch):
    from app.marketing import journeys

    monkeypatch.setattr(journeys, "_JOURNEYS", str(tmp_path / "j.jsonl"))
    monkeypatch.setattr(journeys, "_RUNS", str(tmp_path / "r.jsonl"))
    assert journeys.seed_defaults() == 3
    assert len(journeys.list_journeys()) == 3
    j = journeys.add_journey("t", "inquiry_received", [{"type": "draft_whatsapp", "params": {}}], enabled=True)
    assert j["enabled"] is True
    assert journeys.set_enabled(j["id"], False) is True
    assert journeys.delete_journey(j["id"]) is True
    rule = {"enabled": True, "trigger": "signup", "condition": {"niche": "solar"}}
    assert journeys._matches(rule, "signup", {"niche": "solar"}) is True
    assert journeys._matches(rule, "signup", {"niche": "auto"}) is False
    assert journeys._matches(rule, "inquiry_received", {"niche": "solar"}) is False


def test_journeys_emit_gated(tmp_path, monkeypatch):
    from app.marketing import journeys

    monkeypatch.setattr(journeys, "_JOURNEYS", str(tmp_path / "j.jsonl"))
    monkeypatch.setattr(journeys, "_RUNS", str(tmp_path / "r.jsonl"))
    journeys.add_journey("t", "signup", [{"type": "notify", "params": {"text": "hi"}}], enabled=True)
    monkeypatch.delenv("JOURNEY_ENGINE", raising=False)
    assert asyncio.run(journeys.emit_event("signup", {})) == []  # gated off
    monkeypatch.setenv("JOURNEY_ENGINE", "1")
    runs = asyncio.run(journeys.emit_event("signup", {"business_name": "X"}))
    assert len(runs) == 1
    assert runs[0]["results"][0]["action"] == "notify"


# --------------------------------------------------------------------------- #
# review_engine (sentiment gate)
# --------------------------------------------------------------------------- #
def test_review_engine_sentiment_gate(tmp_path, monkeypatch):
    from app.marketing import review_engine

    monkeypatch.setattr(review_engine, "_STORE", str(tmp_path / "rev.jsonl"))
    happy = asyncio.run(review_engine.request_review("Sharma Solar", sentiment_score=5))
    assert happy["gate"] == "google_review"
    assert happy["message"]
    unhappy = asyncio.run(review_engine.request_review("Sharma Solar", customer_name="Ravi", sentiment_score=2))
    assert unhappy["gate"] == "private_feedback"
    assert unhappy["message"]


# --------------------------------------------------------------------------- #
# whatsapp_flows (scaffold, Meta-gated)
# --------------------------------------------------------------------------- #
def test_whatsapp_flows_inert_without_creds(monkeypatch):
    from app.marketing import whatsapp_flows

    assert whatsapp_flows.FLOW_LEAD_CAPTURE.get("version")
    assert whatsapp_flows.FLOW_LEAD_CAPTURE.get("screens")
    monkeypatch.delenv("WHATSAPP_LEAD_FLOW_ID", raising=False)
    res = asyncio.run(whatsapp_flows.send_flow("+919999999999"))
    assert res["ok"] is False
    assert res.get("inert") is True


# --------------------------------------------------------------------------- #
# missed_call (Vobiz-gated)
# --------------------------------------------------------------------------- #
def test_missed_call_gated(monkeypatch):
    from app.telephony import missed_call

    # avoid real side-effects (jsonl/db) — patch the lazily-imported savers
    import app.api.public_site as ps

    monkeypatch.setattr(ps, "_append_jsonl", lambda r: True, raising=False)
    monkeypatch.setattr(ps, "_save_lead_db", lambda r: None, raising=False)
    monkeypatch.delenv("MISSED_CALL_CALLBACK", raising=False)
    missed_call._RECENT.clear()
    res = asyncio.run(missed_call.handle_missed_call("+919888877777", "solar", "Test"))
    assert res["ok"] is True and res["callback"] is False  # lead captured, no callback (gated)
    assert asyncio.run(missed_call.handle_missed_call(""))["ok"] is False  # no number


# --------------------------------------------------------------------------- #
# customer_auth helpers (self-serve signup wiring)
# --------------------------------------------------------------------------- #
def test_customer_auth_helpers(tmp_path, monkeypatch):
    from app.api import customer_auth

    monkeypatch.setattr(customer_auth, "_STORE", str(tmp_path / "auth.jsonl"))
    assert customer_auth.login_exists("x@y.com") is False
    customer_auth.register_login("x@y.com", "secret123", "cid123")
    assert customer_auth.login_exists("x@y.com") is True
    assert customer_auth.client_has_login("cid123") is True
    assert customer_auth.client_has_login("nope") is False


# --------------------------------------------------------------------------- #
# niche_prospector (all-niche scraping rotation)
# --------------------------------------------------------------------------- #
def test_niche_prospector_targets(tmp_path, monkeypatch):
    from app.platform import niche_prospector

    monkeypatch.setattr(niche_prospector, "_CURSOR", str(tmp_path / "cur.json"))
    targets = niche_prospector.build_targets(batch=3, max_keywords=2)
    assert targets  # NICHES me keywords hain -> non-empty
    assert all(set(("niche", "query", "cities")).issubset(t) for t in targets)
    assert 1 <= len({t["niche"] for t in targets}) <= 3
    assert len(niche_prospector._all_niche_keys(tier="S")) >= 1
    # cursor rotation advances
    niche_prospector._write_cursor(5)
    assert niche_prospector._read_cursor() == 5


# --------------------------------------------------------------------------- #
# niche_pack (content_focus marketing pack helpers)
# --------------------------------------------------------------------------- #
def test_niche_pack_helpers():
    from app.marketing import niche_pack

    cfg = niche_pack._niche_cfg("ai_marketing")
    assert cfg.get("name")
    assert isinstance(niche_pack._derive_offer(cfg), str) and niche_pack._derive_offer(cfg)
    assert niche_pack._cta(cfg)
    assert niche_pack._derive_offer({}) == "Aaj hi shuru karo — pehle hafte me naye leads."
