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
    # Bypass the heavy __init__ (KB / niche-DB load). Stream/close paths still
    # need the close-state attrs that __init__ would set — missing ones get
    # swallowed by reply_stream_sentences try/except and silently miss close.
    b = TelecallerBrain.__new__(TelecallerBrain)
    b.niche = niche
    b.client_name = "Demo Co"
    b.client_id = None
    b.voice_role = "telecaller"
    b.agent_name = "Swara"
    b.memory_subject = None
    b._interest_confirmed = False
    b._discovery_skip = 0
    b.caller_phone = ""
    b.close_signal_fired = False
    b.closing_started = False
    b.final_message_queued = False
    b.final_message_played = False
    b.session_closed = False
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


def test_paid_vs_free_beats_feature_pitch() -> None:
    """Live 2026-08-06: paid/free asks that also say service/feature must get
    price facts, NOT the canned product pitch (customer heard pitch twice)."""
    from app.marketing.packages import get_packages

    b = _brain("ai_marketing")
    b._interest_confirmed = False
    starter = next(p["price_inr_month"] for p in get_packages() if p["key"] == "starter")
    utterances = (
        "पेड है की फ्री है? ये सब सर्विस जो तुम प्रोवाइड कर रहा हो वो फ्री है की पेड है?",
        "तो paid है की free है ये feature तो?",
        "paid hai ya free",
        "ye service free hai kya",
    )
    for ut in utterances:
        ans = TelecallerBrain._customer_qa_reply(b, ut)
        assert ans, ut
        low = ans.lower()
        assert f"{starter:,}" in ans or str(starter) in ans, ut
        assert "instagram-facebook pe roz posts" not in low, ut
        fp = TelecallerBrain._fast_path_reply(b, [{"role": "user", "content": "hello"}], ut)
        assert f"{starter:,}" in fp or str(starter) in fp, ut


def test_fast_path_discloses_ai_identity() -> None:
    b = _brain("ai_marketing")
    b._interest_confirmed = False
    ans = TelecallerBrain._fast_path_reply(b, [], "aap bot ho kya")
    assert "ai assistant" in ans.lower()
    assert "swara" in ans.lower()


def test_fast_path_whatsapp_is_a_handoff_not_a_qualify() -> None:
    """2026-07-03 contract change (user mandate + all-transcript analysis): a
    WhatsApp ask = channel handoff (wrap the paid call, details move to
    WhatsApp) — NOT another qualify question. The old 'leads chahiye ya
    content?' fired even right after an explicit commit in 3 real calls."""
    # Web path (no dialed number): ask them to confirm the number — the line
    # must contain 'whatsapp number confirm' so the next turn's post-close-wrap
    # catches the spoken number.
    b = _brain("ai_marketing")
    b._interest_confirmed = False
    b.caller_phone = ""
    ans = TelecallerBrain._fast_path_reply(b, [], "whatsapp pe bhej do")
    assert "whatsapp number confirm" in ans.lower()
    assert "leads chahiye ya content" not in ans.lower()


def test_fast_path_whatsapp_phone_path_fires_close_and_wraps(monkeypatch) -> None:
    # Phone path (caller_phone = the number we dialed): durable close actions
    # fire NOW and the call wraps toward WhatsApp.
    b = _brain("ai_marketing")
    b._interest_confirmed = False
    b.caller_phone = "+919876543210"
    fired = []
    monkeypatch.setattr(b, "_on_close_signal", lambda: fired.append(1), raising=False)
    ans = TelecallerBrain._fast_path_reply(b, [], "whatsapp pe details bhej do")
    assert fired, "_on_close_signal must fire on a phone-path WhatsApp handoff"
    assert "whatsapp" in ans.lower()
    assert "leads chahiye ya content" not in ans.lower()


def test_fast_path_whatsapp_negation_does_not_handoff() -> None:
    # "WhatsApp pe mat bhejo" must NOT trigger the handoff.
    b = _brain("ai_marketing")
    b._interest_confirmed = False
    b.caller_phone = ""
    ans = TelecallerBrain._fast_path_reply(b, [], "whatsapp pe mat bhejo")
    assert "whatsapp number confirm" not in ans.lower()


# --------------------------------------------------------------------------- #
# Fluency/coherence fixes (the "1-2 turn baad confuse, noob baat karta" batch).
# --------------------------------------------------------------------------- #
def test_clean_cuts_hallucinated_transcript() -> None:
    # Small free models kabhi poora dialogue continue kar dete hain — Swara ka
    # sirf pehla turn bolna chahiye, "User:"/"Swara:" leak nahi.
    # 2026-07-17: leading "Ji … sir" habit fillers bhi strip hote hain.
    b = _brain("general")
    out = TelecallerBrain._clean(b, "Ji theek hai sir. User: aur batao Swara: haan ji")
    low = out.lower()
    assert "user:" not in low and "swara:" not in low
    assert "theek hai" in low
    assert "ji sir" not in low and not low.startswith("ji ")


def test_clean_strips_unclosed_paren_leak() -> None:
    # Reasoning/meta leak ek un-closed parenthetical me — cut ho jaaye.
    b = _brain("general")
    out = TelecallerBrain._clean(b, "Aap yeh kaise manage karte ho? (Lagta hai ki user")
    assert "(" not in out
    assert out.endswith("?")


def test_clean_strips_think_block_leak() -> None:
    # 2026-08-18 agent_tester: free model ne literal "<think> Here's a thinking
    # process:..." bol diya (laundry/electronics scorecard). TTS usse bol deta
    # — strip karo, real answer bachao.
    b = _brain("general")
    out = TelecallerBrain._clean(
        b,
        "<think> Here's a thinking process: 1. Analyze User Input: - User said: "
        'home pickup dete ho kya"</think> Haan ji, home pickup bilkul milta hai.'
        " Kab theek rahega?",
    )
    assert "<think" not in out.lower()
    assert "thinking process" not in out.lower()
    assert "home pickup" in out.lower()


def test_clean_strips_unclosed_think_tag() -> None:
    # Unclosed <think... (koi closing tag nahi) — tag se pehle ka hissa bachao.
    b = _brain("general")
    out = TelecallerBrain._clean(b, "Namaste! <think> yahan reasoning hai bina close")
    assert "<think" not in out.lower()
    assert "namaste" in out.lower()


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

    for niche in ("real_estate_luxury", "solar_residential", "insurance"):
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


# --------------------------------------------------------------------------- #
# 2026-07-03 — reply_stream_sentences() was missing the post-close-wrap and
# buy/close-signal short-circuits that reply() already had. Since
# USE_LLM_STREAM_TTS=1 routes every real phone call through the STREAM path
# (not reply()), a real caller's explicit close signal never short-circuited
# on a live call — confirmed with a real 2026-07-03 test-call transcript
# ("प्री प्लान एक्टिवेट करो" got "Ji, zara dobara boliye?" instead of a
# close-confirm). These tests lock in that the stream path now matches reply().
# --------------------------------------------------------------------------- #
async def test_stream_reply_close_signal_short_circuits_before_llm() -> None:
    b = _brain("ai_marketing")
    b.close_signal_fired = False
    b.caller_phone = ""
    out: list[str] = []
    async for sent in TelecallerBrain.reply_stream_sentences(b, [], "प्री प्लान एक्टिवेट करो।"):
        out.append(sent)
    text = " ".join(out)
    assert "WhatsApp" in text
    assert "shuru kar deti hoon" in text


async def test_stream_reply_resets_close_signal_fired_per_turn() -> None:
    """Mirror reply(): sticky prior-turn close_signal_fired must clear on stream entry."""
    b = _brain("ai_marketing")
    b.close_signal_fired = True
    b.caller_phone = ""
    out: list[str] = []
    async for sent in TelecallerBrain.reply_stream_sentences(b, [], "ok"):
        out.append(sent)
    # No phone + non-close utterance => _on_close_signal cannot re-set the flag.
    assert b.close_signal_fired is False
    assert out  # stream still yields something (fast-path/script/fallback)


async def test_stream_reply_post_close_wrap_pivots_to_whatsapp() -> None:
    b = _brain("ai_marketing")
    b.close_signal_fired = False
    b.caller_phone = ""
    history = [
        {
            "role": "assistant",
            "content": "Bilkul sir! Aaj hi shuru kar deti hoon — bas aapka WhatsApp number confirm kar dijiye.",
        }
    ]
    out: list[str] = []
    async for sent in TelecallerBrain.reply_stream_sentences(
        b, history, "haan yahi number 9876543210"
    ):
        out.append(sent)
    text = " ".join(out)
    assert "WhatsApp" in text
    assert "9 8 7 6 5 4 3 2 1 0" in text


# --------------------------------------------------------------------------- #
# 2026-07-03 — all-transcript learnings: repeat-ask hard cap (rule 12 was
# prompt-only; 5 real calls had 2-4x "zara dobara boliye") + stream first-
# sentence guards (the stream path yielded raw LLM output with none of
# reply()'s post-LLM protections).
# --------------------------------------------------------------------------- #
def test_note_repeat_ask_allows_exactly_one_per_call() -> None:
    b = _brain("general")
    assert TelecallerBrain._note_repeat_ask(b) is True  # first: allowed
    assert TelecallerBrain._note_repeat_ask(b) is False  # second: hard-blocked
    assert TelecallerBrain._note_repeat_ask(b) is False


async def test_stream_repeat_ask_on_clear_sentence_falls_back_to_reply(monkeypatch) -> None:
    """LLM streams 'Ji, zara dobara boliye?' against a fully clear substantive
    complaint (verbatim shape from a real 2026-07-03 call) — the stream must NOT
    speak it; it abandons the stream and uses reply()'s guarded output."""
    b = _brain("ai_marketing")
    b.close_signal_fired = False
    b.caller_phone = ""

    async def _fake_kb(_ut):
        return []

    def _fake_prompt(_h, _u, _f):
        return "prompt"

    async def _fake_tokens(**_kw):
        yield "Ji, zara dobara boliye?"

    from app.voice_agent import free_ai

    monkeypatch.setattr(b, "_kb_facts", _fake_kb, raising=False)
    monkeypatch.setattr(b, "_build_prompt", _fake_prompt, raising=False)
    monkeypatch.setattr(free_ai, "chat_stream", _fake_tokens)

    async def _guarded_reply(_h, _u):
        return "Aapko product marketing ke liye ready leads chahiye — Instagram ya Google se?"

    monkeypatch.setattr(b, "reply", _guarded_reply, raising=False)

    out: list[str] = []
    async for sent in TelecallerBrain.reply_stream_sentences(
        b,
        [],
        "मेरी बात का जवाब दो, मुझे product marketing के लिए leads chahiye aur aap दूसरी baat कर रही हो",
    ):
        out.append(sent)
    text = " ".join(out)
    assert "dobara boliye" not in text.lower()
    assert "leads" in text.lower()


# --------------------------------------------------------------------------- #
# 2026-07-03 — THIRD parallel-brain gap: with VOICE_TOOLS=1 (live on VPS),
# _on_utterance routes every turn through reply_with_tools() FIRST, which was
# "fully isolated" from reply()/reply_stream_sentences and had NO close-signal
# guards. Real 21:42 IST call: "final karo, pre-plan start karo." (verified
# _is_close_intent=True in the live container) still got a discovery question.
# All THREE brains are now pinned on the close path.
# --------------------------------------------------------------------------- #
async def test_tools_path_close_signal_short_circuits_before_llm() -> None:
    b = _brain("ai_marketing")
    b.close_signal_fired = False
    b.caller_phone = ""
    spoken, tool_call = await TelecallerBrain.reply_with_tools(
        b,
        [{"role": "assistant", "content": "Ek baar free me try karke dekhna chahenge?"}],
        "final karo, pre-plan start karo.",
        registry=None,
    )
    assert tool_call is None
    assert "WhatsApp" in spoken
    assert "shuru kar deti hoon" in spoken


async def test_tools_path_post_close_wrap_pivots_to_whatsapp() -> None:
    b = _brain("ai_marketing")
    b.close_signal_fired = False
    b.caller_phone = ""
    history = [
        {
            "role": "assistant",
            "content": "Bilkul sir! Aaj hi shuru kar deti hoon — bas aapka WhatsApp number confirm kar dijiye.",
        }
    ]
    spoken, tool_call = await TelecallerBrain.reply_with_tools(
        b, history, "haan yahi number 9876543210", registry=None
    )
    assert tool_call is None
    assert "WhatsApp" in spoken
    assert "9 8 7 6 5 4 3 2 1 0" in spoken


# --------------------------------------------------------------------------- #
# 2026-07-17 — live-call quality: no habit fillers; clear product facts
# --------------------------------------------------------------------------- #
def test_clean_strips_banned_habit_fillers() -> None:
    b = _brain("ai_marketing")
    out = TelecallerBrain._clean(b, "Ji sir, haan ji — AI se posts aur ads automatic.")
    low = out.lower()
    assert "ji sir" not in low
    assert "haan ji" not in low
    assert "haji" not in low
    assert "posts" in low or "ads" in low
    # AI disclosure still allowed when present
    disclosed = TelecallerBrain._clean(b, "Main ek AI assistant hoon. Posts automatic.")
    assert "ai assistant" in disclosed.lower()


def test_product_qa_has_clear_facts_without_sir_filler() -> None:
    b = _brain("ai_marketing")
    b._interest_confirmed = False
    feat = TelecallerBrain._customer_qa_reply(b, "aap kya kya features dete ho")
    assert feat
    low = feat.lower()
    assert any(w in low for w in ("instagram", "facebook", "posts", "ads", "google"))
    assert " ji" not in f" {low}"
    assert not low.startswith("sir")
    assert "sir —" not in low and "sir," not in low
    price = TelecallerBrain._customer_qa_reply(b, "price kitna hai")
    assert "1,999" in price or "1999" in price
    assert "5,999" in price or "5999" in price
    assert "sir" not in price.lower()
    eng = TelecallerBrain._customer_qa_reply(b, "okay so what do you guys do exactly")
    assert eng
    elow = eng.lower()
    assert any(w in elow for w in ("instagram", "facebook", "posts", "ads", "marketing"))
    assert "sir" not in elow


def test_thinking_filler_texts_have_no_address_fillers() -> None:
    from app.telephony import vobiz_stream as vs

    banned = ("ji sir", "sir", "haji", "achha ji", "haan ji")
    for t in vs._FILLER_TEXTS:
        low = t.lower()
        assert not any(b in low for b in banned), t
