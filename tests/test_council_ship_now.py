"""Council ship-now: trust config + trial banner helpers."""

from __future__ import annotations

import json
import os


def test_trust_turnstile_file_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("TURNSTILE_SECRET_KEY", raising=False)
    monkeypatch.delenv("TURNSTILE_SITE_KEY", raising=False)
    store = tmp_path / "data" / "trust_config.json"
    store.parent.mkdir(parents=True)
    store.write_text(
        '{"turnstile_site_key":"pk_test","turnstile_secret_key":"sk_test"}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    from app.platform import trust_config

    assert trust_config.get_turnstile_site_key() == "pk_test"
    assert trust_config.get_turnstile_secret() == "sk_test"
    st = trust_config.status()
    assert st["turnstile"]["armed"] is True


def test_posthog_file_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("POSTHOG_API_KEY", raising=False)
    monkeypatch.delenv("POSTHOG_HOST", raising=False)
    store = tmp_path / "data" / "posthog_config.json"
    store.parent.mkdir(parents=True)
    store.write_text(
        json.dumps({"posthog_api_key": "phc_real_key", "posthog_host": "https://us.i.posthog.com"}),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    from app.api.activation import _posthog
    from app.platform import posthog_config

    assert posthog_config.get_api_key() == "phc_real_key"
    assert posthog_config.get_host() == "https://us.i.posthog.com"
    st = posthog_config.status()
    assert st["armed"] is True
    assert _posthog()["status"] == "OK"


def test_trial_banner_expired():
    from app.api.customer_dashboard_builders import _trial_banner

    tb = _trial_banner(
        {"trial": True, "trial_expires": "2020-01-01T00:00:00+00:00"},
        has_paid_plan=False,
    )
    assert tb is not None
    assert tb.expired is True
    assert tb.show_pay_cta is True


def test_trial_banner_paid_skips():
    from app.api.customer_dashboard_builders import _trial_banner

    assert _trial_banner({"trial": True}, has_paid_plan=True) is None
