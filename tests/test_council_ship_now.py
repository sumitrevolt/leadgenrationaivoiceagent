"""Council ship-now: trust config + trial banner helpers."""

from __future__ import annotations

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
