"""Tests — 2026-07-05 USER-MANDATE fixes (paisa-burn + IVR/bot false-qualify).

1. dial_gate: promotional outbound TEST-MODE allowlist (default ON, fail-closed).
2. call_qualifier: bot/IVR detection + min-user-turns gate (qualified ka darwaza).
3. post_call_hooks: bot-suspect => outcome NULL + detected_intent, call_cost metering.
4. VobizClient.place_call: dial_gate choke-point (blocked dial = zero network).
"""

from __future__ import annotations

import json

import pytest

from app.telephony import dial_gate


def _isolate(monkeypatch, tmp_path, *, mode_env=None, allow_env=None, file_cfg=None):
    monkeypatch.delenv("DIAL_TEST_MODE", raising=False)
    monkeypatch.delenv("DIAL_TEST_ALLOWLIST", raising=False)
    cfg = tmp_path / "dial_test_mode.json"
    monkeypatch.setenv("DIAL_TEST_MODE_CONFIG", str(cfg))
    if mode_env is not None:
        monkeypatch.setenv("DIAL_TEST_MODE", mode_env)
    if allow_env is not None:
        monkeypatch.setenv("DIAL_TEST_ALLOWLIST", allow_env)
    if file_cfg is not None:
        cfg.write_text(json.dumps(file_cfg), encoding="utf-8")


# --------------------------------------------------------------------------- #
# dial_gate
# --------------------------------------------------------------------------- #
def test_default_test_mode_on_blocks_promotional(monkeypatch, tmp_path):
    """Koi config nahi => test-mode ON => promotional cold call BLOCKED."""
    _isolate(monkeypatch, tmp_path)
    assert dial_gate.test_mode() is True
    allowed, reason = dial_gate.check("+919812345678", "promotional")
    assert allowed is False
    assert "allowlist" in reason


def test_transactional_never_gated(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    allowed, reason = dial_gate.check("+919812345678", "transactional")
    assert allowed is True
    assert reason == "non_promotional"


def test_allowlisted_number_passes(monkeypatch, tmp_path):
    """Env allowlist + E.164/0-prefix normalize (last-10 match)."""
    _isolate(monkeypatch, tmp_path, allow_env="+91 82610-30181, 09812345678")
    assert dial_gate.check("+918261030181", "promotional")[0] is True
    assert dial_gate.check("9812345678", "promotional")[0] is True
    assert dial_gate.check("+919999999999", "promotional")[0] is False


def test_file_allowlist_merges_and_env_mode_zero_opens(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, file_cfg={"enabled": True, "numbers": ["8308009815"]})
    assert dial_gate.check("+918308009815", "promotional")[0] is True
    # env explicit 0 = final (file kuch bhi bole)
    monkeypatch.setenv("DIAL_TEST_MODE", "0")
    assert dial_gate.test_mode() is False
    assert dial_gate.check("+917000000000", "promotional")[0] is True


def test_file_can_disable_test_mode(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, file_cfg={"enabled": False})
    assert dial_gate.test_mode() is False


# --------------------------------------------------------------------------- #
# call_qualifier — bot/IVR detection
# --------------------------------------------------------------------------- #
def test_detect_ivr_phrases():
    from app.voice_agent.call_qualifier import detect_bot_or_ivr

    cases = [
        "assistant: namaste\nuser: Welcome to Relook Clinic, press 1 for appointment",
        "assistant: hi\nuser: aapki call hamare liye mahatvapurn hai, kripya line par bane rahen",
        "assistant: hi\nuser: hindi ke liye 1 dabayen",
        "assistant: hi\nuser: आपका कॉल रिकॉर्ड की जा रही है",
    ]
    for tx in cases:
        suspect, reason = detect_bot_or_ivr(tx)
        assert suspect is True, tx
        assert reason


def test_detect_repeated_bot_loop():
    from app.voice_agent.call_qualifier import detect_bot_or_ivr

    tx = "\n".join(
        [
            "assistant: namaste",
            "user: haan boliye",
            "assistant: hum AI marketing...",
            "user: haan boliye",
            "assistant: sirf 1999 me...",
            "user: haan boliye",
        ]
    )
    assert detect_bot_or_ivr(tx)[0] is True


def test_human_conversation_not_flagged():
    from app.voice_agent.call_qualifier import detect_bot_or_ivr

    tx = "\n".join(
        [
            "assistant: namaste, main AI assistant",
            "user: haan bataiye kya hai",
            "assistant: hum marketing automate karte hain",
            "user: price kya hai iska",
            "assistant: 1999 mahina",
            "user: theek hai demo bhej do WhatsApp pe",
        ]
    )
    assert detect_bot_or_ivr(tx)[0] is False


@pytest.mark.asyncio
async def test_qualify_gated_on_few_turns(monkeypatch):
    """LLM 'qualified' bole par user turns < min => override FALSE."""
    from app.voice_agent import call_qualifier as cq

    async def fake_chat(system, msgs, **kw):
        return (
            json.dumps(
                {
                    "interest_score": 5,
                    "qualified": True,
                    "appointment_requested": True,
                    "budget_signal": "high",
                    "summary": "bahut interested",
                    "next_action": "call",
                    "followup_draft": "hi",
                }
            ),
            "mistral",
        )

    monkeypatch.setattr("app.voice_agent.free_ai.chat", fake_chat)
    monkeypatch.delenv("QUALIFY_BOT_GATE", raising=False)
    monkeypatch.delenv("MIN_QUALIFY_USER_TURNS", raising=False)
    tx = "assistant: namaste ji, main AI assistant bol raha hoon aapke business ke liye\nuser: haan theek hai bhai"
    q = await cq.qualify_transcript(tx, {})
    assert q["qualified"] is False
    assert q["appointment_requested"] is False
    assert q["interest_score"] <= 2
    assert q["user_turns"] == 1
    assert q["bot_reason"].startswith("user_turns=")
    assert q["summary"].startswith("[UNVERIFIED")


@pytest.mark.asyncio
async def test_qualify_gated_on_ivr(monkeypatch):
    from app.voice_agent import call_qualifier as cq

    async def fake_chat(system, msgs, **kw):
        return json.dumps({"interest_score": 4, "qualified": True, "summary": "in"}), "groq"

    monkeypatch.setattr("app.voice_agent.free_ai.chat", fake_chat)
    monkeypatch.delenv("QUALIFY_BOT_GATE", raising=False)
    tx = "\n".join(
        [
            "assistant: namaste",
            "user: welcome to ABC industries, press 1 for sales",
            "assistant: main AI hoon",
            "user: press 2 for support",
            "assistant: ok",
            "user: for hindi press 3",
        ]
    )
    q = await cq.qualify_transcript(tx, {})
    assert q["bot_suspected"] is True
    assert q["qualified"] is False


@pytest.mark.asyncio
async def test_qualify_clean_human_passes(monkeypatch):
    from app.voice_agent import call_qualifier as cq

    async def fake_chat(system, msgs, **kw):
        return json.dumps({"interest_score": 4, "qualified": True, "summary": "in"}), "groq"

    monkeypatch.setattr("app.voice_agent.free_ai.chat", fake_chat)
    monkeypatch.delenv("QUALIFY_BOT_GATE", raising=False)
    monkeypatch.delenv("MIN_QUALIFY_USER_TURNS", raising=False)
    tx = "\n".join(
        [
            "assistant: namaste",
            "user: haan boliye kaun",
            "assistant: AI marketing wale",
            "user: acha price kya hai",
            "assistant: 1999",
            "user: theek hai trial bhejo",
        ]
    )
    q = await cq.qualify_transcript(tx, {})
    assert q["qualified"] is True
    assert q["bot_suspected"] is False


# --------------------------------------------------------------------------- #
# post_call_hooks — bot-suspect mapping + cost metering
# --------------------------------------------------------------------------- #
def test_build_call_log_bot_suspect_null_outcome_and_cost(monkeypatch):
    monkeypatch.setenv("CALL_LOG_DB", "1")
    monkeypatch.delenv("VOBIZ_COST_PAISE_PER_MIN", raising=False)
    from app.telephony import post_call_hooks as pch

    q = {"interest_score": 4, "qualified": False, "bot_suspected": True, "summary": "x"}
    row = pch.build_call_log(
        call_id="sid-bot",
        provider="vobiz",
        phone="+919812345678",
        duration_s=90.0,
        user_turns=4,
        outcome="completed",
        q=q,
    )
    assert row is not None
    assert row.outcome is None  # unknown/unverified — NOT interested
    assert row.detected_intent == "bot_suspected"
    assert row.call_cost == 2 * 45  # ceil(90s/60)=2 min × 45 paise


def test_build_call_log_cost_zero_for_phoneless(monkeypatch):
    monkeypatch.setenv("CALL_LOG_DB", "1")
    from app.telephony import post_call_hooks as pch

    row = pch.build_call_log(
        call_id="sid-ws", provider="vobiz", phone="", duration_s=120.0, outcome="test_session"
    )
    assert row is not None
    assert row.call_cost == 0


# --------------------------------------------------------------------------- #
# VobizClient.place_call — dial_gate choke-point
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_place_call_blocked_by_dial_gate(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)  # default: test-mode ON, empty allowlist
    from app.telephony.vobiz_handler import VobizClient

    client = VobizClient()
    result = await client.place_call(
        to="+919812345678", answer_url="https://x/answer", call_type="promotional"
    )
    assert result.get("blocked") is True
    assert result["body"]["error"] == "blocked_by_dial_test_mode"


@pytest.mark.asyncio
async def test_place_call_allowlisted_passes_gate(monkeypatch, tmp_path):
    """Allowlisted promo number dial_gate se aage badhta hai (phir compliance/
    network layer apna kaam kare — yahan sirf gate-pass verify)."""
    _isolate(monkeypatch, tmp_path, allow_env="9812345678")
    from app.telephony import vobiz_handler as vh

    called = {}

    class _FakeGate:
        async def check(self, to, ct):
            called["compliance"] = True

            class D:
                allowed = False
                reasons = ["stop_here"]

                def as_dict(self):
                    return {}

            return D()

    monkeypatch.setattr("app.telephony.compliance.get_compliance_gate", lambda: _FakeGate())
    client = vh.VobizClient()
    result = await client.place_call(
        to="+919812345678", answer_url="https://x/answer", call_type="promotional"
    )
    # dial_gate ne pass kiya (blocked_by_dial_test_mode NAHI) — compliance tak pahuncha
    assert called.get("compliance") is True
    assert result["body"].get("error") != "blocked_by_dial_test_mode"
