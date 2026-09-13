"""Fail-closed verification for the enterprise Telegram setup API.

Exercises the gating in ``app.api.telegram_setup`` WITHOUT a live server and
WITHOUT any network calls. The module is skipped cleanly if ``fastapi`` is not
installed in the active interpreter.
"""

import pytest

# Must run before importing the module under test (which imports fastapi).
pytest.importorskip("fastapi")

from app.api import telegram_setup as ts  # noqa: E402


def test_read_is_always_allowed(monkeypatch):
    """GET is always allowed; reflects spec + advertises write_enabled=False."""
    monkeypatch.delenv("TELEGRAM_SETUP_ENABLED", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    data = ts.read_setup()

    assert data["write_enabled"] is False
    n_product = sum(len(p.get("groups", [])) for p in data["products"])
    n_cross = len(data.get("cross_product", []))
    assert n_product + n_cross == 10


def test_patch_refused_when_disabled(monkeypatch):
    """PATCH edit is REFUSED with 403 unless TELEGRAM_SETUP_ENABLED == '1'."""
    monkeypatch.delenv("TELEGRAM_SETUP_ENABLED", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    with pytest.raises(Exception) as exc:
        ts.update_group("marketing.announcements", {"chat_id": "-100123"})

    assert exc.value.status_code == 403


def test_apply_refused_without_token(monkeypatch):
    """POST /apply is REFUSED with 503 when enabled but no bot token."""
    monkeypatch.setenv("TELEGRAM_SETUP_ENABLED", "1")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    with pytest.raises(Exception) as exc:
        ts.apply_setup()

    assert exc.value.status_code == 503


def test_find_group_mapping():
    """Group id resolution maps product.key and cross.key; unknown -> None."""
    spec = ts._load_spec()

    voice_support = ts._find_group(spec, "voice.support")
    assert voice_support is not None
    assert voice_support.get("key") == "support"

    cross_admin = ts._find_group(spec, "cross.internal_admin")
    assert cross_admin is not None
    assert cross_admin.get("key") == "internal_admin"

    assert ts._find_group(spec, "nope.unknown") is None
