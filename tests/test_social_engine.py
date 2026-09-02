"""social_engine — native social-posting engine (own queue + providers + vault).

Bars:
- vault: token encrypt-at-rest roundtrip (Fernet if key, plaintext fallback).
- enqueue_publish -> durable job(s) queued; process_queue dispatches via provider.
- configured provider ok -> published; inert provider -> skipped (terminal, no endless retry).
- SOCIAL_ENGINE flag OFF -> process_queue inert.
- second drain claims 0 (idempotent).
Providers/DB stubbed; engine logic only.
"""

from __future__ import annotations

import asyncio

import pytest

from app.social_engine import engine, store, vault
from app.social_engine.base import PublishResult, SocialProvider


class _Fake(SocialProvider):
    name = "fake"

    def __init__(self):
        self.calls = []

    def configured(self, account=None):
        return True

    async def publish(self, req, account):
        self.calls.append(req.platform)
        return PublishResult(ok=True, platform="fake", post_id="P-1")


class _Inert(SocialProvider):
    name = "inert"

    def configured(self, account=None):
        return False

    async def publish(self, req, account):
        return PublishResult(ok=False, platform="inert", error="x")


@pytest.fixture
def iso(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "_PATH", str(tmp_path / "jobs.jsonl"))
    monkeypatch.setattr(vault, "_PATH", str(tmp_path / "tokens.jsonl"))
    monkeypatch.setattr(store, "_mirror", lambda job: None)  # hermetic (no DB side-effect)
    fake = _Fake()
    monkeypatch.setattr(engine, "_REGISTRY", {"fake": fake, "inert": _Inert()})
    monkeypatch.setenv("SOCIAL_ENGINE", "1")
    monkeypatch.delenv("SOCIAL_TOKEN_KEY", raising=False)
    return fake


def test_vault_roundtrip(iso):
    assert vault.put("c1", "instagram", "TOK", account_ref="ig9", meta={"p": 1})
    g = vault.get("c1", "instagram")
    assert g and g["token"] == "TOK" and g["account_ref"] == "ig9"


def test_enqueue_and_process_publishes(iso):
    ids = engine.enqueue_publish("c1", caption="hi", platforms=["fake"])
    assert len(ids) == 1
    out = asyncio.run(engine.process_queue())
    assert out["ran"] is True and out["published"] == 1
    assert "fake" in iso.calls
    assert any(j["status"] == "published" for j in store.list_jobs("c1"))


def test_inert_provider_skipped(iso):
    engine.enqueue_publish("c1", caption="hi", platforms=["inert"])
    out = asyncio.run(engine.process_queue())
    assert out["skipped"] == 1
    assert any(j["status"] == "skipped" for j in store.list_jobs("c1"))


def test_process_queue_flag_off_inert(iso, monkeypatch):
    monkeypatch.setenv("SOCIAL_ENGINE", "0")
    assert asyncio.run(engine.process_queue()) == {"ran": False, "reason": "SOCIAL_ENGINE off"}


def test_idempotent_second_drain(iso):
    engine.enqueue_publish("c1", caption="hi", platforms=["fake"])
    asyncio.run(engine.process_queue())
    out2 = asyncio.run(engine.process_queue())
    assert out2["claimed"] == 0


def test_celery_worker_registers_social_drain_task():
    from app.worker import celery_app

    assert "app.social_engine.tasks" in set(celery_app.conf.include or ())
    assert "social_engine.drain" in celery_app.tasks
