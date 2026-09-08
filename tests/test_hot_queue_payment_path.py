"""BLK-01 (2026-08-22): calling_flagged Hot Queue cards me payment path.

Regression cover: high-intent cards pehle sirf free-audit pitch (precomputed
``wa_followup_link``) ya generic "reply karein" fallback bhejte the — warm lead
ke haath me UPI link nahi aata tha (BLK-01 root cause). Ab card builder
``_interested_offer_block`` ka offer+UPI footer embed karta hai:

- armed VPA  -> wa_link me original text + upi://pay footer dono
- unarmed    -> link BILKUL pehle jaisa (zero behaviour change)
- no followup link -> fallback message + footer

Pure python — upi_config store tmp_path pe, candidates monkeypatched.
"""

from __future__ import annotations

from urllib.parse import unquote_plus, urlparse

import pytest


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """upi_config resolver chain neutralised (env + settings + store → tmp)."""
    from app.config import settings
    from app.platform import upi_config as mod

    monkeypatch.setattr(mod, "_STORE", lambda: str(tmp_path / "platform_upi.json"))
    monkeypatch.delenv("UPI_VPA", raising=False)
    monkeypatch.setattr(settings, "upi_vpa", "", raising=False)
    return mod


def _wa_text(link: str) -> str:
    q = urlparse(link).query
    for part in q.split("&"):
        if part.startswith("text="):
            return unquote_plus(part[5:])
    return ""


def _build_cards(monkeypatch, candidate: dict) -> list[dict]:
    from app.platform import auto_outreach as ao
    from app.platform.reply_agent import _calling_flagged_cards

    monkeypatch.setattr(ao, "hot_queue_candidates", lambda limit=20: [candidate])
    return _calling_flagged_cards(limit=5, seen_from=set(), seen_phone=set())


@pytest.fixture
def flagged_candidate() -> dict:
    return {
        "id": "p_flag_blk01",
        "business_name": "AFM Solar",
        "phone": "9876543210",
        "email": "afm@test.in",
        "niche": "solar_residential",
        "city": "Pune",
        "status": "ready",
        "lead_score": 80,
        "reason": "calling_flagged",
        # Pre-computed audit pitch (asli prod shape — NO payment path).
        "wa_followup_link": (
            "https://wa.me/919876543210"
            "?text=Namaste+AFM+Solar+ji+%E2%80%94+free+Google+audit"
            "%3A+leadsgenai.in%2Faudit"
        ),
    }


def test_armed_vpa_appends_upi_to_followup_link(cfg, monkeypatch, flagged_candidate):
    """THE BLK-01 fix: audit-pitch link me UPI footer bhi aata hai."""
    cfg.set_vpa("leadsgen@okhdfcbank", set_by="test")

    cards = _build_cards(monkeypatch, flagged_candidate)

    assert cards, "card hi nahi bana"
    link = cards[0]["wa_link"]
    assert link.startswith("https://wa.me/919876543210?")
    txt = _wa_text(link)
    assert "free Google audit" in txt, "original audit pitch toot gaya"
    assert "upi://pay?" in txt, "UPI deep-link missing from WA draft"
    assert "leadsgen@okhdfcbank" in txt, "armed VPA missing from WA draft"


def test_unarmed_link_unchanged(cfg, monkeypatch, flagged_candidate):
    """Gating: VPA na ho to link byte-for-byte original rehta hai."""
    from app.platform import reply_agent as ra

    cards = _build_cards(monkeypatch, flagged_candidate)

    assert cards
    assert cards[0]["wa_link"] == flagged_candidate["wa_followup_link"]


def test_fallback_message_carries_offer_when_no_followup_link(cfg, monkeypatch):
    """No precomputed link -> generic Namaste msg + payment path dono."""
    cfg.set_vpa("leadsgen@okhdfcbank", set_by="test")
    cand = {
        "id": "p_flag_blk02",
        "business_name": "Savemax Solar",
        "phone": "9812345678",
        "email": "",
        "niche": "solar_residential",
        "city": "Pune",
        "reason": "calling_flagged",
    }

    cards = _build_cards(monkeypatch, cand)

    assert cards
    link = cards[0]["wa_link"]
    assert link.startswith("https://wa.me/919812345678?text=")
    txt = _wa_text(link)
    assert "Namaste Savemax Solar ji" in txt
    assert "upi://pay?" in txt


def test_no_offer_duplication_when_already_present(cfg, monkeypatch, flagged_candidate):
    """Followup text me offer pehle se ho to double-append nahi hota."""
    cfg.set_vpa("leadsgen@okhdfcbank", set_by="test")
    from app.platform.reply_agent import _interested_offer_block

    offer = _interested_offer_block("AFM Solar")
    flagged_candidate["wa_followup_link"] = "https://wa.me/919876543210?text=" + __import__(
        "urllib.parse", fromlist=["quote"]
    ).quote("Audit pitch." + offer)

    cards = _build_cards(monkeypatch, flagged_candidate)

    assert cards
    txt = _wa_text(cards[0]["wa_link"])
    assert txt.count("upi://pay?") == 1, "offer do baar append hua"
