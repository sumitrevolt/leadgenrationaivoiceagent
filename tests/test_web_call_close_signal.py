"""Landing-page voice onboarding -- close-signal -> in-page trial-signup
overlay. _close_signal_payload() decides whether to emit a WS close_signal
event so the browser can show the inline-signup overlay right in the call
session (instead of only via the WhatsApp handoff link). Flag-gated
WEBCALL_INLINE_SIGNUP, default OFF.
"""

from __future__ import annotations

from app.api.web_call import _close_signal_payload, _webcall_inline_signup_enabled


class _FakeBrain:
    def __init__(
        self,
        close_signal_fired=False,
        client_name="Demo Co",
        niche="ai_marketing",
        caller_phone="",
    ):
        self.close_signal_fired = close_signal_fired
        self.client_name = client_name
        self.niche = niche
        self.caller_phone = caller_phone


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("WEBCALL_INLINE_SIGNUP", raising=False)
    assert _webcall_inline_signup_enabled() is False


def test_flag_on(monkeypatch):
    monkeypatch.setenv("WEBCALL_INLINE_SIGNUP", "1")
    assert _webcall_inline_signup_enabled() is True


def test_payload_none_when_flag_off(monkeypatch):
    monkeypatch.delenv("WEBCALL_INLINE_SIGNUP", raising=False)
    brain = _FakeBrain(close_signal_fired=True, caller_phone="9876543210")
    assert _close_signal_payload(brain) is None


def test_payload_none_when_not_fired(monkeypatch):
    monkeypatch.setenv("WEBCALL_INLINE_SIGNUP", "1")
    brain = _FakeBrain(close_signal_fired=False)
    assert _close_signal_payload(brain) is None


def test_payload_built_when_flag_on_and_fired(monkeypatch):
    monkeypatch.setenv("WEBCALL_INLINE_SIGNUP", "1")
    brain = _FakeBrain(
        close_signal_fired=True,
        client_name="Glow Salon",
        niche="salon",
        caller_phone="9876543210",
    )
    payload = _close_signal_payload(brain)
    assert payload == {
        "type": "close_signal",
        "business_name": "Glow Salon",
        "niche": "salon",
        "phone": "9876543210",
    }
