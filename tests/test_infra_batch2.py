"""Tests — infra batch-2 (telephony readiness, queue guard, new agents, ops page)."""

from __future__ import annotations

import asyncio

from tests._api_helpers import iter_mounted_routes


def test_telephony_readiness_checks(monkeypatch):
    from app.telephony import telephony_readiness as tr

    res = tr.run_checks()
    assert 0 <= res["score"] <= 100
    # Provider-agnostic check keys (refactor: vobiz default; exotel_creds only when
    # TELEPHONY_PROVIDER=exotel). caller_id is the provider's DID-cred dimension.
    assert "caller_id" in res["checks"] and "tts_edge" in res["checks"]
    assert "llm_chain" in res["checks"] and "stt_groq" in res["checks"]
    assert isinstance(res["actions"], list) and res["actions"]
    # creds unset env me -> missing me dikhe (defensive: config fallback ho sakta)
    assert isinstance(res["missing"], list)


def test_telephony_readiness_watch_never_raises(tmp_path, monkeypatch):
    from app.telephony import telephony_readiness as tr

    monkeypatch.setattr(tr, "_LOG", str(tmp_path / "tel.jsonl"))
    monkeypatch.delenv("TELEPHONY_READY_ALERTS", raising=False)
    out = asyncio.run(tr.run_watch())
    assert "score" in out
    out2 = asyncio.run(tr.run_watch())  # second run = prev_score compare path
    assert "score" in out2


def test_queue_depth_defensive_and_health_shape(tmp_path, monkeypatch):
    from app.platform import automation_health as ah

    monkeypatch.setattr(ah, "_RUNS", lambda: str(tmp_path / "r.jsonl"))
    monkeypatch.setattr(ah, "_BEATS", lambda: str(tmp_path / "b.json"))
    q = ah.queue_depth()  # Redis na ho -> -1, kabhi raise nahi
    # contract: core keys hamesha; extra queues (heavy/dead) additive allowed
    assert {"celery", "dlq"}.issubset(set(q.keys()))
    h = ah.health()
    assert "queue" in h and "queue_backlogged" in h


def test_new_staff_in_roster():
    from app.platform.team import STAFF

    assert "tara" in STAFF and STAFF["tara"]["title"] == "Voice Infra Ops"
    assert "nikhil" in STAFF and "Revenue" in STAFF["nikhil"]["title"]
    assert len(STAFF) >= 12  # 8 original + tara/nikhil + guru/vikram (roster grows)


def test_ops_routes_registered():
    from app.api.growth import router

    paths = {r.path for r in iter_mounted_routes(router)}
    assert "/growth/infra/telephony-readiness" in paths
    assert "/growth/revenue/summary" in paths
    assert "/growth/inbox" in paths
    # /app/ops page route main.py me hai — yahan growth API hi check


def test_utm_attribution_mapping(tmp_path, monkeypatch):
    """Inquiry utm_source → channel outcome auto-record (bandit attribution)."""
    from app.marketing import channel_experiments as ce

    monkeypatch.setattr(ce, "_RUNS", str(tmp_path / "r.jsonl"))
    monkeypatch.setattr(ce, "_OUTCOMES", str(tmp_path / "o.jsonl"))
    # public_site ke _UTM_MAP jaisa mapping — direct record path verify
    r = ce.record_outcome("quora", "inquiry", 1, "utm:quora")
    assert r["ok"] is True and r["stats"]["outcomes"] == 1


def test_inquiry_model_has_utm():
    from app.api.public_site import InquiryIn

    assert "utm_source" in InquiryIn.model_fields
