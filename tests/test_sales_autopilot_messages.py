"""Sales Autopilot — message generation + deterministic safety validation."""

from __future__ import annotations

from app.platform.sales_autopilot import messages as messages
from app.platform.sales_autopilot import safety as safety


def _prospect(**over):
    base = {"id": "p-1", "name": "Glow Studio", "city": "Mumbai", "niche": "beauty_makeover"}
    base.update(over)
    return base


def test_initial_whatsapp_has_price_truth_and_optout():
    env = messages.build(_prospect(), channel="whatsapp", step="initial")
    assert str(messages.STARTER_PRICE_INR) in env["body"]
    assert "stop" in env["body"].lower()
    assert env["content_hash"]
    assert env["template_version"] == messages.TEMPLATE_VERSION


def test_initial_email_returns_subject():
    env = messages.build(_prospect(), channel="email", step="initial")
    assert env["subject"]
    assert "1999" in env["body"]


def test_safety_approves_clean_message():
    env = messages.build(_prospect(), channel="whatsapp", step="initial")
    v = safety.validate(env)
    assert v["status"] == safety.AUTO_APPROVED


def test_safety_rejects_banned_claim():
    env = messages.build(_prospect(), channel="whatsapp", step="initial")
    env["body"] = env["body"] + " We guarantee #1 results, 100% risk-free!"
    v = safety.validate(env)
    assert v["status"] == safety.AUTO_REJECTED
    assert any("banned_claim" in r for r in v["reasons"])


def test_safety_rejects_price_mismatch():
    env = messages.build(_prospect(), channel="whatsapp", step="initial")
    env["body"] = "Our Starter plan is Rs 499/month. Reply STOP to opt out."
    v = safety.validate(env)
    assert v["status"] == safety.AUTO_REJECTED
    assert any("price_mismatch" in r for r in v["reasons"])


def test_safety_rejects_missing_optout_on_outreach():
    env = messages.build(_prospect(), channel="whatsapp", step="initial")
    env["body"] = "Hi Glow Studio, we run AI marketing for beauty businesses at Rs 1999/month."
    v = safety.validate(env)
    assert v["status"] == safety.AUTO_REJECTED
    assert "missing_optout" in v["reasons"]


def test_safety_rejects_unfilled_placeholder():
    env = messages.build(_prospect(), channel="whatsapp", step="initial")
    env["body"] = "Hi {{name}}, reply STOP to opt out. Rs 1999/month."
    v = safety.validate(env)
    assert v["status"] == safety.AUTO_REJECTED
    assert "unfilled_placeholder" in v["reasons"]


def test_safety_error_fail_closed(monkeypatch):
    monkeypatch.setattr(safety, "_deterministic", lambda env: (_ for _ in ()).throw(ValueError()))
    v = safety.validate({"channel": "whatsapp", "body": "x"})
    assert v["status"] == safety.OWNER_EXCEPTION_REQUIRED


def test_name_injection_stripped():
    env = messages.build(_prospect(name="Evil {{x}} }"), channel="whatsapp", step="initial")
    assert "{{" not in env["body"] and "}}" not in env["body"]
