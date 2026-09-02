"""backfill_bounce_outcomes — dry-run / apply / idempotent / no PII."""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.interaction import Interaction
from app.platform.reply_agent import classify_delivery_report
from scripts.backfill_bounce_outcomes import KNOWN_SEND_DENOMINATOR, plan, run


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _add_other(engine, iid: str, body: str, meta: str = "{}"):
    Session = sessionmaker(bind=engine)
    with Session() as db:
        db.add(
            Interaction(
                id=iid,
                channel="email",
                direction="in",
                body_summary=body,
                outcome="other",
                meta_json=meta,
            )
        )
        db.commit()


def test_plan_classifies_hard_soft_complaint_and_leaves_subject_only():
    rows = [
        (
            "h1",
            "Final-Recipient: rfc822; a@b.com\nStatus: 5.1.1\nmailer-daemon@",
            "{}",
        ),
        (
            "s1",
            "Final-Recipient: rfc822; a@b.com\nStatus: 4.2.1\nmailer-daemon@",
            "{}",
        ),
        (
            "c1",
            "Feedback-Type: abuse\nreport-type=feedback-report",
            '{"from":"abuse@isp.example"}',
        ),
        (
            "x1",
            "",  # subject-only would live in meta; empty body + no structural → unchanged
            '{"subject":"Mail delivery failed: returning message to sender"}',
        ),
    ]
    p = plan(rows, classify_delivery_report)
    assert p["updates"]["h1"] == "hard_bounce"
    assert p["updates"]["s1"] == "soft_bounce"
    assert p["updates"]["c1"] == "complaint"
    assert "x1" not in p["updates"]
    assert p["stats"]["to_reclassify"] == 3
    assert p["stats"]["unchanged"] == 1


def test_dry_run_writes_nothing():
    engine = _engine()
    _add_other(
        engine,
        "d1",
        "Final-Recipient: rfc822; a@b.com\nStatus: 5.1.1\nmailer-daemon@",
    )
    r = run(engine, classify_delivery_report, apply=False)
    assert r["applied"] is False
    assert r["updated"] == 0
    assert "d1" in r["updates"]
    with engine.connect() as conn:
        outcome = conn.execute(text("select outcome from interactions where id='d1'")).scalar_one()
    assert outcome == "other"


def test_apply_idempotent_and_no_pii_in_stats():
    engine = _engine()
    _add_other(
        engine,
        "a1",
        "Final-Recipient: rfc822; secret.person@example.com\nStatus: 5.1.1\nmailer-daemon@",
    )
    r1 = run(engine, classify_delivery_report, apply=True)
    assert r1["applied"] is True
    assert r1["updated"] == 1
    # Stats keys are counts only — never echo body/email.
    blob = str(r1["stats"])
    assert "secret.person" not in blob
    assert "@example.com" not in blob

    r2 = run(engine, classify_delivery_report, apply=True)
    # Second apply: candidate set is empty (no longer outcome=other).
    assert r2["candidate_count"] == 0
    assert r2["updated"] == 0
    with engine.connect() as conn:
        outcome = conn.execute(text("select outcome from interactions where id='a1'")).scalar_one()
    assert outcome == "hard_bounce"


def test_known_denominator_constant():
    assert KNOWN_SEND_DENOMINATOR == 2543
