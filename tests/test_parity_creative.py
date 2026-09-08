"""Tests — Agent B creative features (jingle, bg_remove, multilang 9-lang,
creative router). No network, no DB, no LLM — sab defensive/pure paths
(style: test_marketing_upgrades.py)."""

from __future__ import annotations

import asyncio
import sys

from app.marketing import bg_remove, jingle, multilang_post


# ------------------------------- Jingle (F1) ------------------------------- #
def test_jingle_available_shape():
    av = jingle.available()
    assert set(av) == {"ffmpeg", "edge_tts", "ok"}
    assert av["ok"] == av["edge_tts"]  # ffmpeg optional


def test_jingle_safe_file_path_regex_locked(tmp_path, monkeypatch):
    monkeypatch.setattr(jingle, "_OUT_DIR", str(tmp_path))
    # traversal / junk → None
    assert jingle.safe_file_path("../../etc/passwd") is None
    assert jingle.safe_file_path("jingle_XYZ.mp3") is None
    assert jingle.safe_file_path("") is None
    # valid name but missing file → None
    assert jingle.safe_file_path("jingle_0123456789.mp3") is None
    # valid + exists → path
    f = tmp_path / "jingle_abcdef0123.mp3"
    f.write_bytes(b"x" * 200)
    assert jingle.safe_file_path("jingle_abcdef0123.mp3") == str(f)


def test_jingle_fallback_script_and_duration():
    s = jingle._fallback_script("solar", "Sharma Solar", "20% off", "hinglish")
    assert "Sharma Solar" in s and "20% off" in s
    # bina inputs bhi kabhi empty nahi
    assert jingle._fallback_script("", "", "", "hinglish")
    d = jingle.estimate_duration(s)
    assert d > 0
    assert jingle.estimate_duration("") == 0.0


def test_jingle_pick_voice():
    assert jingle.pick_voice("hinglish") == "hi-IN-SwaraNeural"
    assert jingle.pick_voice("tamil") == "ta-IN-PallaviNeural"
    assert jingle.pick_voice("unknown-lang") == "hi-IN-SwaraNeural"
    # explicit valid voice wins; junk voice ignored
    assert jingle.pick_voice("hindi", "mr-IN-AarohiNeural") == "mr-IN-AarohiNeural"
    assert jingle.pick_voice("hindi", "../evil; rm") == "hi-IN-SwaraNeural"


def test_jingle_missing_dep_error_dict(monkeypatch):
    monkeypatch.setattr(
        jingle, "available", lambda: {"ffmpeg": False, "edge_tts": False, "ok": False}
    )
    res = asyncio.run(jingle.generate_jingle("solar", "Test Biz"))
    assert res["ok"] is False and "error" in res


# ---------------------------- Background removal (F2) ---------------------- #
def test_bg_remove_empty_and_oversize():
    r1 = bg_remove.remove_bg(b"")
    assert isinstance(r1, dict) and r1["ok"] is False
    r2 = bg_remove.remove_bg(b"x" * (bg_remove._MAX_BYTES + 1))
    assert isinstance(r2, dict) and "8MB" in r2["error"]


def test_bg_remove_graceful_without_rembg(tmp_path, monkeypatch):
    monkeypatch.setattr(bg_remove, "_CACHE_DIR", str(tmp_path))
    monkeypatch.setitem(sys.modules, "rembg", None)  # force import fail
    assert bg_remove.available() is False
    res = bg_remove.remove_bg(b"fake-image-bytes")
    assert isinstance(res, dict) and res["ok"] is False and "rembg" in res["error"]


def test_bg_remove_cache_hit_skips_rembg(tmp_path, monkeypatch):
    monkeypatch.setattr(bg_remove, "_CACHE_DIR", str(tmp_path))
    monkeypatch.setitem(sys.modules, "rembg", None)  # rembg ABSENT — cache hi bachaye
    data = b"some-photo-bytes"
    cached = tmp_path / bg_remove._cache_name(data)
    cached.write_bytes(b"P" * 500)
    out = bg_remove.remove_bg(data)
    assert out == b"P" * 500  # bytes from cache, no rembg needed


# ---------------------------- Multilang 9x (F3) ----------------------------- #
def test_multilang_has_nine_langs_backward_compat():
    assert set(multilang_post.DEFAULT_LANGS) == {"hinglish", "hindi", "marathi"}
    for lg in ["gujarati", "telugu", "tamil", "bengali", "punjabi", "kannada"]:
        assert lg in multilang_post.LANGS
    assert len(multilang_post.LANGS) == 9
    assert multilang_post.supported_langs() == list(multilang_post.LANGS)


def test_multilang_empty_caption():
    res = asyncio.run(multilang_post.translate_post(""))
    assert res["ok"] is False


def test_multilang_default_stays_three(monkeypatch):
    import app.voice_agent.free_ai as free_ai

    async def fake_chat(system, messages, max_tokens=90, temperature=0.6):
        return "", ""  # LLM fail → original fallback

    monkeypatch.setattr(free_ai, "chat", fake_chat)
    res = asyncio.run(multilang_post.translate_post("Diwali offer 20% off!"))
    assert res["ok"] is True
    assert res["langs"] == ["hinglish", "hindi", "marathi"]  # growth.py caller unchanged
    assert all(v == "Diwali offer 20% off!" for v in res["versions"].values())


def test_multilang_new_langs_parsed(monkeypatch):
    import app.voice_agent.free_ai as free_ai

    async def fake_chat(system, messages, max_tokens=90, temperature=0.6):
        return '{"gujarati": "દિવાળી ઓફર!", "telugu": "దీపావళి ఆఫర్!"}', "fake"

    monkeypatch.setattr(free_ai, "chat", fake_chat)
    res = asyncio.run(
        multilang_post.translate_post("Diwali offer!", ["gujarati", "telugu", "badlang"])
    )
    assert res["ok"] is True
    assert res["langs"] == ["gujarati", "telugu"]  # unknown filtered
    assert res["versions"]["gujarati"] == "દિવાળી ઓફર!"
    assert res["versions"]["telugu"] == "దీపావళి ఆఫర్!"


# ------------------------------ Router (creative) --------------------------- #
def test_creative_router_shape():
    from app.api.creative import router

    assert router.prefix == "/creative"
    paths = {r.path for r in router.routes}
    assert "/creative/jingle" in paths
    assert "/creative/jingle-file/{name}" in paths
    assert "/creative/bg-remove" in paths
    assert "/creative/status" in paths
