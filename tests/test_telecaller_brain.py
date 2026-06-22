"""Regression tests for the 2026-06-18 voice-QA fixes in TelecallerBrain.

Pure / deterministic (no LLM, no network, no heavy __init__) so they run offline
and lock in:
  V1 _script_fallback discovery-skip fix (opener excluded from the index)
  V2 _looks_like_greeting widened gate (catches client/swara/ai-assistant re-greets)

These guard against silent regression of fixes that otherwise only have
integration coverage (scripts/agent_tester.py needs a running app).
"""

from app.voice_agent.telecaller_brain import TelecallerBrain


def _brain(niche: str) -> TelecallerBrain:
    # Bypass the heavy __init__ (KB / niche-DB load) — _script_fallback only
    # needs self.niche and the static _clean helper.
    b = TelecallerBrain.__new__(TelecallerBrain)
    b.niche = niche
    return b


# --------------------------------------------------------------------------- #
# V2 — mid-call re-greet guard
# --------------------------------------------------------------------------- #
def test_looks_like_greeting_catches_regreet_variants() -> None:
    g = TelecallerBrain._looks_like_greeting
    assert g("Ji sir, main LeadGen AI ki taraf se baat kar rahi hoon, 30 second") is True
    assert g("Main Swara bol rahi hoon aapse") is True
    assert g("Namaste, main Swara bol rahi hoon Sharma Solar ki taraf se, do minute") is True


def test_looks_like_greeting_allows_normal_replies() -> None:
    g = TelecallerBrain._looks_like_greeting
    # Real discovery questions / answers must NOT be flagged (no false-positive,
    # else a good reply gets wrongly swapped for a script line).
    assert g("aapka bijli ka bill kitna aata hai") is False
    assert g("ji haan bilkul") is False
    assert g("budget approx kitna chal raha hai") is False


# --------------------------------------------------------------------------- #
# V1 — discovery-skip (opener must not consume a discovery slot)
# --------------------------------------------------------------------------- #
def test_script_fallback_starts_at_first_discovery() -> None:
    from app.voice_agent.niche_scripts import get_script

    niche = "solar_residential"
    disc = [d for d in ((get_script(niche) or {}).get("discovery") or []) if d]
    if not disc:
        return  # niche script unavailable — nothing to assert
    b = _brain(niche)
    # opener = 1 assistant turn already in history; first user reply just arrived
    hist = [
        {"role": "assistant", "content": "<opener>"},
        {"role": "user", "content": "haan boliye"},
    ]
    # Fix => idx = max(0, spoken-1) = 0 => discovery[0]. Bug returned discovery[1].
    assert b._script_fallback(hist) == TelecallerBrain._clean(disc[0])


def test_script_fallback_advances_each_turn() -> None:
    from app.voice_agent.niche_scripts import get_script

    niche = "solar_residential"
    b = _brain(niche)
    disc = [d for d in ((get_script(niche) or {}).get("discovery") or []) if d]
    if len(disc) < 2:
        return

    def fb(n_assistant: int) -> str:
        h = [{"role": "assistant", "content": disc[i]} for i in range(min(n_assistant, len(disc)))]
        h.append({"role": "user", "content": "haan"})
        return b._script_fallback(h)

    # Each extra bot turn must advance the pointer (no immediate repeat).
    assert fb(1) and fb(2) and fb(1) != fb(2)


def test_clean_rejects_meta_junk() -> None:
    bad = "Yeh thoda unclear hai, maaf kijiye main phir se poochti hoon?"
    assert TelecallerBrain._clean(bad) == ""
    ok = "Google pe upar dikhta hai kya?"
    assert TelecallerBrain._clean(ok) == ok


def test_terminal_kya_question_is_detected() -> None:
    g = TelecallerBrain._looks_like_question
    assert g("Google pe dikhta hai kya") is True
    assert g("Aap kya bechte ho") is True


def test_terminal_kya_triggers_customer_qa_reply() -> None:
    b = _brain("ai_marketing")
    b._interest_confirmed = False
    ans = TelecallerBrain._customer_qa_reply(b, "Google pe dikhta hai kya")
    assert ans
    assert "google" in ans.lower() or "audit" in ans.lower()
