"""Interested-reply offer footer — the funnel's money step.

Regression cover for 2026-08-04: ``reply_agent._draft`` read ``os.environ["UPI_VPA"]``
directly, so a VPA armed at runtime through ``POST /api/admin/upi/configure``
(which writes ``data/platform_upi.json``, no restart) produced an interested-prospect
reply with NO payment instruction — while ``/api/public/pay-info`` and
``activation._payments_ready`` both reported UPI enabled off the same store.

Pure python: ``upi_config`` store path monkeypatched to tmp_path, no network/LLM.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """upi_config pointed at a tmp store, env VPA cleared."""
    from app.platform import upi_config as mod

    monkeypatch.setattr(mod, "_STORE", lambda: str(tmp_path / "platform_upi.json"))
    monkeypatch.delenv("UPI_VPA", raising=False)
    return mod


@pytest.fixture
def block():
    from app.platform.reply_agent import _interested_offer_block

    return _interested_offer_block


def test_dashboard_armed_vpa_reaches_the_offer(cfg, block):
    """THE regression: VPA armed via the admin store (not env) must still ship."""
    cfg.set_vpa("leadsgen@okhdfcbank", set_by="test")

    out = block("Sharma Salon")

    assert "leadsgen@okhdfcbank" in out, "dashboard-armed VPA missing from offer"
    assert "upi://pay?" in out


def test_env_vpa_still_wins(cfg, block, monkeypatch):
    """Existing .env deployments keep working — env is first in the resolver chain."""
    monkeypatch.setenv("UPI_VPA", "envvpa@ybl")

    out = block("Sharma Salon")

    assert "envvpa@ybl" in out


def test_unarmed_upi_appends_nothing(cfg, block):
    """Gating unchanged from the original: no VPA = no footer at all.

    The footer must stay conditional because `whatsapp_reply` drafts through the
    same `_draft`. Making it unconditional put a pricing line into WhatsApp
    replies that never carried one — caught by `test_wa_conversation` in CI.
    """
    assert block("Sharma Salon") == ""


def test_deeplink_carries_amount_from_packages(cfg, block):
    """Amount = billing-truth single source, never a hardcoded literal."""
    from app.marketing.packages import get_starter_price_inr

    cfg.set_vpa("leadsgen@okhdfcbank", set_by="test")

    out = block("Sharma Salon")

    assert f"am={get_starter_price_inr()}" in out
    assert "cu=INR" in out


def test_note_carries_business_name_for_reconciliation(cfg, block):
    """`tn` lets the owner match the bank credit back to a prospect."""
    cfg.set_vpa("leadsgen@okhdfcbank", set_by="test")

    out = block("Sharma Salon")

    assert "tn=LeadsGenAI%20Sharma%20Salon" in out


def test_business_name_is_url_quoted(cfg, block):
    """A business name with & / ? must not corrupt the deep-link query string."""
    cfg.set_vpa("leadsgen@okhdfcbank", set_by="test")

    out = block("A&B Salon?x")

    assert "&B Salon?x" not in out
    assert "%26B" in out


def test_never_raises_on_broken_config(cfg, block, monkeypatch):
    """Broken config behaves like unarmed — and must never lose the draft.

    `pricing` is bound after the VPA check, so returning it from the handler
    would UnboundLocalError and take the whole reply down with it.
    """

    def boom() -> str:
        raise RuntimeError("store unreadable")

    monkeypatch.setattr(cfg, "get_vpa", boom)

    assert block("Sharma Salon") == ""


@pytest.mark.asyncio
async def test_draft_appends_offer_only_for_interested(cfg, block, monkeypatch):
    """Wiring check: _draft appends the block for `interested`, not other intents."""
    from app.platform import reply_agent

    cfg.set_vpa("leadsgen@okhdfcbank", set_by="test")

    async def fake_chat(**kwargs):
        return "Namaste, dhanyavaad.", {}

    monkeypatch.setattr("app.voice_agent.free_ai.chat", fake_chat)

    hot = await reply_agent._draft("Sharma Salon", "re: audit", "interested hu", "interested")
    cold = await reply_agent._draft("Sharma Salon", "re: audit", "abhi nahi", "objection")

    assert "upi://pay?" in hot
    assert "upi://pay?" not in cold
