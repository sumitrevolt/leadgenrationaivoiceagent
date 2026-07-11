"""Loop-social-3 (2026-07-11): SOCIAL_DRY_RUN=1 sandbox mode.

Contract:
- When `SOCIAL_DRY_RUN=1` is set, `_dispatch_one` returns a fabricated
  `PublishResult(ok=True, post_id="dry-<platform>-<jid>", raw={"dry_run":True})`
  WITHOUT calling the real provider.publish() method.
- Inert providers (configured() = False) STILL short-circuit to `__inert__`
  before dry-run — dry-run is not a way to spoof unconfigured accounts.
- With dry_run on + engine on, `process_queue` publishes to the ledger + admin
  cockpit as if the post went out.
- Dry-run is independent of the master `SOCIAL_ENGINE` gate — if the engine is
  OFF, `process_queue` still returns `{"ran": False, "reason": "SOCIAL_ENGINE off"}`
  and dry-run never fires. This preserves the operator's ability to test the
  ledger UI without accidentally starting the drain.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from app.social_engine import engine, store, vault
from app.social_engine.base import PublishResult, SocialProvider


class _Configured(SocialProvider):
    name = "configured"

    def __init__(self):
        self.publish_calls = 0

    def configured(self, account=None):
        return True

    async def publish(self, req, account):
        # If dry-run works this method NEVER gets called; guarded assertion below.
        self.publish_calls += 1
        return PublishResult(ok=True, platform="configured", post_id="REAL-PID")


class _Inert(SocialProvider):
    name = "inert"

    def __init__(self):
        self.publish_calls = 0

    def configured(self, account=None):
        return False

    async def publish(self, req, account):
        self.publish_calls += 1
        return PublishResult(ok=False, platform="inert", error="should not be called")


@pytest.fixture()
def dry(monkeypatch, tmp_path):
    """Isolated queue+vault + config file that turns dry-run OFF by default."""
    monkeypatch.setattr(store, "_PATH", str(tmp_path / "jobs.jsonl"))
    monkeypatch.setattr(vault, "_PATH", str(tmp_path / "tokens.jsonl"))
    monkeypatch.setattr(store, "_mirror", lambda job: None)
    cfg = tmp_path / "social_engine.json"
    cfg.write_text('{"enabled": true, "dry_run": false}', encoding="utf-8")
    monkeypatch.setenv("SOCIAL_ENGINE_CONFIG", str(cfg))
    monkeypatch.delenv("SOCIAL_ENGINE", raising=False)
    monkeypatch.delenv("SOCIAL_DRY_RUN", raising=False)
    monkeypatch.delenv("SOCIAL_TOKEN_KEY", raising=False)
    configured = _Configured()
    inert = _Inert()
    monkeypatch.setattr(engine, "_REGISTRY", {"configured": configured, "inert": inert})
    return {"configured": configured, "inert": inert, "cfg": cfg}


# --------------------------------------------------------------------------- #
# Dry-run flag semantics                                                       #
# --------------------------------------------------------------------------- #
def test_dry_run_disabled_by_default(dry, monkeypatch):
    assert engine._dry_run_enabled() is False


def test_dry_run_env_explicit_wins(dry, monkeypatch):
    monkeypatch.setenv("SOCIAL_DRY_RUN", "1")
    assert engine._dry_run_enabled() is True
    monkeypatch.setenv("SOCIAL_DRY_RUN", "0")
    assert engine._dry_run_enabled() is False


def test_dry_run_config_file_fallback(dry, monkeypatch):
    dry["cfg"].write_text('{"enabled": true, "dry_run": true}', encoding="utf-8")
    assert engine._dry_run_enabled() is True


# --------------------------------------------------------------------------- #
# Dispatch semantics                                                           #
# --------------------------------------------------------------------------- #
def test_dry_run_bypasses_real_provider_publish(dry, monkeypatch):
    monkeypatch.setenv("SOCIAL_ENGINE", "1")
    monkeypatch.setenv("SOCIAL_DRY_RUN", "1")
    ids = engine.enqueue_publish("c1", caption="dry", platforms=["configured"])
    assert len(ids) == 1
    out = asyncio.run(engine.process_queue())
    assert out["ran"] is True
    assert out["published"] == 1

    # The critical assertion: real .publish() must never be invoked.
    assert dry["configured"].publish_calls == 0

    rows = store.list_jobs("c1")
    published = [r for r in rows if r.get("status") == "published"]
    assert len(published) == 1
    pid = str(published[0].get("post_id") or "")
    assert pid.startswith("dry-configured-")


def test_dry_run_still_honors_inert_providers(dry, monkeypatch):
    """Inert providers (no creds) MUST still be skipped — dry-run is not a
    creds-spoof. Prevents ops accidentally believing an unconfigured provider
    was working just because dry-run was on."""
    monkeypatch.setenv("SOCIAL_ENGINE", "1")
    monkeypatch.setenv("SOCIAL_DRY_RUN", "1")
    engine.enqueue_publish("c1", caption="dry", platforms=["inert"])
    out = asyncio.run(engine.process_queue())
    assert out["skipped"] == 1
    assert dry["inert"].publish_calls == 0  # both dry-run and real bypassed


def test_dry_run_ineffective_when_engine_off(dry, monkeypatch):
    """Dry-run cannot secretly turn on drain when the master engine is off —
    process_queue must still return the SOCIAL_ENGINE off short-circuit."""
    monkeypatch.setenv("SOCIAL_ENGINE", "0")
    monkeypatch.setenv("SOCIAL_DRY_RUN", "1")
    engine.enqueue_publish("c1", caption="dry", platforms=["configured"])
    out = asyncio.run(engine.process_queue())
    assert out == {"ran": False, "reason": "SOCIAL_ENGINE off"}
    assert dry["configured"].publish_calls == 0
