"""Lead phone-dedup regression tests (F-DB2, production audit 2026-07-01).

app/api/public_site.py::_save_lead_db was the one real-DB Lead() write path
with no dedup-by-phone check (app/platform/prospector.py and app/tasks/sync.py
already had it). Fixed to match that established convention: a repeat inquiry
from the same phone updates the existing lead instead of creating a duplicate.

Self-contained (in-memory SQLite, monkeypatched onto app.models.base) — does
NOT touch the shared test DB or the real dev DB, since app/api/public_site.py
talks to app.models.base's sync session directly rather than through the
FastAPI get_db dependency that tests/conftest.py overrides.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.lead import Lead


def _isolated_db(monkeypatch):
    """Point app.models.base's sync session at a fresh in-memory engine."""
    import app.models.base as base_mod

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    monkeypatch.setattr(base_mod, "_get_sync_engine", lambda: engine)
    monkeypatch.setattr(base_mod, "_SessionLocal", session_factory)
    return session_factory


def test_repeat_inquiry_same_phone_updates_existing_lead(monkeypatch):
    session_factory = _isolated_db(monkeypatch)
    from app.api.public_site import _save_lead_db

    id1 = _save_lead_db(
        {"phone": "+919876500001", "business_name": "Acme Co", "message": "first inquiry"}
    )
    id2 = _save_lead_db(
        {"phone": "+919876500001", "business_name": "Acme Co", "message": "second inquiry"}
    )

    assert id1 is not None
    assert id1 == id2, "repeat inquiry from the same phone must reuse the existing lead"

    s = session_factory()
    try:
        rows = s.query(Lead).filter(Lead.phone == "+919876500001").all()
        assert len(rows) == 1, "must not create a duplicate Lead row for the same phone"
        assert "first inquiry" in rows[0].notes
        assert "second inquiry" in rows[0].notes
    finally:
        s.close()


def test_different_phones_create_separate_leads(monkeypatch):
    session_factory = _isolated_db(monkeypatch)
    from app.api.public_site import _save_lead_db

    id1 = _save_lead_db({"phone": "+919876500002", "business_name": "Biz A"})
    id2 = _save_lead_db({"phone": "+919876500003", "business_name": "Biz B"})

    assert id1 != id2

    s = session_factory()
    try:
        assert s.query(Lead).count() == 2
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# Format-variant-aware dedupe (2026-07-04 dialer-sprint audit follow-on)
#
# The dedup checks above (prospector.py, sync.py, scraping.py) all did an
# EXACT-STRING `Lead.phone == candidate` comparison. Every path normalizes its
# OWN candidate before comparing, but none accounts for the DB already holding
# the SAME number in a DIFFERENT raw format from another path — e.g.
# prospector.py stores digits-only "919967993679" while the CRM/sheet import
# path stores "+919967993679". Exact-match silently misses this, so a live
# scan (2026-07-04) found REAL businesses duplicated across sources: same
# company_name/phone, one row from "import" (with "+"), one from
# "google_maps" (without) — polluting dialer lists with double-dials.
# --------------------------------------------------------------------------- #
from app.models.lead import lead_exists_for_phone, phone_format_variants


def test_phone_format_variants_covers_common_indian_formats():
    variants = phone_format_variants("+91 99679-93679")
    assert "9967993679" in variants
    assert "919967993679" in variants
    assert "+919967993679" in variants
    assert "09967993679" in variants


def test_phone_format_variants_empty_for_unparseable():
    assert phone_format_variants("") == []
    assert phone_format_variants("12345") == []  # < 10 digits
    assert phone_format_variants(None) == []


def test_lead_exists_for_phone_matches_across_raw_formats(monkeypatch):
    """The actual production bug: a lead stored WITH '+91' must be found when
    the candidate arrives WITHOUT it (and vice versa)."""
    session_factory = _isolated_db(monkeypatch)
    s = session_factory()
    try:
        s.add(Lead(id="l1", company_name="Test Co", phone="+919967993679"))
        s.commit()
        # Candidate arrives digits-only (as prospector.py always stores) —
        # must still be recognised as the SAME number.
        assert lead_exists_for_phone(s, "919967993679") is True
        assert lead_exists_for_phone(s, "9967993679") is True
        assert lead_exists_for_phone(s, "09967993679") is True
        # A genuinely different number must NOT match.
        assert lead_exists_for_phone(s, "9111111111") is False
    finally:
        s.close()


def test_prospector_persist_dedupes_across_raw_formats(monkeypatch):
    """End-to-end regression: prospector._persist_prospect_to_db must not
    create a second Lead row when the same business already exists under a
    different raw phone format (the exact real-world scenario found live)."""
    session_factory = _isolated_db(monkeypatch)
    from app.platform import prospector

    # Simulate the CRM/sheet-import path's format: leading "+".
    s = session_factory()
    try:
        s.add(Lead(id="seed1", company_name="Passport Office Solapur", phone="+916019377936"))
        s.commit()
    finally:
        s.close()

    # prospector's own ingestion (digits-only) rediscovers the SAME business.
    created = prospector._persist_prospect_to_db(
        {"phone": "+916019377936", "business_name": "Passport Office Solapur"}
    )
    assert created is False, "must dedupe, not insert a second row"

    s = session_factory()
    try:
        assert s.query(Lead).count() == 1
    finally:
        s.close()
