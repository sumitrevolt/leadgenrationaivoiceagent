"""2026-07-06 call-batch learning fixes (05-Jul 22-call transcript audit).

Real failures fixed (data/call_transcripts/2026-07-05.jsonl):
1. IVR phrases the live batch said but _IVR_PATTERNS missed ("Welcome to
   LiveSpace", "प्रेस वन", "connect your call", voicemail scripts) — agent
   167s tak HDFC-Ergo IVR se discovery karta raha.
2. In-call IVR strike counter + hangup (IVR_HANGUP, default ON) — pehle sirf
   voicemail-reply bolta tha, call chalti rehti thi (paisa burn).
3. Whisper noise-hallucination loops ("Aam shabd, Aam Shabd, ..." x6) LLM tak
   pahunch ke turns kharab karte the — _is_junk repetition filter.
4. Good call f452cce6: value-statement ke baad customer "Okay." bola aur bot ne
   AGLA discovery-sawaal puchha (close nahi) — hot lead bina next-step ke gaya.
   ACK_TRIAL_CLOSE (default ON) ab trial-close ask deta hai.
5. Dialed path par post-close affirm ("haan yahi number") durable close
   (_on_close_signal) fire nahi karta tha — sirf web path karta tha.
"""

from __future__ import annotations

import asyncio

import pytest

from app.telephony.vobiz_stream import VobizStreamSession
from app.voice_agent.call_qualifier import detect_bot_or_ivr
from app.voice_agent.telecaller_brain import TelecallerBrain

# --------------------------------------------------------------------------- #
# 1. call_qualifier — observed-in-prod IVR phrases now detected
# --------------------------------------------------------------------------- #
OBSERVED_IVR_LINES = [
    "Welcome to LiveSpace.",
    "Thank you for calling the HDFC Ergo agent. To buy policy, please press 1.",
    "I am sorry, you have not entered any input. Press 1 for fresh interior requirements.",
    "If you are an existing Lipspace customer.",
    "The bottom you are trying to reach isn't available.",
    "Your call has been forwarded to voicemail. At the tone, please record your message.",
    "This call is recorded for quality and training purposes.",
    "प्रेस वन सो फ्रेश इंटीरियर रिक्वायर्मेंट।",
    "वाल वी क्नेक्ट योर कोल प्लीज वेट",
]


@pytest.mark.parametrize("line", OBSERVED_IVR_LINES)
def test_detect_bot_or_ivr_catches_observed_lines(line):
    suspect, why = detect_bot_or_ivr(f"user: {line}")
    assert suspect is True, f"missed IVR phrase: {line!r} ({why})"


def test_detect_bot_or_ivr_real_human_not_flagged():
    tx = "user: haan bolo\nuser: abhi agency se karwate hain\nuser: theek hai batao"
    assert detect_bot_or_ivr(tx)[0] is False


# --------------------------------------------------------------------------- #
# 2. vobiz_stream._is_ivr_prompt — shared _IVR_RE consult
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "line",
    [
        "Welcome to LiveSpace.",
        "प्रेस वन सो फ्रेश इंटीरियर रिक्वायर्मेंट।",
        "Please wait while we connect your call.",
        "Your call has been forwarded to voicemail.",
    ],
)
def test_is_ivr_prompt_widened(line):
    assert VobizStreamSession._is_ivr_prompt(line) is True


def test_is_ivr_prompt_human_speech_not_flagged():
    assert VobizStreamSession._is_ivr_prompt("haan boliye, kya offer hai aapka?") is False
    assert VobizStreamSession._is_ivr_prompt("abhi agency se karwate hain") is False


# --------------------------------------------------------------------------- #
# 2b. IVR hangup gates
# --------------------------------------------------------------------------- #
def test_ivr_hangup_default_on(monkeypatch):
    monkeypatch.delenv("IVR_HANGUP", raising=False)
    assert VobizStreamSession._ivr_hangup_on() is True
    monkeypatch.setenv("IVR_HANGUP", "0")
    assert VobizStreamSession._ivr_hangup_on() is False


def test_ivr_max_hits_default_and_floor(monkeypatch):
    monkeypatch.delenv("IVR_MAX_HITS", raising=False)
    assert VobizStreamSession._ivr_max_hits() == 2
    monkeypatch.setenv("IVR_MAX_HITS", "0")
    assert VobizStreamSession._ivr_max_hits() == 1
    monkeypatch.setenv("IVR_MAX_HITS", "garbage")
    assert VobizStreamSession._ivr_max_hits() == 2


# --------------------------------------------------------------------------- #
# 3. _is_junk — Whisper repetition-hallucination filter
# --------------------------------------------------------------------------- #
def test_is_junk_drops_hallucination_loop():
    # Verbatim from call 9 (sid bfccd8ad) — reached the LLM in prod.
    assert (
        VobizStreamSession._is_junk(
            "Aam shabd, Aam Shabd, Aam shabd, Aam shabd, Aam shabd, Aam shabd. Hello."
        )
        is True
    )


@pytest.mark.parametrize(
    "line",
    [
        "haan haan",  # genuine double-ack — 2 tokens, below threshold
        "ok ok ji",  # 3 tokens — below threshold
        "Aam shabd, agency,",  # carries real info ("agency") — must survive
        "achha theek hai ji bilkul",  # varied tokens — unique ratio high
        "haan haan haan bilkul karna hai",  # affirm burst w/ real content
    ],
)
def test_is_junk_keeps_real_speech(line):
    assert VobizStreamSession._is_junk(line) is False


# --------------------------------------------------------------------------- #
# 4. ACK -> TRIAL-CLOSE (good-call f452cce6 learning)
# --------------------------------------------------------------------------- #
VALUE_STATEMENT = (
    "Achha sir — agency 15-25K leti hai, hum 1,999 se. Inquiry follow-up bhi AI se ho jaata hai."
)


def _brain() -> TelecallerBrain:
    b = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    b.confirm_interest()
    return b


def test_bare_ack_after_value_statement_closes(monkeypatch):
    monkeypatch.delenv("ACK_TRIAL_CLOSE", raising=False)
    hist = [{"role": "assistant", "content": VALUE_STATEMENT}]
    out = _brain()._fast_path_reply(hist, "Okay.")
    assert out, "expected deterministic trial-close, got fall-through"
    assert "whatsapp number confirm" in out.lower()


@pytest.mark.parametrize("ack", ["haan", "theek hai", "bilkul", "ji", "hmm"])
def test_bare_ack_variants_close(monkeypatch, ack):
    monkeypatch.delenv("ACK_TRIAL_CLOSE", raising=False)
    hist = [{"role": "assistant", "content": VALUE_STATEMENT}]
    out = _brain()._fast_path_reply(hist, ack)
    assert out and "whatsapp number confirm" in out.lower()


def test_ack_after_question_keeps_old_flow(monkeypatch):
    """Last bot line ends with '?' => 'Okay' is an ANSWER, not a close moment."""
    monkeypatch.delenv("ACK_TRIAL_CLOSE", raising=False)
    hist = [{"role": "assistant", "content": "Google pe search karne par upar dikhta hai kya?"}]
    out = _brain()._fast_path_reply(hist, "Okay.")
    assert "whatsapp number confirm" not in (out or "").lower()


def test_ack_close_needs_confirmed_interest(monkeypatch):
    monkeypatch.delenv("ACK_TRIAL_CLOSE", raising=False)
    b = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")  # no confirm
    hist = [{"role": "assistant", "content": VALUE_STATEMENT}]
    out = b._fast_path_reply(hist, "Okay.")
    assert "whatsapp number confirm" not in (out or "").lower()


def test_ack_close_flag_off_restores_old_behavior(monkeypatch):
    monkeypatch.setenv("ACK_TRIAL_CLOSE", "0")
    hist = [{"role": "assistant", "content": VALUE_STATEMENT}]
    out = _brain()._fast_path_reply(hist, "Okay.")
    assert "whatsapp number confirm" not in (out or "").lower()


def test_negative_never_closes(monkeypatch):
    monkeypatch.delenv("ACK_TRIAL_CLOSE", raising=False)
    hist = [{"role": "assistant", "content": VALUE_STATEMENT}]
    out = _brain()._fast_path_reply(hist, "nahi")
    assert "whatsapp number confirm" not in (out or "").lower()


# --------------------------------------------------------------------------- #
# 5. Post-close wrap: dialed-path affirm fires durable close
# --------------------------------------------------------------------------- #
def test_dialed_path_affirm_fires_close_signal(monkeypatch):
    fired = []
    monkeypatch.setattr(
        TelecallerBrain, "_on_close_signal", lambda self: fired.append(True), raising=True
    )
    b = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    b.set_caller_phone("9876543210")
    hist = [
        {
            "role": "assistant",
            "content": (
                "Bilkul sir! Aaj hi shuru kar deti hoon — bas aapka WhatsApp "
                "number confirm kar dijiye, setup ki saari jaankari wahin bhej deti hoon."
            ),
        }
    ]
    out = asyncio.run(b.reply(hist, "haan yahi number hai"))
    assert fired, "dialed-path affirm did not fire _on_close_signal"
    assert "whatsapp" in out.lower()
