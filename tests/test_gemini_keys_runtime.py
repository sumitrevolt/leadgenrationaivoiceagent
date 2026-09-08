"""Runtime Gemini-key store — admin "Voice Keys" page persistence + voice-primary.

Locks: save_runtime_keys() persists + reloads so keys join the pool; voice_primary
flows to telecaller brain via the runtime store (no .env / restart needed).
"""

import json

from app.voice_agent import gemini_keys
from app.voice_agent.telecaller_brain import TelecallerBrain


def test_runtime_keys_save_and_pool(tmp_path, monkeypatch):
    monkeypatch.setattr(gemini_keys, "_RUNTIME_FILE", str(tmp_path / "vk.json"))
    gemini_keys.save_runtime_keys(
        ["AIzaTESTkey1", "AIzaTESTkey2", "AIzaTESTkey1"], voice_primary=True
    )
    assert gemini_keys.runtime_voice_primary() is True
    pool = gemini_keys.gemini_keys()
    assert "AIzaTESTkey1" in pool and "AIzaTESTkey2" in pool
    # dedupe held (the repeated key appears once)
    assert pool.count("AIzaTESTkey1") == 1
    # cleanup so the cached pool doesn't leak test keys into other tests
    monkeypatch.setattr(gemini_keys, "_RUNTIME_FILE", str(tmp_path / "empty.json"))
    gemini_keys.reload_keys()


def test_voice_gemini_primary_reads_runtime(tmp_path, monkeypatch):
    f = tmp_path / "vk2.json"
    f.write_text(json.dumps({"keys": [], "voice_primary": True}), encoding="utf-8")
    monkeypatch.setattr(gemini_keys, "_RUNTIME_FILE", str(f))
    monkeypatch.delenv("VOICE_GEMINI_PRIMARY", raising=False)
    assert TelecallerBrain._voice_gemini_primary() is True
    monkeypatch.setattr(gemini_keys, "_RUNTIME_FILE", str(tmp_path / "none.json"))
    gemini_keys.reload_keys()


def test_runtime_absent_is_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(gemini_keys, "_RUNTIME_FILE", str(tmp_path / "missing.json"))
    assert gemini_keys.runtime_voice_primary() is False
    gemini_keys.reload_keys()  # must not raise
