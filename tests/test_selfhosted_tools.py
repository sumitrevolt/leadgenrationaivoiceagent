"""Self-hosted tools stack (SearXNG + ntfy) — gated/inert-without-env contract tests."""

import asyncio
import os

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("SEARXNG_URL", "NTFY_URL", "NTFY_TOPIC", "NTFY_TOKEN", "BRAVE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    yield


def test_searxng_inert_without_env():
    from app.integrations import searxng

    assert searxng.enabled() is False
    assert asyncio.run(searxng.search("solar pune")) == []
    assert asyncio.run(searxng.healthy()) is False


def test_searxng_enabled_flag(monkeypatch):
    from app.integrations import searxng

    monkeypatch.setenv("SEARXNG_URL", "http://127.0.0.1:1/")  # trailing slash strip
    assert searxng.enabled() is True
    assert searxng.base_url() == "http://127.0.0.1:1"
    # Unreachable host -> never raises, [] return
    assert asyncio.run(searxng.search("x")) == []


def test_ntfy_inert_without_env():
    from app.integrations import ntfy

    assert ntfy.enabled() is False
    assert asyncio.run(ntfy.push("t", "m")) is False
    ntfy.push_bg("t", "m")  # sync context = silent no-op, no raise


def test_ntfy_enabled_never_raises(monkeypatch):
    from app.integrations import ntfy

    monkeypatch.setenv("NTFY_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("NTFY_TOPIC", "leadgen-test")
    assert ntfy.enabled() is True
    # Unreachable -> False, no exception
    assert asyncio.run(ntfy.push("t", "m", priority="bogus", tags=["a", "b"])) is False


def test_harvester_websearch_status_reflects_searxng(monkeypatch):
    from app.platform import lead_harvester as lh

    st = lh.source_status()
    assert st["websearch"] is False
    monkeypatch.setenv("SEARXNG_URL", "http://searxng:8080")
    st2 = lh.source_status()
    assert st2["websearch"] is True


def test_harvester_websearch_inert_without_providers():
    from app.platform import lead_harvester as lh

    out = asyncio.run(lh._src_websearch("solar", "Pune", 5))
    assert out["leads"] == []
    assert "skipped" in out
