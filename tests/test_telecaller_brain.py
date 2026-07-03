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
    assert b._script_fallback(hist) == TelecallerBrain._clean(b, disc[0])


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
    b = _brain("general")
    bad = "Yeh thoda unclear hai, maaf kijiye main phir se poochti hoon?"
    assert TelecallerBrain._clean(b, bad) == ""
    ok = "Google pe upar dikhta hai kya?"
    assert TelecallerBrain._clean(b, ok) == ok


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


def test_platform_price_uses_package_source_of_truth() -> None:
    from app.marketing.packages import get_packages

    b = _brain("ai_marketing")
    b._interest_confirmed = False
    price = next(p["price_inr_month"] for p in get_packages() if p["key"] == "starter")
    ans = TelecallerBrain._customer_qa_reply(b, "price kitna hai")
    assert f"Rs {price:,}" in ans


def test_fast_path_discloses_ai_identity() -> None:
    b = _brain("ai_marketing")
    b._interest_confirmed = False
    ans = TelecallerBrain._fast_path_reply(b, [], "aap bot ho kya")
    assert "ai assistant" in ans.lower()
    assert "swara" in ans.lower()


def test_fast_path_whatsapp_gate_qualifies_first() -> None:
    b = _brain("ai_marketing")
    b._interest_confirmed = False
    ans = TelecallerBrain._fast_path_reply(b, [], "whatsapp pe bhej do")
    assert "whatsapp" in ans.lower()
    assert "leads" in ans.lower() or "content" in ans.lower()
    assert "?" in ans


# --------------------------------------------------------------------------- #
# Fluency/coherence fixes (the "1-2 turn baad confuse, noob baat karta" batch).
# --------------------------------------------------------------------------- #
def test_clean_cuts_hallucinated_transcript() -> None:
    # Small free models kabhi poora dialogue continue kar dete hain — Swara ka
    # sirf pehla turn bolna chahiye, "User:"/"Swara:" leak nahi.
    b = _brain("general")
    out = TelecallerBrain._clean(b, "Ji theek hai sir. User: aur batao Swara: haan ji")
    low = out.lower()
    assert "user:" not in low and "swara:" not in low
    assert out.startswith("Ji theek hai")


def test_clean_strips_unclosed_paren_leak() -> None:
    # Reasoning/meta leak ek un-closed parenthetical me — cut ho jaaye.
    b = _brain("general")
    out = TelecallerBrain._clean(b, "Aap yeh kaise manage karte ho? (Lagta hai ki user")
    assert "(" not in out
    assert out.endswith("?")


def test_clean_allows_two_short_sentences() -> None:
    # Answer-then-question ek hi reply me (pehle 1-sentence cap clip kar deta tha).
    b = _brain("general")
    out = TelecallerBrain._clean(b, "Haan ji, loan ho jaata hai. Aap salaried hain ya business?")
    low = out.lower()
    assert "loan ho jaata hai" in low
    assert "salaried" in low


def test_voice_gemini_primary_flag(monkeypatch) -> None:
    # Voice-scoped Gemini-primary: only flips the telecaller brain, not the global
    # free_ai chain (so marketing/agents stay on Mistral/Groq primary).
    monkeypatch.delenv("VOICE_GEMINI_PRIMARY", raising=False)
    assert TelecallerBrain._voice_gemini_primary() is False
    monkeypatch.setenv("VOICE_GEMINI_PRIMARY", "1")
    assert TelecallerBrain._voice_gemini_primary() is True


def test_customer_qa_no_blanket_valueline_dump() -> None:
    # Vertical niche ka koi bhi off-keyword sawaal pe pehle value_lines[0] dump
    # hota tha (real_estate me har sawaal ka ek hi irrelevant jawab = confused).
    # Ab "" -> LLM context se answer kare.
    b = _brain("real_estate")
    b._interest_confirmed = False
    ans = TelecallerBrain._customer_qa_reply(b, "location kahan hai project ka")
    assert ans == ""


# --------------------------------------------------------------------------- #
# Opener parity — vertical niches MUST open with their own researched script
# opening, NOT the ai_marketing platform pitch (the "noob baat kar rahi" bug:
# web-call used brain.opening_line() which always returned UNIVERSAL_AGENT_INTRO).
# --------------------------------------------------------------------------- #
def _opener_brain(niche: str) -> TelecallerBrain:
    b = _brain(niche)
    b.voice_role = "telecaller"
    b.client_name = "Sharma Realty"
    b.niche_name = niche.replace("_", " ").title()
    b.pitch_hook = ""
    return b


def test_opening_line_vertical_uses_niche_script_not_platform_pitch() -> None:
    from app.voice_agent.universal_pitch import UNIVERSAL_AGENT_INTRO

    for niche in ("real_estate", "solar_residential", "insurance"):
        opener = TelecallerBrain.opening_line(_opener_brain(niche))
        # Must NOT be the marketing platform pitch.
        assert opener != UNIVERSAL_AGENT_INTRO, f"{niche} opened with platform pitch"
        assert "instagram" not in opener.lower(), f"{niche} leaked marketing pitch"
        assert "free trial" not in opener.lower(), f"{niche} leaked marketing pitch"
        # Client name placeholder must be filled (no raw [Company]).
        assert "[" not in opener
        # Permission-based: ends by asking for the customer's time.
        assert "?" in opener


def test_opening_line_platform_niche_still_pitches_platform() -> None:
    # ai_marketing IS the platform-selling call — it should still pitch the platform.
    opener = TelecallerBrain.opening_line(_opener_brain("ai_marketing"))
    low = opener.lower()
    assert "leads generation ai" in low or "instagram" in low


# --------------------------------------------------------------------------- #
# 2026-06-27 — "kya kya service/feature provide karte ho" deterministic answer.
# Yeh sabse common discovery sawaal roman me kisi keyword se match NAHI hota tha,
# isliye throttled free-LLM pe gir ke deflect ho jaata ("dobara boliye" / "detail
# bhej deti hoon" = noob). Ab fast-path canned answer dena chahiye (LLM-independent).
# --------------------------------------------------------------------------- #
def test_what_services_question_gets_concrete_answer() -> None:
    b = _brain("ai_marketing")
    b._interest_confirmed = False
    for q in (
        "Kya kya service provide kar rahe ho",
        "aap kya kya features dete ho",
        "ismein kya kya milega",
        "aapki services kya hain",
    ):
        ans = TelecallerBrain._customer_qa_reply(b, q)
        assert ans, f"no canned answer for: {q!r}"
        low = ans.lower()
        # Concrete product answer (services), NOT a deflection / clarify line.
        assert any(w in low for w in ("instagram", "facebook", "posts", "ads", "google"))
        assert "dobara boliye" not in low
        assert "bhej deti hoon" not in low


def test_what_services_devanagari_features_word() -> None:
    # Whisper(hi) Devanagari output — "फीचर"/"सर्विस" bhi route hona chahiye.
    b = _brain("ai_marketing")
    b._interest_confirmed = False
    ans = TelecallerBrain._customer_qa_reply(b, "इसमें क्या क्या फीचर हैं")
    assert ans
    assert any(w in ans.lower() for w in ("instagram", "posts", "ads", "google"))


# --------------------------------------------------------------------------- #
# 2026-06-27 — leftover [placeholder] never spoken. The SOURCE prompt-rule /
# KB doc ("aapka number [website/inquiry] se mila") got parroted raw → TTS bola
# "bracket website slash inquiry" = noob (live call 2026-06-26). _fill must strip.
# --------------------------------------------------------------------------- #
def test_fill_strips_leftover_source_placeholder() -> None:
    b = _brain("ai_marketing")
    b.client_name = "LeadGen AI"
    out = TelecallerBrain._fill(b, "Ji sir, number [Google/website/inquiry] se mila.")
    assert "[" not in out and "]" not in out
    assert "/" not in out  # the slash-soup inside the bracket is gone too
    assert "number" in out.lower() and "mila" in out.lower()
    # no doubled space / orphan space-before-period left behind
    assert "  " not in out
    assert " ." not in out


def test_fill_still_replaces_known_placeholders() -> None:
    b = _brain("ai_marketing")
    b.client_name = "Sharma Solar"
    out = TelecallerBrain._fill(b, "Main [Company] ki taraf se [Name] bol rahi hoon.")
    assert "Sharma Solar" in out
    assert "Swara" in out
    assert "[" not in out


def test_fill_noop_without_brackets() -> None:
    b = _brain("ai_marketing")
    b.client_name = "X"
    s = "Ji sir, bilkul — aaj setup kar doon?"
    assert TelecallerBrain._fill(b, s) == s


# --------------------------------------------------------------------------- #
# 2026-07-03 — self-pitch mode: assumptive sell + fast WhatsApp handoff,
# scoped ONLY to the ai_marketing (self-marketing) niche.
# --------------------------------------------------------------------------- #
def _system_prompt_brain(niche: str) -> TelecallerBrain:
    b = _brain(niche)
    b.client_name = "LeadGen AI"
    b.niche_name = niche
    b.pitch_hook = "AI se naye customers dilana"
    b.allowed_numbers = ""
    b.niche_script_context = ""
    b.questions = ["Aap exactly kis cheez ki talaash me hain?"]
    return b


def test_self_pitch_block_present_for_platform_niche() -> None:
    b = _system_prompt_brain("ai_marketing")
    prompt = TelecallerBrain._build_system_prompt(b)
    assert "SELF-PITCH MODE" in prompt
    assert "WHATSAPP" in prompt.upper()


def test_self_pitch_block_absent_for_client_niche() -> None:
    b = _system_prompt_brain("solar")
    prompt = TelecallerBrain._build_system_prompt(b)
    assert "SELF-PITCH MODE" not in prompt
