"""OPS-013 — the WhatsApp AI auto-reply flag must never be enabled silently.

Meta's WhatsApp Business API policy bars general-purpose AI chatbots. This agent
is task-scoped by construction, but `WHATSAPP_AI_AUTOREPLY=1` widens the drafted
intent set to include `other` (open-ended inbound -> open-ended LLM answer). That
is the only drift vector, so it gets a loud, quotable, testable warning.

These tests assert the WARNING exists — they do not change send behaviour.
"""

import pytest

from app.platform.reply_agent import autoreply_policy_warning


def test_off_is_silent(caplog):
    with caplog.at_level("WARNING"):
        assert autoreply_policy_warning(False) == ""
    assert "GENERAL-PURPOSE" not in caplog.text


def test_on_warns_loudly(caplog):
    with caplog.at_level("WARNING"):
        msg = autoreply_policy_warning(True)
    assert "GENERAL-PURPOSE AI chatbots" in msg
    assert "GENERAL-PURPOSE AI chatbots" in caplog.text


def test_warning_points_at_the_policy_and_the_flag():
    msg = autoreply_policy_warning(True)
    assert "WHATSAPP_AI_AUTOREPLY" in msg
    assert "OPS-013" in msg
    assert "ban" in msg.lower()


@pytest.mark.parametrize("enabled", [False, True])
def test_never_raises(enabled):
    assert isinstance(autoreply_policy_warning(enabled), str)
