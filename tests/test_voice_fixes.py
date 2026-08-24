"""Pure-python tests for SP7 voice product code-gap closures.

Covers (no telephony / no network / no real LLM):
  1. app/tasks/calling.py — the Celery call tasks now use the REAL CallManager
     API (queue_call / start_call_processor), NOT the non-existent
     initiate_call / process_queue (latent AttributeError under legacy beat).
  2. app/voice_agent/amd.py — answering-machine detection used by the new gated
     AMD_DETECT path in vobiz_stream (transcript heuristics).
  3. The AMD_DETECT gating contract (flag default OFF = no-op).
  4. app/telephony/missed_call.py — inbound/missed-call lead capture (the new
     /api/webhooks/vobiz/inbound route delegates here).

All side-effects (jsonl/db) are monkeypatched away so the suite is hermetic.
"""

from __future__ import annotations

import asyncio
import inspect
import os

import pytest


# --------------------------------------------------------------------------- #
# 1) calling.py uses the correct CallManager API (no dead method names)
# --------------------------------------------------------------------------- #
def test_calling_tasks_use_real_callmanager_api():
    """make_call_task → queue_call; process_queue → start_call_processor.

    Guards against the latent AttributeError: CallManager has NO initiate_call /
    process_queue methods, so the old source would crash if legacy beat fired.
    """
    import app.tasks.calling as calling

    make_src = inspect.getsource(calling.make_call_task)
    assert "call_manager.queue_call" in make_src, "make_call_task must enqueue via queue_call()"
    assert "call_manager.initiate_call" not in make_src, (
        "initiate_call does not exist on CallManager"
    )

    pq_src = inspect.getsource(calling.process_queue)
    assert "start_call_processor" in pq_src, "process_queue must drain via start_call_processor()"
    # the only valid 'process_queue' reference is the task def name itself
    assert "call_manager.process_queue" not in pq_src, "CallManager has no process_queue()"


def test_callmanager_has_expected_methods():
    """The methods calling.py relies on actually exist on CallManager."""
    from app.telephony.call_manager import CallManager

    assert hasattr(CallManager, "queue_call")
    assert hasattr(CallManager, "start_call_processor")
    assert hasattr(CallManager, "handle_call_completed")
    # and the dead names are confirmed absent (so nobody re-introduces them)
    assert not hasattr(CallManager, "initiate_call")
    assert not hasattr(CallManager, "process_queue")


def test_process_queue_signature_bounded():
    """process_queue is bounded (max_seconds) so the worker never blocks forever."""
    import app.tasks.calling as calling

    sig = inspect.signature(
        calling.process_queue.__wrapped__
        if hasattr(calling.process_queue, "__wrapped__")
        else calling.process_queue
    )
    # Celery wraps the function; fall back to source check if signature is opaque.
    src = inspect.getsource(calling.process_queue)
    assert "wait_for" in src and "timeout" in src, "drain must be time-bounded"
    assert "TimeoutError" in src, "the expected timeout must be swallowed gracefully"


# --------------------------------------------------------------------------- #
# 2) AMD detector heuristics (the engine behind AMD_DETECT)
# --------------------------------------------------------------------------- #
def test_amd_detects_voicemail_greeting():
    from app.voice_agent.amd import AnsweringMachineDetector

    amd = AnsweringMachineDetector()
    r = amd.detect_from_transcript(
        "You have reached the voicemail of Raj. Please leave a message after the beep."
    )
    assert r.is_machine is True
    assert r.confidence >= 0.6
    assert r.action in ("leave_message", "hangup")


def test_amd_detects_hinglish_voicemail():
    from app.voice_agent.amd import AnsweringMachineDetector

    amd = AnsweringMachineDetector()
    r = amd.detect_from_transcript("Kripya beep ke baad apna message record karein.")
    assert r.is_machine is True


def test_amd_human_greeting_is_not_machine():
    from app.voice_agent.amd import AnsweringMachineDetector

    amd = AnsweringMachineDetector()
    r = amd.detect_from_transcript("Hello? Haan boliye, kaun?")
    assert r.is_machine is False
    assert r.action == "continue"


def test_amd_empty_transcript_safe():
    from app.voice_agent.amd import AnsweringMachineDetector

    amd = AnsweringMachineDetector()
    r = amd.detect_from_transcript("")
    assert r.is_machine is False
    assert r.action == "continue"


# --------------------------------------------------------------------------- #
# 3) AMD_DETECT gating contract on the vobiz_stream session
# --------------------------------------------------------------------------- #
def _make_session():
    """Construct a VobizStreamSession without a real WS (we never call handle())."""
    from app.telephony.vobiz_stream import VobizStreamSession

    class _FakeWS:
        def __init__(self):
            self.closed = False

        async def close(self):
            self.closed = True

    return VobizStreamSession(_FakeWS(), niche="solar", client_id="c1", client_name="Acme")


def test_amd_check_noop_when_flag_off(monkeypatch):
    """AMD_DETECT unset/OFF → _amd_check returns False (default flow unchanged)."""
    monkeypatch.delenv("AMD_DETECT", raising=False)
    sess = _make_session()
    out = asyncio.run(sess._amd_check("Please leave a message after the beep."))
    assert out is False
    assert sess._amd_machine is False
    assert sess.ws.closed is False  # call NOT aborted when flag off


def test_amd_check_aborts_on_machine_when_flag_on(monkeypatch):
    """AMD_DETECT=1 + voicemail greeting → _amd_check aborts (True) and closes WS."""
    monkeypatch.setenv("AMD_DETECT", "1")
    sess = _make_session()
    out = asyncio.run(
        sess._amd_check("You have reached the voicemail. Leave a message after the tone.")
    )
    assert out is True
    assert sess._amd_machine is True
    assert sess.ws.closed is True


def test_amd_check_human_continues_when_flag_on(monkeypatch):
    """AMD_DETECT=1 + human greeting → _amd_check returns False (continue normally)."""
    monkeypatch.setenv("AMD_DETECT", "1")
    sess = _make_session()
    out = asyncio.run(sess._amd_check("Haan ji boliye"))
    assert out is False
    assert sess._amd_machine is False
    assert sess.ws.closed is False


def test_amd_state_initialized():
    sess = _make_session()
    assert sess._amd_checked is False
    assert sess._amd_machine is False


# --------------------------------------------------------------------------- #
# 4) missed-call lead capture (target of /api/webhooks/vobiz/inbound)
# --------------------------------------------------------------------------- #
def test_missed_call_lead_capture_no_callback(monkeypatch):
    import app.api.public_site as ps
    from app.telephony import missed_call

    monkeypatch.setattr(ps, "_append_jsonl", lambda r: True, raising=False)
    monkeypatch.setattr(ps, "_save_lead_db", lambda r: None, raising=False)
    monkeypatch.delenv("MISSED_CALL_CALLBACK", raising=False)
    missed_call._RECENT.clear()

    res = asyncio.run(missed_call.handle_missed_call("+919812345678", "solar", "Acme"))
    assert res["ok"] is True
    assert res["callback"] is False  # gated off → lead captured, no callback


def test_missed_call_rejects_empty_number():
    from app.telephony import missed_call

    res = asyncio.run(missed_call.handle_missed_call(""))
    assert res["ok"] is False


def test_missed_call_dedupe(monkeypatch):
    import app.api.public_site as ps
    from app.telephony import missed_call

    monkeypatch.setattr(ps, "_append_jsonl", lambda r: True, raising=False)
    monkeypatch.setattr(ps, "_save_lead_db", lambda r: None, raising=False)
    monkeypatch.delenv("MISSED_CALL_CALLBACK", raising=False)
    missed_call._RECENT.clear()
    # mark as recently called → dedupe path
    import time as _t

    missed_call._RECENT["+919800000000"] = _t.time()
    res = asyncio.run(missed_call.handle_missed_call("+919800000000", "solar"))
    assert res["ok"] is True
    assert res["callback"] is False
    assert "dedupe" in res.get("reason", "")


# --------------------------------------------------------------------------- #
# 5) inbound webhook route is registered (additive, not shadowing)
# --------------------------------------------------------------------------- #
def test_vobiz_inbound_route_registered():
    from app.telephony.webhooks import router

    paths = {getattr(r, "path", "") for r in router.routes}
    assert "/vobiz/inbound" in paths, "inbound missed-call route must be mounted"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
