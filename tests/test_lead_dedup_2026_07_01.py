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
