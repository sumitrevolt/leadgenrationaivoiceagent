"""Lead status transition wiring + backfill (2026-07-25).

Covers the two-part change that finally moves leads off status='new':
  * Lead.mark_contacted() - the forward NEW->CONTACTED promotion helper
  * interaction_log.record() firing it on an OUTBOUND touch
  * scripts/backfill_lead_status.py repairing history for existing outbound leads

Hard constraints exercised: closure-noise never yields a positive status,
already-advanced leads are never downgraded, idempotent re-runs, dry-run writes
nothing.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.interaction import Interaction
from app.models.lead import Lead, LeadStatus, LeadStatusHistory
from app.platform.reply_agent import _CLOSURE_RE
from scripts.backfill_lead_status import plan, run


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine)()


def _lead(lead_id: str, status: LeadStatus = LeadStatus.NEW, **kw) -> Lead:
    return Lead(
        id=lead_id,
        company_name=kw.get("company_name", "Test Co"),
        phone=kw.get("phone", "9198765432"),
        email=kw.get("email", f"{lead_id}@example.com"),
        status=status,
    )


# ---------------------------------------------------------------------------
# Lead.mark_contacted() - the forward mechanism
# ---------------------------------------------------------------------------


def test_mark_contacted_promotes_new_and_writes_history():
    _, db = _session()
    lead = _lead("l-new")
    db.add(lead)
    db.commit()

    lead.mark_contacted("outreach")
    db.commit()

    assert lead.status == LeadStatus.CONTACTED
    rows = db.query(LeadStatusHistory).filter_by(lead_id="l-new").all()
    assert len(rows) == 1
    assert rows[0].old_status == "new"
    assert rows[0].new_status == "contacted"
    assert rows[0].changed_by == "outreach"


def test_mark_contacted_idempotent_second_call_is_noop():
    _, db = _session()
    lead = _lead("l-idem")
    db.add(lead)
    db.commit()

    lead.mark_contacted("outreach")
    db.commit()
    lead.mark_contacted("outreach")  # already contacted -> no-op
    db.commit()

    assert lead.status == LeadStatus.CONTACTED
    assert db.query(LeadStatusHistory).filter_by(lead_id="l-idem").count() == 1


def test_mark_contacted_never_downgrades_advanced_lead():
    _, db = _session()
    lead = _lead("l-adv", status=LeadStatus.QUALIFIED)
    db.add(lead)
    db.commit()

    lead.mark_contacted("outreach")
    db.commit()

    assert lead.status == LeadStatus.QUALIFIED  # untouched
    assert db.query(LeadStatusHistory).filter_by(lead_id="l-adv").count() == 0


# ---------------------------------------------------------------------------
# backfill plan() - pure decision logic
# ---------------------------------------------------------------------------


def test_plan_promotes_new_lead_with_real_outbound_touch():
    rows = [("A", "Hi, quick idea for your clinic")]
    p = plan(rows, {"A"}, _CLOSURE_RE)
    assert p["promote"] == ["A"]
    assert p["stats"]["to_promote"] == 1


def test_plan_excludes_closure_noise_body():
    # The exact adityabirla ticketing autoresponder wording.
    rows = [("A", "Not required as of now. Hence, case is closed.")]
    p = plan(rows, {"A"}, _CLOSURE_RE)
    assert p["promote"] == []
    assert p["stats"]["closure_noise_rows"] == 1
    assert p["stats"]["leads_closure_noise_only"] == 1


def test_plan_lead_with_both_closure_and_real_touch_is_promoted():
    rows = [
        ("A", "Hence, case is closed."),  # noise
        ("A", "Following up on our proposal"),  # real
    ]
    p = plan(rows, {"A"}, _CLOSURE_RE)
    assert p["promote"] == ["A"]


def test_plan_skips_lead_already_past_new():
    rows = [("A", "Following up on our proposal")]
    p = plan(rows, set(), _CLOSURE_RE)  # A is NOT among status='new'
    assert p["promote"] == []
    assert p["stats"]["already_advanced_skipped"] == 1


# ---------------------------------------------------------------------------
# backfill run() - against a real (sqlite) engine
# ---------------------------------------------------------------------------


def _seed_backfill_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    # NEW lead with a genuine outbound email -> should promote
    db.add(_lead("promote-me"))
    # NEW lead whose only outbound touch is closure-noise -> must NOT promote
    db.add(_lead("noise-only"))
    # Already-advanced lead with outbound -> must NOT be downgraded
    db.add(_lead("already-qual", status=LeadStatus.QUALIFIED))
    db.commit()
    db.add(
        Interaction(
            id="i1",
            lead_id="promote-me",
            channel="email",
            direction="out",
            body_summary="Idea for you",
        )
    )
    db.add(
        Interaction(
            id="i2",
            lead_id="noise-only",
            channel="email",
            direction="out",
            body_summary="Not required as of now. Hence, case is closed.",
        )
    )
    db.add(
        Interaction(
            id="i3",
            lead_id="already-qual",
            channel="email",
            direction="out",
            body_summary="Proposal v2",
        )
    )
    # an INBOUND row must never drive a promotion
    db.add(
        Interaction(
            id="i4",
            lead_id="promote-me",
            channel="email",
            direction="in",
            body_summary="tell me more",
        )
    )
    db.commit()
    db.close()
    return engine


def test_run_dry_run_writes_nothing():
    engine = _seed_backfill_db()
    r = run(engine, _CLOSURE_RE, apply=False)
    assert r["applied"] is False
    assert r["promote"] == ["promote-me"]
    with engine.connect() as conn:
        assert (
            conn.execute(text("select status from leads where id='promote-me'")).scalar() == "new"
        )
        assert conn.execute(text("select count(*) from lead_status_history")).scalar() == 0


def test_run_apply_promotes_only_real_touch_and_is_idempotent():
    engine = _seed_backfill_db()

    r1 = run(engine, _CLOSURE_RE, apply=True)
    assert r1["promoted"] == 1
    assert r1["history"] == 1

    with engine.connect() as conn:
        assert (
            conn.execute(text("select status from leads where id='promote-me'")).scalar()
            == "contacted"
        )
        assert (
            conn.execute(text("select status from leads where id='noise-only'")).scalar() == "new"
        )
        assert (
            conn.execute(text("select status from leads where id='already-qual'")).scalar()
            == "qualified"
        )
        hist = conn.execute(
            text(
                "select old_status,new_status,changed_by from lead_status_history where lead_id='promote-me'"
            )
        ).all()
        assert len(hist) == 1
        assert (
            hist[0][0] == "new" and hist[0][1] == "contacted" and hist[0][2] == "backfill:outreach"
        )

    # Re-run: everything already advanced -> no-op, no duplicate history.
    r2 = run(engine, _CLOSURE_RE, apply=True)
    assert r2["promoted"] == 0
    assert r2["history"] == 0
    with engine.connect() as conn:
        assert conn.execute(text("select count(*) from lead_status_history")).scalar() == 1


# ---------------------------------------------------------------------------
# interaction_log.record() end-to-end - transition fires on an outbound touch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_outbound_interaction_record_promotes_lead(async_db, monkeypatch, tmp_path):
    from app.models.base import get_async_session
    from app.platform import interaction_log

    # Do not pollute the repo's data/interactions.jsonl during the test.
    monkeypatch.setattr(interaction_log, "_JSONL", lambda: str(tmp_path / "interactions.jsonl"))

    async with get_async_session() as s:
        s.add(_lead("lead-fwd", email="fwd@example.com"))
        await s.commit()

    await interaction_log.record(
        channel="email",
        direction="out",
        email="fwd@example.com",
        body_summary="Hi, quick idea for your business",
        outcome="sent",
    )

    async with get_async_session() as s:
        lead = await s.get(Lead, "lead-fwd")
        assert lead is not None and lead.status == LeadStatus.CONTACTED
        rows = (
            await s.execute(
                text(
                    "select old_status,new_status,changed_by from lead_status_history "
                    "where lead_id='lead-fwd'"
                )
            )
        ).all()
        assert len(rows) == 1
        assert rows[0][0] == "new" and rows[0][1] == "contacted" and rows[0][2] == "outreach"
