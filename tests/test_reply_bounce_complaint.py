"""Bounce / complaint classification — measurable deliverability outcomes.

HARD RULE: subject text alone must NEVER classify as bounce/complaint.
Classified delivery reports must never reach the LLM path.
"""

from __future__ import annotations

import email.message
from pathlib import Path

import pytest

from app.platform import reply_agent
from app.platform.reply_agent import classify_delivery_report


def _msg(headers: dict[str, str] | None = None, payload: str = "") -> email.message.Message:
    m = email.message.Message()
    for k, v in (headers or {}).items():
        m[k] = v
    if payload:
        m.set_payload(payload)
    return m


# ---------------------------------------------------------------------------
# Hard bounce
# ---------------------------------------------------------------------------


def test_hard_bounce_mailer_daemon_with_dsn_5xx():
    body = (
        "This is an automatically generated Delivery Status Notification.\n"
        "Final-Recipient: rfc822; ramesh@example.com\n"
        "Action: failed\n"
        "Status: 5.1.1\n"
        "Diagnostic-Code: smtp; 550 5.1.1 user unknown\n"
    )
    kind = classify_delivery_report(
        "mailer-daemon@hostinger.com",
        _msg({"Content-Type": "multipart/report; report-type=delivery-status"}),
        "Undelivered Mail Returned to Sender",
        body,
    )
    assert kind == "hard_bounce"


def test_hard_bounce_bounce_localpart_alone_is_structural():
    """Bounce sender localpart is a structural signal (not subject guessing)."""
    assert classify_delivery_report("bounce@somesender.com", _msg(), "hello", "") == "hard_bounce"


def test_hard_bounce_never_reaches_llm_path():
    """Triage must short-circuit delivery reports before _classify()."""
    src = Path(reply_agent.__file__).read_text(encoding="utf-8")
    assert "delivery_kind = classify_delivery_report(frm, msg, subj, body)" in src
    assert src.index("delivery_kind = classify_delivery_report") < src.index(
        "intent = await _classify(subj, body)"
    )
    assert "outcome=delivery_kind" in src


# ---------------------------------------------------------------------------
# Soft bounce
# ---------------------------------------------------------------------------


def test_soft_bounce_dsn_4xx():
    body = (
        "Final-Recipient: rfc822; temp@example.com\n"
        "Action: delayed\n"
        "Status: 4.2.1\n"
        "Diagnostic-Code: smtp; 450 4.2.1 mailbox full\n"
    )
    kind = classify_delivery_report(
        "mailer-daemon@mx.example.com",
        _msg({"Content-Type": "multipart/report; report-type=delivery-status"}),
        "Delayed Mail",
        body,
    )
    assert kind == "soft_bounce"


# ---------------------------------------------------------------------------
# Complaint / feedback-loop
# ---------------------------------------------------------------------------


def test_complaint_feedback_type_header():
    kind = classify_delivery_report(
        "fbl@yahoo.com",
        _msg(
            {
                "Content-Type": "multipart/report; report-type=feedback-report",
                "Feedback-Type": "abuse",
            }
        ),
        "abuse report",
        "Feedback-Type: abuse\n",
    )
    assert kind == "complaint"


def test_complaint_abuse_sender():
    assert (
        classify_delivery_report("abuse@isp.example", _msg(), "spam complaint", "") == "complaint"
    )


# ---------------------------------------------------------------------------
# HARD RULE: subject alone is insufficient
# ---------------------------------------------------------------------------


def test_subject_only_does_not_classify_as_bounce():
    kind = classify_delivery_report(
        "system@example.com",
        _msg(),
        "Mail delivery failed: returning message to sender",
        "",
    )
    assert kind is None
    assert (
        reply_agent._is_bounce_message(
            "system@example.com",
            _msg(),
            "Mail delivery failed: returning message to sender",
            "",
        )
        is False
    )


def test_genuine_human_reply_not_bounce():
    assert (
        classify_delivery_report(
            "sharma.solar@gmail.com",
            _msg(),
            "Re: your email — interested",
            "Yes please share pricing for 3 shops.",
        )
        is None
    )


# ---------------------------------------------------------------------------
# Existing guards still work
# ---------------------------------------------------------------------------


def test_case_closure_still_works():
    assert reply_agent._is_case_closure("", "Not required as of now. Hence, case is closed.")


def test_auto_ack_still_works():
    assert reply_agent._is_auto_ack(_msg(), "Thank you for your interest in our services")


def test_spam_content_still_works():
    assert reply_agent._is_spam_content("Reddy Anna cricket id", "")


def test_classify_never_raises():
    assert classify_delivery_report(None, None, None, None) is None  # type: ignore[arg-type]


def test_delivery_outcomes_vocab():
    assert reply_agent._DELIVERY_OUTCOMES == ("hard_bounce", "soft_bounce", "complaint")
    for k in reply_agent._DELIVERY_OUTCOMES:
        assert k in reply_agent._STATUS


def test_auto_submitted_plus_dsn_body_is_structural():
    body = "Final-Recipient: rfc822; x@y.com\nStatus: 5.7.1\n"
    kind = classify_delivery_report(
        "noreply@mx.example",
        _msg({"Auto-Submitted": "auto-generated"}),
        "Delivery Status Notification",
        body,
    )
    assert kind == "hard_bounce"


@pytest.mark.parametrize(
    "frm,subj",
    [
        ("mailer-daemon@hostinger.com", "Undelivered Mail Returned to Sender"),
        ("postmaster@mx1.hostinger.com", "Delivery Status Notification (Failure)"),
    ],
)
def test_bounce_localparts_still_detected(frm, subj):
    assert reply_agent._is_bounce_message(frm, _msg(), subj, "") is True
