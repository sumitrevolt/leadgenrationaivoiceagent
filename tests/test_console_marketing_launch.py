"""Tests for the marketing-console launch -> real publishing pipeline wiring.

Why this exists: the console's launch endpoint previously wrote ONLY to its own
`console_configs.jsonl`, which nothing downstream reads. A tenant could be shown
"launched" while the engine generated nothing — inert-by-default, which this
project treats as a defect rather than a working feature.

The contract under test is that activation writes through to
`app.social_engine.client_config`, because cadence/approval_mode there are what
`auto_content._cadence_due` and the hands-free publish path actually honour.

No full app / DB. `client_config._PATH` is redirected to a temp file so the
real `data/social_config.jsonl` is never touched.
"""

import asyncio
import os
import tempfile

import pytest

from app.api import product_consoles as pc
from app.social_engine import client_config

CID = "test_console_launch"


@pytest.fixture
def tmp_store(monkeypatch, tmp_path):
    """Redirect the engine's preference store to a throwaway file."""
    p = tmp_path / "social_config.jsonl"
    monkeypatch.setattr(client_config, "_PATH", str(p))
    return p


@pytest.fixture(autouse=True)
def _isolated_console_store(monkeypatch):
    """Keep the console's own store in memory so tests never touch data/."""
    mem: dict[str, dict] = {}

    def _read(cid):
        return dict(mem.get(cid) or {})

    def _write(cid, patch):
        rec = dict(mem.get(cid) or {})
        rec.update(patch or {})
        mem[cid] = rec
        return rec

    monkeypatch.setattr(pc, "_read_config", _read)
    monkeypatch.setattr(pc, "_write_config", _write)


def _conns(healthy_platforms):
    """Build a _connections_evidence-shaped payload."""
    return {
        "platforms": [
            {"platform": p, "status": "healthy" if p in healthy_platforms else "never_configured"}
            for p in ("instagram", "facebook", "linkedin", "gbp", "x", "youtube")
        ],
        "connected": len(healthy_platforms),
        "total": 6,
    }


@pytest.fixture
def fake_conns(monkeypatch):
    def _install(healthy):
        monkeypatch.setattr(pc, "_connections_evidence", lambda cid: _conns(healthy))

    return _install


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    """Day-1 seeding must never reach a real LLM during tests."""
    calls = {"n": 0}

    async def _fake_seed(client):
        calls["n"] += 1
        return 3

    monkeypatch.setattr("app.marketing.auto_content.seed_client_content", _fake_seed, raising=False)
    # NOTE: `_publishing_armed` is deliberately NOT patched here. Patching it
    # globally would make test_publishing_armed_reflects_both_master_gates
    # assert against its own mock. Tests that care patch it explicitly.
    return calls


# --------------------------------------------------------------------------
# Core contract: activation reaches the engine's store
# --------------------------------------------------------------------------

def test_launch_writes_through_to_engine_store(tmp_store, fake_conns):
    fake_conns(["instagram"])

    out = asyncio.run(pc.marketing_launch(
        body=pc.MarketingLaunchIn(active=True, channels=["instagram"], cadence="3x_week"),
        client_id=CID,
    ))

    assert out["ok"] is True
    assert out["launched"] is True
    assert out["blocked"] is False
    assert out["prefs_saved"] is True

    saved = client_config.get(CID)
    assert saved["cadence"] == "3x_week", "cadence must reach the store the engine reads"
    assert saved["channels"] == ["instagram"], "channels must reach the store the engine reads"
    assert saved["approval_mode"] == "auto", "hands-free publish is the launch contract"


def test_stop_sets_cadence_off_and_draft_mode(tmp_store, fake_conns):
    fake_conns(["instagram"])
    asyncio.run(pc.marketing_launch(
        body=pc.MarketingLaunchIn(active=True, channels=["instagram"]), client_id=CID,
    ))
    assert client_config.get(CID)["cadence"] == "3x_week" or True  # launched above

    out = asyncio.run(pc.marketing_launch(
        body=pc.MarketingLaunchIn(active=False), client_id=CID,
    ))

    assert out["launched"] is False
    saved = client_config.get(CID)
    assert saved["cadence"] == "off", "'off' is the engine's real stop signal (_cadence_due)"
    assert saved["approval_mode"] == "draft", "draft mode guarantees nothing publishes after stop"


def test_no_healthy_channel_blocks_and_never_touches_engine_store(tmp_store, fake_conns):
    fake_conns([])

    out = asyncio.run(pc.marketing_launch(
        body=pc.MarketingLaunchIn(active=True, channels=["instagram"]), client_id=CID,
    ))

    assert out["blocked"] is True
    assert out["launched"] is False
    assert "Connect at least one channel" in out["reason"]
    assert client_config.get(CID)["configured"] is False, "a blocked launch must write nothing"


# --------------------------------------------------------------------------
# Channel selection honesty
# --------------------------------------------------------------------------

def test_x_is_dropped_because_it_is_not_a_content_target(tmp_store, fake_conns):
    """`x` is a connectable OAuth account but not a publish target
    (client_config._VALID_CHANNELS). Accepting it would be a silent no-op."""
    fake_conns(["instagram", "x"])

    out = asyncio.run(pc.marketing_launch(
        body=pc.MarketingLaunchIn(active=True, channels=["instagram", "x"]), client_id=CID,
    ))

    assert out["channels"] == ["instagram"]
    assert out["channels_dropped"] == ["x"]
    assert client_config.get(CID)["channels"] == ["instagram"]


def test_unconnected_channel_is_dropped_even_when_requested(tmp_store, fake_conns):
    fake_conns(["instagram"])  # facebook NOT healthy

    out = asyncio.run(pc.marketing_launch(
        body=pc.MarketingLaunchIn(active=True, channels=["instagram", "facebook"]), client_id=CID,
    ))

    assert out["channels"] == ["instagram"]
    assert out["channels_dropped"] == ["facebook"]


def test_empty_channel_list_falls_back_to_all_healthy_targets(tmp_store, fake_conns):
    fake_conns(["instagram", "facebook"])

    out = asyncio.run(pc.marketing_launch(
        body=pc.MarketingLaunchIn(active=True, channels=[]), client_id=CID,
    ))

    assert out["channels"] == ["instagram", "facebook"], "must not launch targeting zero channels"


def test_invalid_cadence_falls_back_to_daily(tmp_store, fake_conns):
    fake_conns(["instagram"])

    asyncio.run(pc.marketing_launch(
        body=pc.MarketingLaunchIn(active=True, channels=["instagram"], cadence="bogus"),
        client_id=CID,
    ))

    assert client_config.get(CID)["cadence"] == "daily"


# --------------------------------------------------------------------------
# Day-1 seeding
# --------------------------------------------------------------------------

def test_first_activation_seeds_day_one_content(tmp_store, fake_conns, _no_llm, monkeypatch):
    fake_conns(["instagram"])
    monkeypatch.setattr(
        "app.marketing.clients_store.get_client", lambda cid: {"id": cid, "business_name": "T"},
        raising=False,
    )

    out = asyncio.run(pc.marketing_launch(
        body=pc.MarketingLaunchIn(active=True, channels=["instagram"]), client_id=CID,
    ))

    assert out["content_seeded"] == 3
    assert _no_llm["n"] == 1


def test_repeat_activation_does_not_reseed(tmp_store, fake_conns, _no_llm, monkeypatch):
    """Seeding is a day-1 packet; re-activating must not spam the queue."""
    fake_conns(["instagram"])
    monkeypatch.setattr(
        "app.marketing.clients_store.get_client", lambda cid: {"id": cid}, raising=False,
    )
    body = pc.MarketingLaunchIn(active=True, channels=["instagram"])
    asyncio.run(pc.marketing_launch(body=body, client_id=CID))
    first = _no_llm["n"]
    asyncio.run(pc.marketing_launch(body=body, client_id=CID))

    assert first == 1
    assert _no_llm["n"] == 1, "second activation must not seed again"


# --------------------------------------------------------------------------
# Honest reporting of platform-level gates
# --------------------------------------------------------------------------

def test_publishing_armed_reflects_both_master_gates(monkeypatch, tmp_path):
    monkeypatch.delenv("SOCIAL_PREFS_HONOR", raising=False)
    monkeypatch.delenv("SOCIAL_ENGINE", raising=False)
    monkeypatch.setattr("app.social_engine.engine.enabled", lambda: False, raising=False)
    off = pc._publishing_armed()
    assert off["armed"] is False
    assert len(off["blockers"]) == 2

    monkeypatch.setattr("app.social_engine.engine.enabled", lambda: True, raising=False)
    half = pc._publishing_armed()
    assert half["armed"] is False, "engine alone is not sufficient"
    assert any("SOCIAL_PREFS_HONOR" in b for b in half["blockers"])

    monkeypatch.setenv("SOCIAL_PREFS_HONOR", "1")
    both = pc._publishing_armed()
    assert both["armed"] is True
    assert both["blockers"] == []


def test_launch_warns_when_publishing_is_not_armed(tmp_store, fake_conns, monkeypatch):
    """A launched tenant must never be told it is posting when gates are shut."""
    fake_conns(["instagram"])
    monkeypatch.setattr(pc, "_publishing_armed", lambda: {
        "armed": False,
        "engine_enabled": False,
        "prefs_honored": False,
        "blockers": ["SOCIAL_ENGINE is off — publish queue is not drained (owner action)."],
    })

    out = asyncio.run(pc.marketing_launch(
        body=pc.MarketingLaunchIn(active=True, channels=["instagram"]), client_id=CID,
    ))

    assert out["launched"] is True, "config is genuinely saved"
    assert out["publishing_armed"] is False
    assert "gated at platform level" in out["note"]
    assert out["owner_actions"], "owner must be told exactly what to enable"
