"""GBP audit — heuristic + council suggestions (never auto-persist score)."""

from __future__ import annotations

import asyncio


def test_heuristic_suggest_conservative_without_facts():
    from app.marketing import gbp_audit

    out = gbp_audit.heuristic_suggest({})
    assert out["ok"] is True
    # empty profile → mostly worst indices
    assert out["answers"]["photos"] == gbp_audit._worst_idx("photos")
    assert out["answers"]["reviews_count"] == gbp_audit._worst_idx("reviews_count")


def test_heuristic_suggest_uses_gbp_and_phone():
    from app.marketing import gbp_audit

    out = gbp_audit.heuristic_suggest(
        {
            "gbp": "https://maps.google.com/?cid=1",
            "phone": "9876543210",
            "website": "https://example.com",
            "services": "Bridal makeup",
            "city": "Nagpur",
            "niche": "salon",
        }
    )
    assert out["answers"]["claimed"] == 1  # mid, not best
    assert out["answers"]["contact"] == 0
    assert out["answers"]["services"] == 1


def test_parse_council_gbp_answers():
    from app.marketing import gbp_audit

    text = """
Some chatter
Q_claimed: 1
Q_photos: 99
Q_bogus: 0
CONFIDENCE: medium
WHY: conservative
"""
    parsed = gbp_audit.parse_council_gbp_answers(text)
    assert parsed["claimed"] == 1
    assert parsed["photos"] == gbp_audit._clamp_idx("photos", 99)


def test_decide_gbp_suggest_does_not_claim_persisted(monkeypatch):
    from app.platform import boss_council

    async def fake_council(q):
        return {
            "ok": True,
            "stage3": {
                "response": "Q_claimed: 1\nQ_contact: 0\nCONFIDENCE: low\nWHY: seeds\nNEXT: open GBP"
            },
            "metadata": {"members_used": 2},
        }

    monkeypatch.setattr(boss_council, "_run_council", fake_council)
    out = asyncio.run(
        boss_council.decide_gbp_suggest(
            {"id": "jiya-makeover", "gbp": "https://g.page/x", "phone": "9999999999"}
        )
    )
    assert out["ok"] is True
    assert out.get("persisted") is False
    assert out["answers"]["claimed"] == 1


def test_gbp_council_prompt_redacts_phone():
    from app.marketing import gbp_audit
    from app.platform import boss_council

    raw_phone = "9876543210"
    client = {
        "business_name": "Jiya Makeover",
        "phone": raw_phone,
        "whatsapp_phone": "9123456789",
        "email": "owner@example.com",
        "niche": "salon",
        "city": "Nagpur",
    }
    heur = gbp_audit.heuristic_suggest(client)
    prompt = boss_council._gbp_question(client, heur)
    assert raw_phone not in prompt
    assert "9123456789" not in prompt
    assert "XXXX3210" in prompt or "[PHONE REDACTED]" in prompt
    assert "Jiya Makeover" not in prompt
    assert "J***" in prompt
