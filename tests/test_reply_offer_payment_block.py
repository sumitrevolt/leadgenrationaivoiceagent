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
    """upi_config pointed at a tmp store, with ALL THREE resolver sources cleared.

    ``get_vpa()`` resolves ``UPI_VPA`` env → ``settings.upi_vpa`` → data file.
    Clearing only env + file left the middle link live: ``app.config.settings`` is
    built by pydantic from the ``.env`` FILE at import time, so ``delenv`` cannot
    reach it. On any checkout whose ``.env`` carries a real VPA the "unarmed"
    precondition was never actually established and the store-armed VPA was
    shadowed — the absence-asserting tests failed for an environment reason, not
    a code reason (AGENT_WORK_RULES R4). Neutralise the whole chain here.
    """
    from app.config import settings
    from app.platform import upi_config as mod

    monkeypatch.setattr(mod, "_STORE", lambda: str(tmp_path / "platform_upi.json"))
    monkeypatch.delenv("UPI_VPA", raising=False)
    monkeypatch.setattr(settings, "upi_vpa", "", raising=False)
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


def test_settings_vpa_is_honoured_between_env_and_file(cfg, block, monkeypatch):
    """Locks the middle resolver link, which previously had NO coverage.

    ``get_vpa()`` documents ``env → settings → file``. Only env and file were
    exercised, so the settings branch was free to shadow a dashboard-armed VPA
    without any test noticing. Pin it: settings ships when env is absent.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "upi_vpa", "settingsvpa@ybl", raising=False)

    out = block("Sharma Salon")

    assert "settingsvpa@ybl" in out
    assert cfg.source() == "settings"


def test_settings_vpa_shadows_dashboard_armed_vpa(cfg, block, monkeypatch):
    """Documents a real operator trap so it cannot regress silently.

    ``set_vpa()`` writes the FILE, which is last in the chain. When a VPA also
    arrives via settings (a ``.env`` file entry that never reached the process
    environment), an admin can arm a new VPA, get ``ok: true`` back, and still
    have every payment surface serve the OLD one. Asserted as current behaviour,
    not endorsed — see the owner note in SESSION_HANDOFF.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "upi_vpa", "settingsvpa@ybl", raising=False)
    cfg.set_vpa("dashboard@okhdfcbank", set_by="test")

    out = block("Sharma Salon")

    assert "settingsvpa@ybl" in out
    assert "dashboard@okhdfcbank" not in out


def test_unarmed_upi_appends_nothing(cfg, block):
    """Gating unchanged from the original: no VPA = no footer at all.

    The footer must stay conditional because `whatsapp_reply` drafts through the
    same `_draft`. Making it unconditional put a pricing line into WhatsApp
    replies that never carried one — caught by `test_wa_conversation` in CI.
    """
    assert block("Sharma Salon") == ""


def test_deeplink_prefills_no_amount(cfg, block):
    """No `am=` — the plan is unknown here and the catalogue is multi-price.

    `_draft` gets no plan/deal binding, and the catalogue spans Marketing Main
    ₹1,999, Combo ₹5,999 and Voice bands ₹4,999/₹9,999/₹19,999. Prefilling the
    Starter price would give a Combo- or Voice-interested prospect a one-tap link
    that underpays their plan — a billing-truth break (CLAUDE.md §5). Locked so a
    later edit cannot silently re-add it without a real plan binding.
    """
    cfg.set_vpa("leadsgen@okhdfcbank", set_by="test")

    out = block("Sharma Salon")

    assert "am=" not in out
    assert "₹" not in out
    assert "Starter" not in out
    assert "cu=INR" in out
    assert "https://leadsgenai.in/pricing" in out  # plan choice stays on /pricing


def test_note_carries_business_name_as_context(cfg, block):
    """`tn` is human-readable context only — NOT a unique payment reference.

    No immutable prospect/deal/order id exists at this point in the state
    machine, so business name alone does not guarantee bank reconciliation.
    Open payment-automation gap, deliberately not papered over here.
    """
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
