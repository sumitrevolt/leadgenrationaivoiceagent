"""Postiz runtime config — env -> encrypted-vault fallback (no-restart set) +
SOCIAL_ENGINE data-file fallback. Recreate-forbidden VPS pattern (upi_config)."""

import json
import sys
import types


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


def test_effective_integration_ids_env_wins_over_vault(monkeypatch):
    from app.marketing import postiz_publish as pp

    _mock_vault(monkeypatch, integrations="vault1,vault2")
    monkeypatch.setenv("POSTIZ_INTEGRATIONS", "env1,env2,env3")
    assert pp.effective_integration_ids() == ["env1", "env2", "env3"]
    assert pp.integrations_source() == "env"


def test_effective_integration_ids_vault_fallback(monkeypatch):
    from app.marketing import postiz_publish as pp

    _mock_vault(monkeypatch, integrations="v1,v2")
    monkeypatch.delenv("POSTIZ_INTEGRATIONS", raising=False)
    assert pp.effective_integration_ids() == ["v1", "v2"]
    assert pp.integrations_source() == "vault"


def test_effective_integration_ids_client_record_wins(monkeypatch):
    from app.marketing import postiz_publish as pp

    _mock_vault(monkeypatch, integrations="v1")
    monkeypatch.setenv("POSTIZ_INTEGRATIONS", "env1")
    client = {"id": "acme", "postiz_integrations": "c1,c2"}
    assert pp.effective_integration_ids(client) == ["c1", "c2"]
    assert pp.integrations_source(client) == "client"


def test_integrations_source_none_when_unconfigured(monkeypatch):
    from app.marketing import postiz_publish as pp
    from app.social_engine import vault

    monkeypatch.delenv("POSTIZ_INTEGRATIONS", raising=False)
    monkeypatch.setattr(vault, "get", lambda *a, **k: None)
    assert pp.effective_integration_ids() == []
    assert pp.integrations_source() == "none"


def test_status_diagnostics_match_env_config(monkeypatch):
    from app.marketing import postiz_publish as pp

    _mock_vault(monkeypatch, integrations="")
    monkeypatch.setenv("POSTIZ_INTEGRATIONS", "fb1,ig2,x3")
    monkeypatch.delenv("POSTIZ_API_URL", raising=False)

    assert len(pp.effective_integration_ids()) == 3
    assert pp.integrations_source() == "env"
    assert pp.api_url() == "https://postiz.leadsgenai.in/api"
    assert pp.enabled() is True


async def test_admin_status_reports_effective_env_config(monkeypatch):
    from app.api import growth_automation as ga

    _mock_vault(monkeypatch, integrations="")
    monkeypatch.setenv("POSTIZ_INTEGRATIONS", "fb1,ig2,x3,y4")
    monkeypatch.setenv("SOCIAL_ENGINE", "1")

    out = await ga.social_postiz_status(_user=None)

    assert out["postiz_configured"] is True
    assert out["api_url_set"] is True
    assert out["integrations_count"] == 4
    assert out["integrations_source"] == "env"
    assert out["vault_integrations_count"] == 0
    assert out["social_engine_enabled"] is True


async def test_publish_video_preserves_postiz_post_ids(monkeypatch):
    from app.marketing import postiz_publish as pp

    seen = {}

    class _Response:
        status_code = 200
        text = ""

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            return _Response([
                {"id": "fb1", "identifier": "facebook"},
                {"id": "x2", "identifier": "x"},
            ])

        async def post(self, *args, **kwargs):
            seen.update(kwargs.get("json") or {})
            return _Response([
                {"postId": "post-fb-123", "integration": "fb1"},
                {"postId": "post-x-456", "integration": "x2"},
            ])

    monkeypatch.setitem(sys.modules, "httpx", types.SimpleNamespace(AsyncClient=_Client))
    monkeypatch.setenv("POSTIZ_API_KEY", "key")
    monkeypatch.setenv("POSTIZ_INTEGRATIONS", "fb1,x2")

    out = await pp.publish_video({}, "Launch proof", "")

    assert out["sent"] is True
    assert out["post_id"] == "post-fb-123"
    assert out["post_ids"] == ["post-fb-123", "post-x-456"]
    assert out["post_url"] == ""
    assert [p["settings"]["__type"] for p in seen["posts"]] == ["facebook", "x"]


async def test_postiz_provider_forwards_publish_evidence(monkeypatch):
    from app.marketing import clients_store, postiz_publish
    from app.social_engine.base import PublishRequest
    from app.social_engine.providers import PostizProvider

    monkeypatch.setattr(clients_store, "get_client", lambda _client_id: {})

    async def _publish(*args, **kwargs):
        return {
            "sent": True,
            "post_id": "post-123",
            "post_ids": ["post-123"],
            "post_url": "https://social.example/post-123",
        }

    monkeypatch.setattr(postiz_publish, "publish_video", _publish)
    result = await PostizProvider().publish(
        PublishRequest(client_id="leadgenai-self", caption="Launch proof", platform="postiz"),
        {},
    )

    assert result.ok is True
    assert result.post_id == "post-123"
    assert result.url == "https://social.example/post-123"
