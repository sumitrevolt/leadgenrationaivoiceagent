"""F4 "Subah ki Briefing" — daily Hinglish HQ bulletin (text + Swara audio).

Bars:
- Happy path: real numbers collected + LLM compose -> text cites them, json cached.
- Cache: second call (not force) reads cache, does NOT re-invoke the LLM.
- force=True: regenerates (LLM called again).
- LLM raises -> deterministic template fallback still contains the real numbers,
  ok:True (never-raise degrade).
- TTS raises -> has_audio False, text still returned + cached.
- Endpoints admin-gated (401/403 without auth).

All cache IO monkeypatched to tmp_path so nothing writes into real data/.
"""

from __future__ import annotations

import asyncio
import os

import pytest
from starlette.testclient import TestClient

from app.api.auth_deps import get_current_user, require_admin
from app.main import app
from app.platform import office_briefing as ob

client = TestClient(app)


# --------------------------------------------------------------------------- #
# Fixtures — isolate cache dir + freeze the collected numbers so assertions can
# check that the exact real numbers land in the bulletin text.
# --------------------------------------------------------------------------- #
FAKE_NUMS = {
    "overdue_jobs": 2,
    "failed_jobs": 3,
    "dlq_depth": 3,
    "hot_queue": 7,
    "new_leads": 11,
    "qualified_leads": 4,
    "top_agents": [{"name": "Isha", "count": 9}, {"name": "Rohan", "count": 5}],
}


@pytest.fixture()
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(ob, "_DIR", str(tmp_path))
    monkeypatch.setattr(ob, "_collect_numbers", lambda: dict(FAKE_NUMS))
    return tmp_path


def _run(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        return asyncio.get_event_loop().run_until_complete(coro)


# --------------------------------------------------------------------------- #
# (a) happy path — LLM compose, numbers cited, json cached.
# --------------------------------------------------------------------------- #
def test_compose_happy_path_caches_json(cache_dir, monkeypatch):
    calls = {"llm": 0, "tts": 0}

    async def _fake_chat(system, messages, **kw):
        calls["llm"] += 1
        # Echo the numbers so the assertion can find them (a real LLM would too).
        return ("Aaj 11 naye leads, 4 qualified. Hot Queue me 7 pending.", "mistral")

    async def _fake_tts(text, path):
        calls["tts"] += 1
        with open(path, "wb") as f:
            f.write(b"ID3fakeaudio")
        return True

    monkeypatch.setattr("app.voice_agent.free_ai.chat", _fake_chat)
    monkeypatch.setattr(ob, "_tts_to_file", _fake_tts)

    out = _run(ob.build_briefing(force=False))
    assert out["ok"] is True
    assert out["has_audio"] is True
    assert "11" in out["text"] and "7" in out["text"]
    assert calls["llm"] == 1 and calls["tts"] == 1
    # json + mp3 both cached under tmp cache dir
    date = out["date"]
    assert os.path.exists(os.path.join(str(cache_dir), f"{date}.json"))
    assert os.path.exists(os.path.join(str(cache_dir), f"{date}.mp3"))


# --------------------------------------------------------------------------- #
# (b) second call reads cache — LLM invoked once total.
# --------------------------------------------------------------------------- #
def test_second_call_reads_cache(cache_dir, monkeypatch):
    calls = {"llm": 0}

    async def _fake_chat(system, messages, **kw):
        calls["llm"] += 1
        return ("11 naye leads aaye aaj.", "mistral")

    async def _fake_tts(text, path):
        with open(path, "wb") as f:
            f.write(b"audio")
        return True

    monkeypatch.setattr("app.voice_agent.free_ai.chat", _fake_chat)
    monkeypatch.setattr(ob, "_tts_to_file", _fake_tts)

    first = _run(ob.build_briefing(force=False))
    second = _run(ob.build_briefing(force=False))
    assert calls["llm"] == 1  # cache hit — no second LLM call
    assert second["cached"] is True
    assert second["text"] == first["text"]
    assert second["has_audio"] is True  # re-derived from disk mp3


# --------------------------------------------------------------------------- #
# (c) force=True regenerates (LLM called again).
# --------------------------------------------------------------------------- #
def test_force_regenerates(cache_dir, monkeypatch):
    calls = {"llm": 0}

    async def _fake_chat(system, messages, **kw):
        calls["llm"] += 1
        return (f"call number {calls['llm']}: 11 leads.", "mistral")

    async def _fake_tts(text, path):
        with open(path, "wb") as f:
            f.write(b"audio")
        return True

    monkeypatch.setattr("app.voice_agent.free_ai.chat", _fake_chat)
    monkeypatch.setattr(ob, "_tts_to_file", _fake_tts)

    _run(ob.build_briefing(force=False))
    out2 = _run(ob.build_briefing(force=True))
    assert calls["llm"] == 2  # forced regen
    assert out2["cached"] is False
    assert "call number 2" in out2["text"]


# --------------------------------------------------------------------------- #
# (d) LLM raises -> template fallback still cites the real numbers, ok:True.
# --------------------------------------------------------------------------- #
def test_llm_fail_template_fallback(cache_dir, monkeypatch):
    async def _boom_chat(system, messages, **kw):
        raise RuntimeError("all providers down")

    async def _fake_tts(text, path):
        with open(path, "wb") as f:
            f.write(b"audio")
        return True

    monkeypatch.setattr("app.voice_agent.free_ai.chat", _boom_chat)
    monkeypatch.setattr(ob, "_tts_to_file", _fake_tts)

    out = _run(ob.build_briefing(force=True))
    assert out["ok"] is True
    # template embeds the raw numbers literally
    assert "11" in out["text"] and "4" in out["text"] and "7" in out["text"]
    assert "Isha" in out["text"]  # top agent surfaced


# --------------------------------------------------------------------------- #
# (e) TTS raises -> has_audio False, text still returned + cached.
# --------------------------------------------------------------------------- #
def test_tts_fail_text_only(cache_dir, monkeypatch):
    async def _fake_chat(system, messages, **kw):
        return ("11 naye leads aaye.", "mistral")

    async def _boom_tts(text, path):
        raise RuntimeError("edge tts 403")

    monkeypatch.setattr("app.voice_agent.free_ai.chat", _fake_chat)
    monkeypatch.setattr(ob, "_tts_to_file", _boom_tts)

    out = _run(ob.build_briefing(force=True))
    assert out["ok"] is True
    assert out["has_audio"] is False
    assert "11" in out["text"]
    date = out["date"]
    assert os.path.exists(os.path.join(str(cache_dir), f"{date}.json"))
    assert not os.path.exists(os.path.join(str(cache_dir), f"{date}.mp3"))


# --------------------------------------------------------------------------- #
# (e2) TTS HANGS -> asyncio.wait_for(_TTS_TIMEOUT_S) bounds it: has_audio False,
# text still returned + cached (regression guard for the reviewer-confirmed
# unbounded-EdgeTTS-on-request-hot-path defect — prod-down class).
# --------------------------------------------------------------------------- #
def test_tts_hang_is_bounded_text_only(cache_dir, monkeypatch):
    async def _fake_chat(system, messages, **kw):
        return ("11 naye leads aaye.", "mistral")

    async def _hang_tts(text, path):
        await asyncio.sleep(5)  # simulates an EdgeTTS network stall
        return True

    monkeypatch.setattr("app.voice_agent.free_ai.chat", _fake_chat)
    monkeypatch.setattr(ob, "_tts_to_file", _hang_tts)
    monkeypatch.setattr(ob, "_TTS_TIMEOUT_S", 0.05)

    out = _run(ob.build_briefing(force=True))
    assert out["ok"] is True
    assert out["has_audio"] is False  # bounded, degraded to text-only
    assert "11" in out["text"]
    date = out["date"]
    assert os.path.exists(os.path.join(str(cache_dir), f"{date}.json"))


# --------------------------------------------------------------------------- #
# (f) endpoints admin-gated. conftest globally overrides the admin dep — pop it
# to exercise the real gate, then restore (documented "mocked-open" lesson).
# --------------------------------------------------------------------------- #
def test_briefing_endpoint_requires_admin():
    saved_admin = app.dependency_overrides.pop(require_admin, None)
    saved_user = app.dependency_overrides.pop(get_current_user, None)
    try:
        r = client.get("/api/platform/office/briefing")
        assert r.status_code in (401, 403)
        r2 = client.get("/api/platform/office/briefing/audio")
        assert r2.status_code in (401, 403)
    finally:
        if saved_admin is not None:
            app.dependency_overrides[require_admin] = saved_admin
        if saved_user is not None:
            app.dependency_overrides[get_current_user] = saved_user


def test_briefing_audio_missing_is_404_safe(tmp_path, monkeypatch):
    """Admin authed (conftest mock) + no cached mp3 -> 404 JSON, never 500."""
    monkeypatch.setattr(ob, "_DIR", str(tmp_path))
    r = client.get("/api/platform/office/briefing/audio")
    assert r.status_code == 404
    assert r.json()["ok"] is False
