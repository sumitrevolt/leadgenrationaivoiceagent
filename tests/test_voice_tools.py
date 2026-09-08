"""Tests for VOICE_TOOLS — agentic in-call actions wiring (default OFF).

Hermetic: no telephony / no network / no real LLM. Covers:
  1. voice_tools.voice_tools_enabled() gating contract (default OFF).
  2. voice_tools.tools_instruction() advertises the high-value actions + CALL form.
  3. function_calling.parse_tool_call() understands the brain's `CALL <tool> {json}`.
  4. build_default_registry().execute() runs a tool offline (simulation fallback).
  5. VobizStreamSession._tool_confirmation() speaks a safe Hinglish line per tool.
  6. TelecallerBrain.reply_with_tools() routes a CALL line -> tool_call, and a
     plain line -> spoken text (with _generate/_kb_facts monkeypatched).
"""

from __future__ import annotations

import asyncio
import os
import types

import pytest


# --------------------------------------------------------------------------- #
# 1) Gating: default OFF
# --------------------------------------------------------------------------- #
def test_voice_tools_gating_default_off(monkeypatch):
    from app.voice_agent import voice_tools

    monkeypatch.delenv("VOICE_TOOLS", raising=False)
    assert voice_tools.voice_tools_enabled() is False
    for on in ("1", "true", "YES", "on"):
        monkeypatch.setenv("VOICE_TOOLS", on)
        assert voice_tools.voice_tools_enabled() is True
    monkeypatch.setenv("VOICE_TOOLS", "0")
    assert voice_tools.voice_tools_enabled() is False


# --------------------------------------------------------------------------- #
# 2) tools_instruction advertises the actions + the CALL convention
# --------------------------------------------------------------------------- #
def test_tools_instruction_lists_actions():
    from app.voice_agent.voice_tools import tools_instruction

    text = tools_instruction()
    assert "CALL" in text
    for tool in ("book_appointment", "capture_lead_info", "transfer_to_human", "end_call"):
        assert tool in text


# --------------------------------------------------------------------------- #
# 3) parse_tool_call understands the brain's emitted CALL line
# --------------------------------------------------------------------------- #
def test_parse_tool_call_from_call_line():
    from app.voice_agent.function_calling import parse_tool_call

    out = parse_tool_call('CALL book_appointment {"when_iso": "2026-07-01T15:00", "name": "Rahul"}')
    assert out and out["name"] == "book_appointment"
    assert out["args"]["when_iso"] == "2026-07-01T15:00"

    # A normal spoken reply must NOT look like a tool call.
    assert parse_tool_call("Ji sir, main aapko kal call karungi.") is None


# --------------------------------------------------------------------------- #
# 4) registry executes a tool offline (calendar sim fallback)
# --------------------------------------------------------------------------- #
def _isolate_calendar(monkeypatch, tmp_path):
    """Point the calendar at a tmp ledger + reset its singleton so book tests are
    hermetic (the real bookings ledger persists 'taken' slots across runs)."""
    import app.integrations.calendar_booking as cb

    monkeypatch.setattr(cb, "DATA_BOOKINGS_DIR", str(tmp_path / "bk"))
    monkeypatch.setattr(cb, "_calendar", None)  # fresh singleton -> empty taken slots
    monkeypatch.setenv("BOOKING_NOTIFY", "0")


def test_registry_executes_book_appointment_offline(monkeypatch, tmp_path):
    _isolate_calendar(monkeypatch, tmp_path)
    from app.voice_agent.function_calling import build_default_registry

    reg = build_default_registry({"niche": "solar_residential", "lead": {"phone": "98765xxxxx"}})
    assert "book_appointment" in reg.names()
    res = asyncio.run(reg.execute("book_appointment", {"when_iso": "2026-07-01T15:00"}))
    assert res.ok is True
    assert isinstance(res.data, dict)


# --------------------------------------------------------------------------- #
# 5) _tool_confirmation speaks a safe Hinglish line per tool
# --------------------------------------------------------------------------- #
def test_tool_confirmation_lines():
    from app.telephony.vobiz_stream import VobizStreamSession

    ok_book = types.SimpleNamespace(ok=True, data={"when": "2026-07-01T15:00"})
    line = VobizStreamSession._tool_confirmation("book_appointment", ok_book)
    assert "book" in line.lower() and line.strip()

    transfer = types.SimpleNamespace(ok=True, data={})
    assert "connect" in VobizStreamSession._tool_confirmation("transfer_to_human", transfer).lower()

    # honours a tool-provided confirmation_text verbatim
    custom = types.SimpleNamespace(ok=True, data={"confirmation_text": "Theek hai Rahul ji."})
    assert (
        VobizStreamSession._tool_confirmation("book_appointment", custom) == "Theek hai Rahul ji."
    )


# --------------------------------------------------------------------------- #
# 6) reply_with_tools routes CALL -> tool_call, plain -> spoken
# --------------------------------------------------------------------------- #
def _make_brain():
    """Build a TelecallerBrain offline (dummy free-provider key avoids the
    no-key raise). Skips if optional deps make construction impossible here."""
    os.environ.setdefault("GROQ_API_KEY", "test-dummy-key")
    try:
        from app.voice_agent.telecaller_brain import TelecallerBrain

        return TelecallerBrain(niche="solar_residential", client_name="Demo Co")
    except Exception as e:  # pragma: no cover - environment dependent
        pytest.skip(f"TelecallerBrain unavailable offline: {e}")


def test_reply_with_tools_routes_tool_call(monkeypatch):
    from app.voice_agent.function_calling import build_default_registry

    brain = _make_brain()
    reg = build_default_registry({"niche": "solar_residential"})

    async def _fake_kb(_ut):
        return []

    async def _fake_gen_call(_prompt):
        return ('CALL book_appointment {"when_iso": "2026-07-01T15:00"}', "test")

    monkeypatch.setattr(brain, "_kb_facts", _fake_kb)
    monkeypatch.setattr(brain, "_generate", _fake_gen_call)
    # CLOSE_DETECT (LIVE, default ON) buy-signal "book kar do" ko pre-LLM confirm pe
    # short-circuit karta — is test ka target TOOL routing hai, close-flow nahi.
    monkeypatch.setattr("app.voice_agent.telecaller_brain._close_detect_enabled", lambda: False)

    spoken, call = asyncio.run(brain.reply_with_tools([], "book kar do kal 3 baje", reg))
    assert call is not None and call["name"] == "book_appointment"
    assert spoken == ""


def test_reply_with_tools_books_on_slot_confirmation(monkeypatch):
    """Bare confirmation ("haan theek hai", NO time/keyword) right after the bot
    proposed a slot must reach the tool-LLM (-> book), not the discovery fast-path.

    Robust by design: _fast_path_reply is forced to a sentinel, so `call` can only
    be non-None if the _action_intent gate correctly bypassed it (the prev-slot +
    confirmation branch). If the gate regresses, the sentinel returns (call=None)."""
    from app.voice_agent.function_calling import build_default_registry

    brain = _make_brain()
    reg = build_default_registry({"niche": "solar_residential"})

    async def _fake_kb(_ut):
        return []

    async def _fake_gen_call(_prompt):
        return ('CALL book_appointment {"when_iso": "2026-07-01T15:00"}', "test")

    monkeypatch.setattr(brain, "_fast_path_reply", lambda *_a, **_k: "FAST_PATH_SHOULD_NOT_WIN")
    monkeypatch.setattr(brain, "_kb_facts", _fake_kb)
    monkeypatch.setattr(brain, "_generate", _fake_gen_call)

    history = [
        {"role": "assistant", "content": "Perfect sir — kal subah gyarah baje slot fix kar doon?"},
    ]
    spoken, call = asyncio.run(brain.reply_with_tools(history, "haan theek hai", reg))
    assert call is not None and call["name"] == "book_appointment"
    assert spoken == ""


def test_reply_with_tools_routes_spoken(monkeypatch):
    from app.voice_agent.function_calling import build_default_registry

    brain = _make_brain()
    reg = build_default_registry({"niche": "solar_residential"})

    async def _fake_kb(_ut):
        return []

    async def _fake_gen_text(_prompt):
        return ("Ji sir, solar pe abhi subsidy chal rahi hai.", "test")

    monkeypatch.setattr(brain, "_kb_facts", _fake_kb)
    monkeypatch.setattr(brain, "_generate", _fake_gen_text)

    spoken, call = asyncio.run(brain.reply_with_tools([], "subsidy hai kya", reg))
    assert call is None
    assert spoken and "solar" in spoken.lower()


# --------------------------------------------------------------------------- #
# 7) shared run_tool_turn helper (used by BOTH vobiz + web-call paths)
# --------------------------------------------------------------------------- #
def test_run_tool_turn_tool_spoken_and_end(monkeypatch, tmp_path):
    _isolate_calendar(monkeypatch, tmp_path)
    from app.voice_agent import voice_tools
    from app.voice_agent.function_calling import build_default_registry

    reg = build_default_registry({"niche": "solar_residential"})

    class _Brain:
        async def reply_with_tools(self, history, user_text, registry):
            if "book" in user_text:
                return "", {"name": "book_appointment", "args": {"when_iso": "2026-07-01T15:00"}}
            if "bye" in user_text:
                return "", {"name": "end_call", "args": {"outcome": "qualified"}}
            return "Ji sir, boliye.", None

    brain = _Brain()

    d_tool = asyncio.run(voice_tools.run_tool_turn(brain, [], "book kar do", reg))
    assert d_tool["did_tool"] is True and d_tool["tool"] == "book_appointment"
    assert d_tool["spoken"] and d_tool["should_end"] is False

    d_say = asyncio.run(voice_tools.run_tool_turn(brain, [], "namaste", reg))
    assert d_say["did_tool"] is False and d_say["spoken"] == "Ji sir, boliye."

    d_end = asyncio.run(voice_tools.run_tool_turn(brain, [], "bye", reg))
    assert d_end["should_end"] is True


def test_run_tool_turn_safe_on_missing_brain():
    from app.voice_agent import voice_tools

    d = asyncio.run(voice_tools.run_tool_turn(None, [], "hi", None))
    assert d == {"spoken": "", "did_tool": False, "tool": None, "should_end": False}


def test_build_registry_for_offline():
    from app.voice_agent import voice_tools

    reg = voice_tools.build_registry_for(niche="solar_residential")
    assert reg is not None and "book_appointment" in reg.names()
