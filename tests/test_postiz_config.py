"""Postiz runtime config — env -> encrypted-vault fallback (no-restart set) +
SOCIAL_ENGINE data-file fallback. Recreate-forbidden VPS pattern (upi_config)."""

import json
import sys
import types


def _mock_vault(
    monkeypatch, token="vk-123", api_url="https://postiz.leadsgenai.in/api", integrations="a1,b2"
):
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


# --------------------------------------------------------------------------- #
# ADR-099: status must report the EFFECTIVE resolved config, not one source.   #
# Regression pin: env-configured integrations were invisible to                #
# /social/postiz/status (reported 0) while publishing was fully wired.         #
# --------------------------------------------------------------------------- #


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


def test_status_counts_env_integrations_not_just_vault(monkeypatch):
    """The actual ADR-099 bug: vault meta empty + env set = status said 0."""
    from app.marketing import postiz_publish as pp

    # Mirrors prod at 2026-07-14: vault has key+url but integrations "".
    _mock_vault(monkeypatch, integrations="")
    monkeypatch.setenv("POSTIZ_INTEGRATIONS", "fb1,ig2,x3")
    monkeypatch.delenv("POSTIZ_API_URL", raising=False)

    effective = pp.effective_integration_ids()
    assert len(effective) == 3, "env-configured channels must be visible to status"
    assert pp.integrations_source() == "env"
    assert pp.api_url() == "https://postiz.leadsgenai.in/api"
    # publish_video() would proceed — status must not contradict that.
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
    assert "dry_run" in out
    assert out["dry_run"] is False
    assert "publish_proven" in out
    assert "queue_counts" in out


async def test_admin_status_reports_publish_proof(monkeypatch, tmp_path):
    from app.api import growth_automation as ga
    from app.marketing import postiz_publish as pp
    from app.social_engine import store

    _mock_vault(monkeypatch, integrations="fb1")
    monkeypatch.setenv("POSTIZ_INTEGRATIONS", "fb1")
    monkeypatch.setenv("SOCIAL_ENGINE", "1")
    jobs = tmp_path / "social_post_jobs.jsonl"
    jobs.write_text(
        '{"id":"j1","status":"published","post_id":"real-post-abc","updated_at":"2026-07-15T12:00:00"}\n'
    )
    monkeypatch.setattr(store, "_PATH", str(jobs))

    async def _fake_live():
        return {"ok": True, "channels": [], "youtube_refresh_needed": False}

    monkeypatch.setattr(pp, "live_integrations_summary", _fake_live)

    out = await ga.social_postiz_status(_user=None)
    assert out["publish_proven"] is True
    assert out["last_real_post_id"] == "real-post-abc"


def test_publish_proof_ignores_dry_run_ids(tmp_path, monkeypatch):
    from app.social_engine import store

    jobs = tmp_path / "social_post_jobs.jsonl"
    jobs.write_text(
        '{"id":"j1","status":"published","post_id":"dry-abc","updated_at":"2026-07-16"}\n'
        '{"id":"j2","status":"published","post_id":"cmr-real","updated_at":"2026-07-15"}\n'
    )
    monkeypatch.setattr(store, "_PATH", str(jobs))
    proof = store.publish_proof()
    assert proof["publish_proven"] is True
    assert proof["last_real_post_id"] == "cmr-real"


async def test_admin_status_reports_dry_run_when_env_set(monkeypatch):
    """ADR-098 class: dry_run must be visible on status (not omit → fake ready)."""
    from app.api import growth_automation as ga

    _mock_vault(monkeypatch, integrations="fb1")
    monkeypatch.setenv("POSTIZ_INTEGRATIONS", "fb1")
    monkeypatch.setenv("SOCIAL_ENGINE", "1")
    monkeypatch.setenv("SOCIAL_DRY_RUN", "1")

    out = await ga.social_postiz_status(_user=None)
    assert out["dry_run"] is True
    assert out["social_engine_enabled"] is True


def test_social_dry_run_in_automation_flags_registry():
    from app.api.automation_flags import AUTOMATION_FLAGS

    assert "SOCIAL_DRY_RUN" in AUTOMATION_FLAGS


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
            return _Response(
                [
                    {"id": "fb1", "identifier": "facebook"},
                    {"id": "x2", "identifier": "x"},
                ]
            )

        async def post(self, *args, **kwargs):
            seen.update(kwargs.get("json") or {})
            return _Response(
                [
                    {"postId": "post-fb-123", "integration": "fb1"},
                    {"postId": "post-x-456", "integration": "x2"},
                ]
            )

    monkeypatch.setitem(sys.modules, "httpx", types.SimpleNamespace(AsyncClient=_Client))
    monkeypatch.setenv("POSTIZ_API_KEY", "key")
    monkeypatch.setenv("POSTIZ_INTEGRATIONS", "fb1,x2")
    monkeypatch.delenv("POSTIZ_PUBLISH_MAX_CHANNELS", raising=False)
    monkeypatch.delenv("POSTIZ_PINTEREST_BOARD", raising=False)

    out = await pp.publish_video({}, "Launch proof", "")

    assert out["sent"] is True
    assert out["post_id"] == "post-fb-123"
    assert out["post_ids"] == ["post-fb-123", "post-x-456"]
    assert out["post_url"] == ""
    assert [p["settings"]["__type"] for p in seen["posts"]] == ["facebook", "x"]


# --------------------------------------------------------------------------- #
# Stage 2 closure: Pinterest Board + max-channels fail-safe selection
# --------------------------------------------------------------------------- #

_PLAT_MAP = {
    "fb1": "facebook",
    "ig1": "instagram",
    "li1": "linkedin",
    "yt1": "youtube",
    "pin1": "pinterest",
    "x1": "x",
}


def test_select_pinterest_included_when_board_set(monkeypatch):
    from app.marketing import postiz_publish as pp

    monkeypatch.setenv("POSTIZ_PINTEREST_BOARD", "board-abc")
    out = pp.select_publish_channels(["fb1", "pin1"], _PLAT_MAP, has_media=True, board="board-abc")
    assert out["ok"] is True
    assert out["channels"] == ["fb1", "pin1"]


def test_select_pinterest_skipped_when_board_missing():
    from app.marketing import postiz_publish as pp

    out = pp.select_publish_channels(["fb1", "pin1"], _PLAT_MAP, has_media=True, board="")
    assert out["ok"] is True
    assert out["channels"] == ["fb1"]
    assert any(s["reason"] == "POSTIZ_PINTEREST_BOARD_unset" for s in out["skipped"])


def test_select_skips_platforms_from_env(monkeypatch):
    """X credits-depleted etc. — operator can skip without rewriting integrations CSV."""
    from app.marketing import postiz_publish as pp

    monkeypatch.setenv("POSTIZ_SKIP_PLATFORMS", "x,youtube")
    out = pp.select_publish_channels(
        ["fb1", "x1", "yt1", "ig1"], _PLAT_MAP, has_media=True, board=""
    )
    assert out["ok"] is True
    assert out["channels"] == ["fb1", "ig1"]
    assert {s["reason"] for s in out["skipped"]} == {"POSTIZ_SKIP_PLATFORMS"}


def test_select_whitespace_board_treated_as_missing():
    from app.marketing import postiz_publish as pp

    out = pp.select_publish_channels(["pin1", "fb1"], _PLAT_MAP, has_media=True, board="   ")
    assert out["channels"] == ["fb1"]


def test_select_only_pinterest_without_board_blocks_zero_target():
    from app.marketing import postiz_publish as pp

    out = pp.select_publish_channels(["pin1"], _PLAT_MAP, has_media=True, board="")
    assert out["ok"] is False
    assert out["channels"] == []
    assert "Board-required" in out["reason"] or "PINTEREST" in out["reason"]


def test_select_max_channels_one_deterministic():
    from app.marketing import postiz_publish as pp

    out = pp.select_publish_channels(
        ["fb1", "ig1", "x1"], _PLAT_MAP, has_media=True, board="", max_channels=1
    )
    assert out["channels"] == ["fb1"]


def test_select_max_channels_two_deterministic():
    from app.marketing import postiz_publish as pp

    out = pp.select_publish_channels(
        ["fb1", "ig1", "x1"], _PLAT_MAP, has_media=True, board="", max_channels=2
    )
    assert out["channels"] == ["fb1", "ig1"]


def test_select_max_greater_than_available():
    from app.marketing import postiz_publish as pp

    out = pp.select_publish_channels(
        ["fb1", "x1"], _PLAT_MAP, has_media=True, board="", max_channels=9
    )
    assert out["channels"] == ["fb1", "x1"]


def test_select_max_zero_blocks(monkeypatch):
    from app.marketing import postiz_publish as pp

    monkeypatch.setenv("POSTIZ_PUBLISH_MAX_CHANNELS", "0")
    out = pp.select_publish_channels(
        ["fb1", "x1"], _PLAT_MAP, has_media=True, board="", max_channels=None
    )
    assert out["ok"] is False
    assert out["channels"] == []
    assert "0" in out["reason"]


def test_select_invalid_max_treated_uncapped(monkeypatch):
    from app.marketing import postiz_publish as pp

    monkeypatch.setenv("POSTIZ_PUBLISH_MAX_CHANNELS", "nope")
    assert pp._publish_max_channels() is None
    out = pp.select_publish_channels(
        ["fb1", "x1"], _PLAT_MAP, has_media=True, board="", max_channels=None
    )
    assert out["channels"] == ["fb1", "x1"]


def test_select_negative_max_blocks(monkeypatch):
    from app.marketing import postiz_publish as pp

    monkeypatch.setenv("POSTIZ_PUBLISH_MAX_CHANNELS", "-3")
    assert pp._publish_max_channels() == 0


def test_select_duplicate_ids_consume_one_slot():
    from app.marketing import postiz_publish as pp

    out = pp.select_publish_channels(
        ["fb1", "fb1", "x1"], _PLAT_MAP, has_media=True, board="", max_channels=2
    )
    assert out["channels"] == ["fb1", "x1"]


def test_select_order_deterministic():
    from app.marketing import postiz_publish as pp

    a = pp.select_publish_channels(
        ["x1", "fb1", "ig1"], _PLAT_MAP, has_media=True, board="", max_channels=3
    )
    b = pp.select_publish_channels(
        ["x1", "fb1", "ig1"], _PLAT_MAP, has_media=True, board="", max_channels=3
    )
    assert a["channels"] == b["channels"] == ["x1", "fb1", "ig1"]


def test_customer_does_not_inherit_env_integrations(monkeypatch):
    from app.marketing import postiz_publish as pp

    monkeypatch.setenv("POSTIZ_INTEGRATIONS", "fb1,ig1")
    jiya = {"id": "jiya-makeover", "business_name": "Jiya Makeover Studio"}
    assert pp.effective_integration_ids(jiya) == []
    own = {"id": "leadgenai-self"}
    assert pp.effective_integration_ids(own) == ["fb1", "ig1"]


def test_plan_publish_channels_read_only(monkeypatch):
    from app.marketing import postiz_publish as pp

    monkeypatch.setenv("POSTIZ_INTEGRATIONS", "fb1,pin1")
    monkeypatch.delenv("POSTIZ_PINTEREST_BOARD", raising=False)
    monkeypatch.setenv("POSTIZ_PUBLISH_MAX_CHANNELS", "1")
    plan = pp.plan_publish_channels(
        {"id": "leadgenai-self"},
        has_media=True,
        platform_map=_PLAT_MAP,
    )
    assert plan["configured"] == ["fb1", "pin1"]
    assert plan["selection"]["ok"] is True
    assert plan["selection"]["channels"] == ["fb1"]
    assert plan["pinterest_board_set"] is False


async def test_publish_video_skips_pinterest_without_board(monkeypatch):
    """Board-required channels must not 400 the whole multi-channel batch."""
    from app.marketing import postiz_publish as pp

    seen = {}
    posts_called = {"n": 0}

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
            return _Response(
                [
                    {"id": "fb1", "identifier": "facebook"},
                    {"id": "pin1", "identifier": "pinterest"},
                ]
            )

        async def post(self, *args, **kwargs):
            posts_called["n"] += 1
            seen.update(kwargs.get("json") or {})
            return _Response([{"postId": "post-fb-only", "integration": "fb1"}])

    monkeypatch.setitem(sys.modules, "httpx", types.SimpleNamespace(AsyncClient=_Client))
    monkeypatch.setenv("POSTIZ_API_KEY", "key")
    monkeypatch.setenv("POSTIZ_INTEGRATIONS", "fb1,pin1")
    monkeypatch.delenv("POSTIZ_PINTEREST_BOARD", raising=False)
    monkeypatch.delenv("POSTIZ_PUBLISH_MAX_CHANNELS", raising=False)

    out = await pp.publish_video({}, "Own-brand canary", "")

    assert out["sent"] is True
    assert out["channels"] == ["fb1"]
    assert [p["integration"]["id"] for p in seen["posts"]] == ["fb1"]
    assert posts_called["n"] == 1


async def test_publish_video_zero_target_skips_create_api(monkeypatch):
    from app.marketing import postiz_publish as pp

    posts_called = {"n": 0}

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
            return _Response([{"id": "pin1", "identifier": "pinterest"}])

        async def post(self, *args, **kwargs):
            posts_called["n"] += 1
            return _Response([])

    monkeypatch.setitem(sys.modules, "httpx", types.SimpleNamespace(AsyncClient=_Client))
    monkeypatch.setenv("POSTIZ_API_KEY", "key")
    monkeypatch.setenv("POSTIZ_INTEGRATIONS", "pin1")
    monkeypatch.delenv("POSTIZ_PINTEREST_BOARD", raising=False)

    out = await pp.publish_video({}, "Should not post", "")
    assert out["sent"] is False
    assert posts_called["n"] == 0


async def test_publish_video_respects_max_channels_cap(monkeypatch):
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
            return _Response(
                [
                    {"id": "fb1", "identifier": "facebook"},
                    {"id": "x2", "identifier": "x"},
                ]
            )

        async def post(self, *args, **kwargs):
            seen.update(kwargs.get("json") or {})
            return _Response([{"postId": "post-1"}])

    monkeypatch.setitem(sys.modules, "httpx", types.SimpleNamespace(AsyncClient=_Client))
    monkeypatch.setenv("POSTIZ_API_KEY", "key")
    monkeypatch.setenv("POSTIZ_INTEGRATIONS", "fb1,x2")
    monkeypatch.setenv("POSTIZ_PUBLISH_MAX_CHANNELS", "1")

    out = await pp.publish_video({}, "One-post canary", "")

    assert out["sent"] is True
    assert out["channels"] == ["fb1"]
    assert len(seen["posts"]) == 1


def test_social_publish_flag_blocks_gate(monkeypatch):
    from app.marketing.video_production import flags
    from app.marketing.video_production.publish_gate import assert_can_publish

    monkeypatch.setenv("VIDEO_PRODUCTION_ENABLED", "1")
    monkeypatch.setenv("VIDEO_SOCIAL_PUBLISH_ENABLED", "0")
    # re-read flags via env
    assert flags.social_publish_enabled() is False
    gate = assert_can_publish(
        {
            "status": "approved",
            "workflow_state": "APPROVED",
            "revision": 0,
            "approved_version": 0,
            "approval_id": "a1",
            "video_path": "data/reels/x.mp4",
            "final_approved": True,
        }
    )
    assert gate["ok"] is False
    assert "VIDEO_SOCIAL_PUBLISH_ENABLED" in gate["error"]


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


def test_integrations_postiz_exports():
    """Verify app.integrations.postiz exports match what celery tasks and admin expect."""
    from app.integrations.postiz import (
        BaseIntegrationClient,
        PostizClient,
        effective_integration_ids,
        enabled,
        integrations_source,
        plan_publish_channels,
        publish_video,
    )

    client = PostizClient()
    assert isinstance(client, BaseIntegrationClient)
    assert callable(client.auto_post)
    assert callable(enabled)
    assert callable(publish_video)
    assert callable(effective_integration_ids)
    assert callable(integrations_source)
    assert callable(plan_publish_channels)


def test_check_gates_status():
    """Verify check_gates returns expected dict with 'pass' values."""
    from app.platform.hot_queue_owner_pack import check_gates

    gates = check_gates()
    assert isinstance(gates, dict)
    assert gates.get("dnd_scrub") == "pass"
    assert gates.get("voice_window") == "pass"
    assert gates.get("kill_fence") == "pass"
    assert all(v == "pass" for v in gates.values())
