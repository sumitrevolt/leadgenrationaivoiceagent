"""Unit tests for free_ai realtime LLM RACE (LLM_REALTIME_RACE, 2026-08-23).

Owner directive: "enterprise grade chat, 1 second bhi dead-air nahi". Live prod
evidence (turn_metrics 2026-08-23): sequential ladder me llm_first 2189-6839ms â€”
ek stalled primary poora _CALL_TIMEOUT_S=8s kha sakta tha. Race = top-2 providers
SIMULTANEOUS, first content token wins, loser cancelled.
"""

from __future__ import annotations

import asyncio

import pytest

from app.voice_agent import free_ai as fa


class _FakeChunk:
    def __init__(self, text: str) -> None:
        self.choices = [type("C", (), {"delta": type("D", (), {"content": text})()})()]


class _FakeStream:
    """Async iterator of chunks + aclose(), mirroring the OpenAI SDK shape."""

    def __init__(self, chunks: list[str]) -> None:
        self._chunks = list(chunks)
        self.closed = False

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for c in self._chunks:
            await asyncio.sleep(0)
            yield _FakeChunk(c)

    async def aclose(self) -> None:
        self.closed = True


def _install_fakes(monkeypatch, mode: str, events: dict[str, list]):
    """mode = 'fast' | 'slow' | 'boom' | 'empty' â€” sab providers ke liye uniform."""

    class _Completions:
        async def create(self, **kwargs):
            if mode == "slow":
                await asyncio.sleep(5)
                raise asyncio.TimeoutError("slow provider")
            if mode == "boom":
                raise RuntimeError(f"{kwargs['model']} exploded")
            if mode == "empty":
                return _FakeStream([])
            return _FakeStream(["Namaste", " ji"])

    class _FakeClient:
        def __init__(self) -> None:
            self.chat = type(
                "Chat", (), {"completions": type("Comp", (), {"create": _Completions().create})()}
            )()

    def make_client(_provider: str):
        return _FakeClient()

    monkeypatch.setattr(fa, "_client", make_client)
    monkeypatch.setattr(fa, "_provider_down", lambda p: False)
    monkeypatch.setattr(fa, "_blocked_for_provider", lambda msgs, p: False)
    monkeypatch.setattr(fa, "_reset_cooldown_streak", lambda p: events["reset"].append(p))
    monkeypatch.setattr(fa, "_trip_cooldown", lambda p, e: events["trip"].append(p))

    import app.platform.llm_metrics as lm

    monkeypatch.setattr(lm, "record", lambda *a, **k: events["metric"].append(a))


@pytest.mark.asyncio
async def test_race_flag_realtime_on_bulk_off(monkeypatch):
    monkeypatch.delenv("LLM_REALTIME_RACE", raising=False)
    assert fa._realtime_race_enabled("realtime") is True
    assert fa._realtime_race_enabled("bulk") is False
    monkeypatch.setenv("LLM_REALTIME_RACE", "0")
    assert fa._realtime_race_enabled("realtime") is False


@pytest.mark.asyncio
async def test_race_winner_streams_and_loser_cancelled(monkeypatch):
    events: dict[str, list] = {"trip": [], "reset": [], "metric": []}
    _install_fakes(monkeypatch, "fast", events)

    # groq fast, cerebras slow-create (loser) â€” per-provider override.
    def make_client(provider: str):
        if provider == "cerebras":

            class _SlowCompletions:
                async def create(self, **kwargs):
                    await asyncio.sleep(5)
                    raise asyncio.TimeoutError("never")

            class _SlowClient:
                def __init__(self):
                    self.chat = type(
                        "Chat",
                        (),
                        {"completions": type("Comp", (), {"create": _SlowCompletions().create})()},
                    )()

            return _SlowClient()

        class _FastCompletions:
            async def create(self, **kwargs):
                return _FakeStream(["Namaste", " ji"])

        class _FastClient:
            def __init__(self):
                self.chat = type(
                    "Chat",
                    (),
                    {"completions": type("Comp", (), {"create": _FastCompletions().create})()},
                )()

        return _FastClient()

    monkeypatch.setattr(fa, "_client", make_client)

    out: list[str] = []
    async for d in fa.chat_stream("", [{"role": "user", "content": "hi"}], profile="realtime"):
        out.append(d)
    assert "".join(out) == "Namaste ji"
    assert events["trip"] == []  # loser was CANCELLED, not errored
    assert events["reset"] == ["groq"]  # winner breaker reset


@pytest.mark.asyncio
async def test_race_both_fail_trips_cooldowns_and_falls_through(monkeypatch):
    events: dict[str, list] = {"trip": [], "reset": [], "metric": []}
    _install_fakes(monkeypatch, "boom", events)
    # boom for everyone: race legs fail -> cooldowns tripped -> sequential skips
    # them (_provider_down) -> nothing left -> empty stream.
    out: list[str] = []
    async for d in fa.chat_stream("", [{"role": "user", "content": "hi"}], profile="realtime"):
        out.append(d)
    assert out == []
    assert set(events["trip"]) >= {"groq", "cerebras"}


@pytest.mark.asyncio
async def test_race_single_candidate_returns_none_sequential_serves(monkeypatch):
    """<2 usable candidates -> race inert, sequential serves normally."""
    events: dict[str, list] = {"trip": [], "reset": [], "metric": []}
    _install_fakes(monkeypatch, {"mode": "fast"}, events)
    monkeypatch.setattr(fa, "_provider_down", lambda p: p != "groq")  # sirf groq usable
    out: list[str] = []
    async for d in fa.chat_stream("", [{"role": "user", "content": "hi"}], profile="realtime"):
        out.append(d)
    assert "".join(out) == "Namaste ji"
    assert events["reset"] == ["groq"]


@pytest.mark.asyncio
async def test_race_disabled_env_gives_sequential_behaviour(monkeypatch):
    monkeypatch.setenv("LLM_REALTIME_RACE", "0")
    events: dict[str, list] = {"trip": [], "reset": [], "metric": []}
    _install_fakes(monkeypatch, {"mode": "fast"}, events)
    out: list[str] = []
    async for d in fa.chat_stream("", [{"role": "user", "content": "hi"}], profile="realtime"):
        out.append(d)
    assert "".join(out) == "Namaste ji"
