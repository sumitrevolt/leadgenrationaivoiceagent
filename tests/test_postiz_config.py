"""Postiz runtime config — env -> encrypted-vault fallback (no-restart set) +
SOCIAL_ENGINE data-file fallback. Recreate-forbidden VPS pattern (upi_config)."""

import json


def _mock_vault(monkeypatch, token="vk-123", api_url="https://postiz.leadsgenai.in/api", integrations="a1,b2"):
    from app.social_engine import vault

    monkeypatch.setattr(
        vault,
        "get",
        lambda client_id, platform, account_ref="": (
            {"token": token, "meta": {"api_url": api_url, "integrations": integrations}}
            if (client_id, platform) == ("_global", "postiz")
            else None
        ),
    )


def test_postiz_key_env_wins(monkeypatch):
    from app.marketing import postiz_publish as pp

    _mock_vault(monkeypatch)
    monkeypatch.setenv("POSTIZ_API_KEY", "env-key")
    assert pp._key() == "env-key"


def test_postiz_key_vault_fallback(monkeypatch):
    from app.marketing import postiz_publish as pp

    _mock_vault(monkeypatch)
    monkeypatch.delenv("POSTIZ_API_KEY", raising=False)
    assert pp._key() == "vk-123"
    assert pp.enabled() is True


def test_postiz_base_and_integrations_vault_fallback(monkeypatch):
    from app.marketing import postiz_publish as pp

    _mock_vault(monkeypatch)
    monkeypatch.delenv("POSTIZ_API_URL", raising=False)
    monkeypatch.delenv("POSTIZ_INTEGRATIONS", raising=False)
    assert pp._base() == "https://postiz.leadsgenai.in/api"
    assert pp._integration_ids(None) == ["a1", "b2"]


def test_postiz_inert_without_any_config(monkeypatch):
    from app.marketing import postiz_publish as pp
    from app.social_engine import vault

    monkeypatch.delenv("POSTIZ_API_KEY", raising=False)
    monkeypatch.setattr(vault, "get", lambda *a, **k: None)
    assert pp.enabled() is False


def test_social_engine_data_file_fallback(monkeypatch, tmp_path):
    from app.social_engine import engine

    cfg = tmp_path / "social_engine.json"
    cfg.write_text(json.dumps({"enabled": True}))
    monkeypatch.setenv("SOCIAL_ENGINE_CONFIG", str(cfg))
    monkeypatch.delenv("SOCIAL_ENGINE", raising=False)
    assert engine.enabled() is True
    # env "0" = hard kill even with file enabled
    monkeypatch.setenv("SOCIAL_ENGINE", "0")
    assert engine.enabled() is False
    # env "1" works without file
    monkeypatch.setenv("SOCIAL_ENGINE", "1")
    monkeypatch.setenv("SOCIAL_ENGINE_CONFIG", str(tmp_path / "absent.json"))
    assert engine.enabled() is True


def test_social_engine_off_when_nothing_set(monkeypatch, tmp_path):
    from app.social_engine import engine

    monkeypatch.delenv("SOCIAL_ENGINE", raising=False)
    monkeypatch.setenv("SOCIAL_ENGINE_CONFIG", str(tmp_path / "absent.json"))
    assert engine.enabled() is False
