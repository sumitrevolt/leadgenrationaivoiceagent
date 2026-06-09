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


# --------------------------------------------------------------------------- #
# Forward Deployed Engineer (FDE) agents
# --------------------------------------------------------------------------- #
def test_fde_registry():
    from app.agents import fde

    skills = fde.list_skills()
    cats = {s["category"] for s in skills}
    assert {"automation", "marketing", "website"} <= cats
    agents = {a["key"] for a in fde.list_agents()}
    assert {"isha_fde", "veer", "aarav", "neo"} <= agents
    neo = [a for a in fde.list_agents() if a["key"] == "neo"][0]
    assert len(neo["skills"]) >= 8  # full-stack covers all categories


def test_fde_deploy_website_skills():
    from app.agents import fde

    r = asyncio.run(
        fde.deploy(
            {"business_name": "Sharma Solar", "niche": "solar_residential", "city": "Pune", "slug": "sharma-solar-7b6f"},
            agent="veer",
            skills=["minisite", "embed_widget"],
        )
    )
    assert r["ok"] is True
    assert r["total"] == 2
    assert any(s["skill"] == "minisite" and s["ok"] for s in r["steps"])


# --------------------------------------------------------------------------- #
# Channels: SMS-DLT / LinkedIn / SEO pages / Cadence orchestrator
# --------------------------------------------------------------------------- #
def test_sms_dlt_inert(monkeypatch):
    from app.integrations import sms_dlt

    assert "audit" in sms_dlt.render("intro", biz="Sharma Solar").lower()
    monkeypatch.delenv("SMS_DLT_ENABLED", raising=False)
    r = asyncio.run(sms_dlt.send_template("+919999999999", "intro", biz="X"))
    assert r["ok"] is False and r.get("inert") is True


def test_linkedin_assist_drafts():
    from app.marketing import linkedin_assist

    d = asyncio.run(linkedin_assist.draft_outreach("Ravi", "Sharma Solar", "solar_residential"))
    assert d["ok"] and d["comment"] and d["connect_note"] and d["dm"]
    assert d["auto_sent"] is False


def test_seo_page_gen():
    from app.marketing import seo_pages

    p = asyncio.run(seo_pages.generate_page("ai_marketing", "Pune"))["page"]
    assert p["title"] and p["h1"] and len(p["faqs"]) >= 2
    assert p["schema"]["@type"] == "FAQPage" and p["cta"]["url"] == "/audit"


def test_cadence_orchestrator(tmp_path, monkeypatch):
    from app.marketing import cadence

    monkeypatch.setattr(cadence, "_LEADS", str(tmp_path / "cl.jsonl"))
    monkeypatch.setattr(cadence, "_RUNS", str(tmp_path / "cr.jsonl"))
    rec = cadence.enroll({"business_name": "Test", "phone": "+919876543210", "niche": "solar_residential", "city": "Pune"})
    assert rec["step_idx"] == 0
    assert cadence.enroll({"phone": "+919876543210"})["id"] == rec["id"]  # dedupe
    assert cadence.stats()["enrolled"] == 1
    monkeypatch.delenv("CADENCE_ENGINE", raising=False)
    assert asyncio.run(cadence.run_due())["ok"] is False  # gated off
    monkeypatch.setenv("CADENCE_ENGINE", "1")
    r = asyncio.run(cadence.run_due())
    assert r["ok"] is True and r["advanced"] >= 1  # day-0 steps fire


# --------------------------------------------------------------------------- #
# Telephony-free channels: partnerships / lead-tools / affiliate / community
# --------------------------------------------------------------------------- #
def test_partnerships():
    from app.marketing import partnerships

    assert len(partnerships.list_partner_types()) >= 5
    d = asyncio.run(partnerships.draft_partnership("ca", "ABC & Co", "Pune"))
    assert d["ok"] and d["pitch"] and d["auto_sent"] is False


def test_lead_tools():
    from app.marketing import lead_tools

    r = lead_tools.missed_call_revenue(5, 10000, 0.2)
    assert r["lost_per_month"] > 0 and r["cta"]["url"] == "/audit"
    s = lead_tools.lead_cost_savings(100, 50)
    assert s["savings_per_month"] >= 0
    g = asyncio.run(lead_tools.google_presence_score("Test", "Pune"))
    assert len(g["checklist"]) >= 4


def test_affiliate(tmp_path, monkeypatch):
    from app.marketing import affiliate

    monkeypatch.setattr(affiliate, "_AFFILIATES", str(tmp_path / "a.jsonl"))
    monkeypatch.setattr(affiliate, "_REFERRALS", str(tmp_path / "r.jsonl"))
    a = affiliate.register_affiliate("Ravi", "ravi@x.com")
    assert a["ok"] and a["code"] and a["link"]
    assert affiliate.register_affiliate("Ravi", "ravi@x.com")["code"] == a["code"]  # dedupe
    affiliate.record_referral(a["code"], {"business_name": "X", "amount": 999}, status="paid")
    st = affiliate.stats(a["code"])
    assert st["referrals"] == 1 and st["commission_earned"] > 0


def test_community_content():
    from app.marketing import community_content

    assert len(community_content.list_platforms()) >= 4
    c = asyncio.run(community_content.draft_content("quora", "leads", "real_estate"))
    assert c["ok"] and c["content"] and c["auto_posted"] is False


# --------------------------------------------------------------------------- #
# Sales automation: proposal / assistant / pipeline
# --------------------------------------------------------------------------- #
def test_proposal():
    from app.marketing import proposal

    r = asyncio.run(proposal.generate_proposal("Sharma Solar", "solar_residential", "Pune", "growth"))
    assert r["ok"] and r["proposal"]
    assert r["payment_link"].endswith("/pricing") and r["price_inr"] == 2499


def test_sales_assistant():
    from app.marketing import sales_assistant

    r = asyncio.run(sales_assistant.handle_message("bahut mehenga hai", "X", "real_estate"))
    assert r["ok"] and r["reply"] and r["cta_url"] and r["auto_sent"] is False


def test_sales_pipeline(tmp_path, monkeypatch):
    from app.marketing import sales_pipeline

    monkeypatch.setattr(sales_pipeline, "_DEALS", str(tmp_path / "d.jsonl"))
    monkeypatch.setattr(sales_pipeline, "_ACTIONS", str(tmp_path / "da.jsonl"))
    d = sales_pipeline.upsert_deal({"business_name": "X", "phone": "+919876543210", "niche": "solar_residential"}, "interested")
    assert d["stage"] == "interested"
    assert sales_pipeline.set_stage(d["id"], "demo_sent") is True
    deal = sales_pipeline.list_deals()[0]
    act = asyncio.run(sales_pipeline.next_action(deal))
    assert act["action"] == "send_proposal"  # demo_sent → proposal
    monkeypatch.delenv("SALES_ENGINE", raising=False)
    assert asyncio.run(sales_pipeline.run_pipeline())["ok"] is False  # gated off
    monkeypatch.setenv("SALES_ENGINE", "1")
    assert asyncio.run(sales_pipeline.run_pipeline())["ok"] is True


# --------------------------------------------------------------------------- #
# Security: per-IP rate-limit dependency (abuse/cost guard)
# --------------------------------------------------------------------------- #
def test_rate_limit_dependency(monkeypatch):
    import app.api.ratelimit as rl
    from fastapi import HTTPException

    class _Req:
        def __init__(self, headers, host="1.2.3.4"):
            self.headers = headers
            self.client = type("C", (), {"host": host})()

    # real client IP: X-Forwarded-For first, warna socket peer
    assert rl._client_ip(_Req({"x-forwarded-for": "9.9.9.9, 1.1.1.1"})) == "9.9.9.9"
    assert rl._client_ip(_Req({}, "5.5.5.5")) == "5.5.5.5"

    # limit cross -> 429
    state = {"n": 0}

    async def _fake_allowed(self, ident):
        state["n"] += 1
        return (state["n"] <= 2, 0)

    monkeypatch.setattr(rl.RateLimiter, "is_allowed", _fake_allowed)
    dep = rl.rate_limit("t", 2, 60)
    req = _Req({"x-forwarded-for": "8.8.8.8"})
    asyncio.run(dep(req))
    asyncio.run(dep(req))
    raised = 0
    try:
        asyncio.run(dep(req))
    except HTTPException as e:
        raised = e.status_code
    assert raised == 429

    # limiter error -> FAIL-OPEN (request block NA ho)
    async def _boom(self, ident):
        raise RuntimeError("redis down")

    monkeypatch.setattr(rl.RateLimiter, "is_allowed", _boom)
    asyncio.run(rl.rate_limit("t2", 1, 60)(_Req({}, "7.7.7.7")))  # no raise = pass
