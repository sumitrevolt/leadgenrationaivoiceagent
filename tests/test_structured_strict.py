"""Pure-python tests for the strict-first json_schema path in app.llm.structured.

No network/LLM/DB: we inject fake ``instructor`` + ``openai`` modules into
sys.modules so the never-raise fallback chain (strict json_schema -> Mode.JSON ->
None) can be asserted deterministically.
"""

from __future__ import annotations

import sys
import types

import pytest

import app.llm.structured as S


# ---------------------------------------------------------------------------
# Fake instructor / openai injected into sys.modules
# ---------------------------------------------------------------------------
class _FakeMode:
    JSON = "JSON"
    JSON_SCHEMA = "JSON_SCHEMA"


class _Recorder:
    """Records every (mode, model) create() attempt in call order."""

    def __init__(self):
        self.attempts = []
        # set of modes that should raise on create(); others "succeed"
        self.fail_modes = set()
        self.return_value = object()


def _install_fake_instructor(monkeypatch, recorder, *, has_json_schema=True):
    inst = types.ModuleType("instructor")

    mode = types.SimpleNamespace(JSON="JSON")
    if has_json_schema:
        mode.JSON_SCHEMA = "JSON_SCHEMA"
    inst.Mode = mode

    class _Completions:
        def __init__(self, mode):
            self._mode = mode

        def create(self, *, model, **_kw):
            recorder.attempts.append((self._mode, model))
            if self._mode in recorder.fail_modes:
                raise RuntimeError(f"boom-{self._mode}")
            return recorder.return_value

    class _Chat:
        def __init__(self, mode):
            self.completions = _Completions(mode)

    class _Client:
        def __init__(self, mode):
            self.chat = _Chat(mode)

    def from_openai(_client, mode=None):
        return _Client(mode)

    inst.from_openai = from_openai
    monkeypatch.setitem(sys.modules, "instructor", inst)

    # Minimal openai module with OpenAI / AsyncOpenAI ctors.
    op = types.ModuleType("openai")
    op.OpenAI = lambda **_k: object()
    op.AsyncOpenAI = lambda **_k: object()
    monkeypatch.setitem(sys.modules, "openai", op)
    return recorder


class _Post:  # stand-in response_model (never actually instantiated by fakes)
    pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_strict_first_then_json_order(monkeypatch):
    """Strict json_schema is tried FIRST; on failure, Mode.JSON is tried next."""
    monkeypatch.setenv("CEREBRAS_API_KEY", "x")  # provider = cerebras
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("STRUCTURED_STRICT_MODEL", raising=False)
    rec = _Recorder()
    rec.fail_modes = {"JSON_SCHEMA"}  # strict fails -> must fall to JSON
    _install_fake_instructor(monkeypatch, rec, has_json_schema=True)

    out = S.extract(_Post, system="s", user="u")
    assert out is rec.return_value
    modes = [m for (m, _model) in rec.attempts]
    assert modes == ["JSON_SCHEMA", "JSON"]  # exact fallback order


def test_strict_success_no_json_attempt(monkeypatch):
    """When strict succeeds, the legacy Mode.JSON path is NOT attempted."""
    monkeypatch.setenv("CEREBRAS_API_KEY", "x")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    rec = _Recorder()
    rec.fail_modes = set()
    _install_fake_instructor(monkeypatch, rec, has_json_schema=True)

    out = S.extract(_Post, system="s", user="u")
    assert out is rec.return_value
    modes = [m for (m, _model) in rec.attempts]
    assert modes == ["JSON_SCHEMA"]
    # Cerebras' current production model supports native strict JSON Schema.
    strict_model = rec.attempts[0][1]
    assert strict_model == "gpt-oss-120b"


def test_no_json_schema_mode_skips_strict(monkeypatch):
    """Old instructor build (no JSON_SCHEMA) -> straight to Mode.JSON."""
    monkeypatch.setenv("CEREBRAS_API_KEY", "x")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    rec = _Recorder()
    _install_fake_instructor(monkeypatch, rec, has_json_schema=False)

    out = S.extract(_Post, system="s", user="u")
    assert out is rec.return_value
    modes = [m for (m, _model) in rec.attempts]
    assert modes == ["JSON"]


def test_all_fail_returns_none_graceful(monkeypatch):
    """Both strict and JSON parse-failures -> graceful None, never raises."""
    monkeypatch.setenv("CEREBRAS_API_KEY", "x")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    rec = _Recorder()
    rec.fail_modes = {"JSON_SCHEMA", "JSON"}
    _install_fake_instructor(monkeypatch, rec, has_json_schema=True)

    out = S.extract(_Post, system="s", user="u")
    assert out is None
    modes = [m for (m, _model) in rec.attempts]
    assert modes == ["JSON_SCHEMA", "JSON"]


def test_no_provider_returns_none(monkeypatch):
    """No provider key -> None without touching instructor."""
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert S.extract(_Post, system="s", user="u") is None


def test_strict_model_selection():
    """_strict_model uses currently supported strict-capable provider models."""
    cb = S._strict_model("https://api.cerebras.ai/v1")
    gq = S._strict_model("https://api.groq.com/openai/v1")
    assert cb == "gpt-oss-120b"
    assert gq and "gpt-oss" not in gq
    assert S._strict_model("https://example.com/v1") is None


def test_retired_cerebras_override_falls_back_to_supported_model(monkeypatch):
    monkeypatch.setenv("STRUCTURED_STRICT_MODEL", "qwen-3-32b")
    assert S._strict_model("https://api.cerebras.ai/v1") == "gpt-oss-120b"


def test_groq_provider_strict_order(monkeypatch):
    """Groq provider also follows strict-first -> JSON fallback order."""
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.delenv("STRUCTURED_STRICT_MODEL", raising=False)
    rec = _Recorder()
    rec.fail_modes = {"JSON_SCHEMA"}
    _install_fake_instructor(monkeypatch, rec, has_json_schema=True)

    out = S.extract(_Post, system="s", user="u")
    assert out is rec.return_value
    assert [m for (m, _model) in rec.attempts] == ["JSON_SCHEMA", "JSON"]


@pytest.mark.asyncio
async def test_aextract_strict_first(monkeypatch):
    """Async variant: strict-first then JSON fallback, returns value."""
    monkeypatch.setenv("CEREBRAS_API_KEY", "x")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    rec = _Recorder()
    rec.fail_modes = {"JSON_SCHEMA"}

    # async fake: create() must be awaitable
    inst = types.ModuleType("instructor")
    inst.Mode = types.SimpleNamespace(JSON="JSON", JSON_SCHEMA="JSON_SCHEMA")

    class _Completions:
        def __init__(self, mode):
            self._mode = mode

        async def create(self, *, model, **_kw):
            rec.attempts.append((self._mode, model))
            if self._mode in rec.fail_modes:
                raise RuntimeError("boom")
            return rec.return_value

    class _Chat:
        def __init__(self, mode):
            self.completions = _Completions(mode)

    class _Client:
        def __init__(self, mode):
            self.chat = _Chat(mode)

    inst.from_openai = lambda _c, mode=None: _Client(mode)
    monkeypatch.setitem(sys.modules, "instructor", inst)
    op = types.ModuleType("openai")
    op.OpenAI = lambda **_k: object()
    op.AsyncOpenAI = lambda **_k: object()
    monkeypatch.setitem(sys.modules, "openai", op)

    out = await S.aextract(_Post, system="s", user="u")
    assert out is rec.return_value
    assert [m for (m, _model) in rec.attempts] == ["JSON_SCHEMA", "JSON"]
