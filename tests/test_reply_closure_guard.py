"""Case-closure guard — stops ticketing auto-responders faking "interested".

Production audit 2026-07-25:

    interactions with outcome='interested'  = 304
    ...of which from ONE adityabirla.com ticketing address = 292
    distinct email addresses that ever replied "interested" = 9

The bodies were explicit REFUSALS classified as the opposite:

    "Not related to Birla Opus. Hence , closed."
    "Not required as of now. Hence, case is closed."
    "We regret to inform you that after careful consideration, we ha..."

`_is_auto_ack` (07-07) already names this exact sender but only matches
acknowledgement wording and only scans the SUBJECT, so closure notices sailed
past it into the LLM and came back "interested".

The real-body strings below are copied from production rows (company name kept
because it is a business identity in a B2B outreach reply, not personal data).
"""

from __future__ import annotations

import pytest

from app.platform.reply_agent import _is_case_closure

# --- verbatim shapes seen in production -----------------------------------
REAL_CLOSURES = [
    "Dear Sir/Madam,\n\nNot related to Birla Opus. Hence , closed.\n\nRegards\nTeam BirlaOpus",
    "Dear Sir/Madam,\n\nNot required as of now. Hence, case is closed.",
    "Dear Customer,\n\nI hope this message finds you well.\n\nWe regret to inform you "
    "that after careful consideration, we have decided not to proceed.",
]


# Rows the guard also removes that were sitting under other outcomes. All were
# inspected in production: every one is an autoresponder/rejection, not a
# prospect. Kept here so a future narrowing of the regex has to face them.
REAL_NON_PROSPECT_UNDER_OTHER_OUTCOMES = [
    # was outcome='question' — bulk institutional autoresponder, not a question
    "Dear Student,\n\nThank you for raising your concern. We regret to inform you "
    "that the information you have provided is insufficient. Kindly visit the portal.",
    # was outcome='question' — wrong-recipient rejection
    "Dear Customer,\n\nUnfortunately, it appears that your query is not related to "
    "Birla Opus Paints. You have reached the wrong desk.",
    # was outcome='objection' — explicit refusal
    "Dear Customer,\n\nWe regret to inform you that after careful consideration, "
    "we have decided not to proceed with this.",
]


@pytest.mark.parametrize("body", REAL_CLOSURES)
def test_catches_real_production_closures(body):
    assert _is_case_closure("", body) is True


@pytest.mark.parametrize("body", REAL_NON_PROSPECT_UNDER_OTHER_OUTCOMES)
def test_catches_rejections_filed_under_other_outcomes(body):
    """These were classified question/objection, but they are still refusals.

    Production check: the guard's only overlap with non-"interested" human
    replies was 6 rows matching `we regret to inform` and 1 matching
    `not related to` — every one an autoresponder or an explicit no.
    """
    assert _is_case_closure("", body) is True


def test_catches_closure_in_subject_too():
    assert _is_case_closure("Your case is closed", "") is True


def test_scans_body_not_just_subject():
    """The 07-07 auto-ack guard only read the subject — that is how these got through."""
    assert _is_case_closure("Re: your enquiry", "Not required as of now.") is True


@pytest.mark.parametrize(
    "text",
    [
        "ticket has been closed",
        "closing this request",
        "no further requirement",
        "not required at this time",
        "not required currently",
    ],
)
def test_catches_closure_variants(text):
    assert _is_case_closure("", text) is True


# --- the part that matters most: do NOT eat real prospects ----------------
@pytest.mark.parametrize(
    "body",
    [
        "Yes, we are interested. Please share pricing.",
        "Sounds good — can you do a demo on Tuesday?",
        "What is the cost for 3 months?",
        "Please call me tomorrow, I want to know more.",
        "We already have a vendor but send details anyway.",
        "Interested. Kitna charge karte ho?",
        # near-miss wording that must NOT trip the guard
        "The case study you sent was useful.",
        "We closed our last funding round, so budget exists.",
        "Not sure yet, but tell me more.",
    ],
)
def test_does_not_false_positive_on_genuine_replies(body):
    assert _is_case_closure("", body) is False


def test_empty_input_is_safe():
    assert _is_case_closure("", "") is False
    assert _is_case_closure(None, None) is False  # type: ignore[arg-type]


# --- operator controls -----------------------------------------------------
def test_guard_can_be_disabled(monkeypatch):
    monkeypatch.setenv("REPLY_CLOSURE_GUARD", "0")
    assert _is_case_closure("", "Not required as of now.") is False


def test_extra_terms_env_adds_patterns_without_deploy(monkeypatch):
    monkeypatch.setenv("REPLY_CLOSURE_EXTRA_TERMS", "kindly ignore,do not contact")
    assert _is_case_closure("", "Kindly ignore this thread.") is True
    assert _is_case_closure("", "Something unrelated.") is False


def test_never_raises(monkeypatch):
    monkeypatch.setenv("REPLY_CLOSURE_GUARD", "1")
    assert _is_case_closure(object(), object()) is False  # type: ignore[arg-type]


# --- wiring ----------------------------------------------------------------
def test_guard_runs_before_llm_classification():
    """Dropping after the LLM call would still burn tokens and could still write
    a fake-hot row — it must short-circuit like the other guards."""
    from pathlib import Path

    src = (
        Path(__file__)
        .resolve()
        .parent.parent.joinpath("app", "platform", "reply_agent.py")
        .read_text(encoding="utf-8")
    )
    assert "if _is_case_closure(subj, body):" in src
    assert 'res["case_closure"]' in src
    # must sit ahead of the spam guard, which itself is pre-LLM
    assert src.index("if _is_case_closure(subj, body):") < src.index(
        "if _is_spam_content(subj, body):"
    )
