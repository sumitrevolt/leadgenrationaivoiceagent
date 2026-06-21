"""
Tests for app.voice_agent.qa_checks — the D-13 conversation QA judge half.
Pure functions; fixtures prove each check fires on a bad transcript and stays
silent on a good one.
"""

from app.voice_agent import qa_checks as qc


def test_is_soft_no():
    assert qc.is_soft_no("dekhte hain baad me")
    assert qc.is_soft_no("abhi nahi, time nahi hai")
    assert qc.is_soft_no("whatsapp pe bhej do")
    assert qc.is_soft_no("nahi chahiye")
    assert not qc.is_soft_no("haan bilkul, demo dikhao")
    assert not qc.is_soft_no("")


def test_has_permission_ask():
    assert qc.has_permission_ask("do minute baat kar sakti hoon ya busy hain?")
    assert qc.has_permission_ask("abhi sahi samay hai?")
    assert not qc.has_permission_ask("namaste, main Swara bol rahi hoon")


def test_pushy_after_softno_fires():
    # caller refuses twice; bot keeps pitching after the 2nd -> finding
    transcript = [
        {"role": "assistant", "content": "Namaste, demo dikhau?"},
        {"role": "user", "content": "abhi nahi"},
        {"role": "assistant", "content": "ek baar dekh lijiye, badhiya hai"},
        {"role": "user", "content": "dekhte hain baad me"},
        {"role": "assistant", "content": "sirf 2 minute, demo book kar du?"},
    ]
    findings = qc.check_pushy_after_softno(transcript)
    assert findings
    assert "PUSHY_AFTER_SOFTNO" in findings[0]


def test_pushy_after_softno_clean_on_graceful_exit():
    # second refusal -> bot de-escalates politely -> NOT pushy
    transcript = [
        {"role": "user", "content": "abhi nahi"},
        {"role": "assistant", "content": "koi baat nahi ji"},
        {"role": "user", "content": "dekhte hain baad me"},
        {"role": "assistant", "content": "bilkul ji, samajh gayi — aapka din accha rahe!"},
    ]
    assert qc.check_pushy_after_softno(transcript) == []


def test_talk_listen_ratio():
    chatty = [
        {"role": "assistant", "content": " ".join(["word"] * 40)},
        {"role": "user", "content": "haan"},
        {"role": "assistant", "content": " ".join(["word"] * 40)},
        {"role": "user", "content": "ok"},
    ]
    f = qc.check_talk_listen_ratio(chatty, max_ratio=0.6)
    assert f and "TALK_LISTEN_RATIO" in f
    balanced = [
        {"role": "assistant", "content": "haan boliye"},
        {"role": "user", "content": " ".join(["word"] * 20)},
        {"role": "assistant", "content": "achha samjha"},
        {"role": "user", "content": " ".join(["word"] * 20)},
    ]
    assert qc.check_talk_listen_ratio(balanced, max_ratio=0.6) is None
    # single bot turn -> not enough to judge a ratio
    assert qc.check_talk_listen_ratio([{"role": "assistant", "content": "a b c"}]) is None


def test_missing_permission():
    no_perm = [
        {"role": "assistant", "content": "Namaste, main Swara AI assistant hoon"},
        {"role": "user", "content": "haan"},
        {"role": "assistant", "content": "aapke business ke liye marketing karte hain"},
    ]
    f = qc.check_missing_permission(no_perm)
    assert f and "MISSING_PERMISSION" in f
    with_perm = [
        {"role": "assistant", "content": "Namaste — do minute baat kar sakti hoon ya busy hain?"},
        {"role": "user", "content": "haan boliye"},
    ]
    assert qc.check_missing_permission(with_perm) is None


def test_literal_translation():
    f = qc.check_literal_translation("main aapki kaise sahayata kar sakta hoon")
    assert f and "LITERAL_TRANSLATION" in f
    assert qc.check_literal_translation("haan ji, demo dikha deti hoon") is None


def test_run_all_aggregates_and_clean():
    bad = [
        {"role": "assistant", "content": "main aapki kaise sahayata karu? " + " ".join(["w"] * 50)},
        {"role": "user", "content": "abhi nahi"},
        {"role": "assistant", "content": "ek baar dekh lijiye"},
        {"role": "user", "content": "dekhte hain"},
        {"role": "assistant", "content": "demo book kar du?"},
    ]
    findings = qc.run_all(bad)
    kinds = " ".join(findings)
    assert "PUSHY_AFTER_SOFTNO" in kinds
    assert "LITERAL_TRANSLATION" in kinds
    assert "MISSING_PERMISSION" in kinds
    # a clean, permission-first, listening conversation -> no findings
    good = [
        {"role": "assistant", "content": "Namaste — do minute baat kar sakti hoon ya busy?"},
        {"role": "user", "content": " ".join(["batao"] * 15)},
        {"role": "assistant", "content": "achha, samjha"},
        {"role": "user", "content": " ".join(["aur"] * 15)},
    ]
    assert qc.run_all(good) == []


def test_never_raises_on_garbage():
    assert qc.run_all(None) == []  # type: ignore[arg-type]
    assert qc.run_all([{"bad": "shape"}, "x", 5]) == []  # type: ignore[list-item]


def test_extended_personas_run_with_stub():
    """D-13 personas drive the eval suite end-to-end without crashing (criteria
    callable, runner integrates). Uses a trivial stub manager — no network/LLM."""
    import asyncio

    from app.voice_agent.eval_suite import EXTENDED_PERSONAS, run_suite

    assert len(EXTENDED_PERSONAS) == 5

    class _Reply:
        def __init__(self, text):
            self.text = text
            self.outcome = None
            self.should_end = False

    class _StubMgr:
        def new_conversation(self):
            return type("S", (), {"finished": False, "outcome": None})()

        async def respond(self, text, state):
            return _Reply("Haan ji, do minute baat kar sakti hoon? Batao kya chahiye?")

    report = asyncio.run(run_suite(lambda: _StubMgr(), personas=EXTENDED_PERSONAS, max_turns=6))
    assert len(report.runs) == len(EXTENDED_PERSONAS)
    for p in EXTENDED_PERSONAS:
        assert p.name in report.by_persona
        assert isinstance(report.by_persona[p.name], bool)
