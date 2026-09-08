"""Cross-tenant READ isolation guard for the customer dashboard (§5 top invariant:
"lead data cross-client leak KABHI nahi").

`GET /api/customer/dashboard` builds its lead list from `_build_from_db()`, which
DB-filters by `Lead.assigned_to == client_id`. The auth side (token.sub, IDOR) is
already covered (test_billing_auth_idor / test_customer_portal / test_lead_override_
ownership), but there was NO read-side test that a customer only ever sees its OWN
leads on the dashboard. A future regression that widened or dropped that filter would
leak another tenant's leads with no failing test.

These use a REAL in-memory SQLite session (mirrors _office_db in test_customer_office.py)
so the actual SQLAlchemy `.filter(Lead.assigned_to == ...)` runs — a mocked DB that
ignored the filter would hide exactly the bug this guards.
"""

from __future__ import annotations


def _iso_db(monkeypatch):
    """Wire app.models.base to a fresh in-memory SQLite so get_db_session() uses it."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.models.base as base_mod

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine)
    base_mod.Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(base_mod, "_engine", engine)
    monkeypatch.setattr(base_mod, "_SessionLocal", Session)
    return Session


def _seed_two_clients(Session):
    from app.models.lead import Lead, LeadStatus

    s = Session()
    try:
        s.add_all(
            [
                Lead(
                    id="lead_a1",
                    company_name="A Biz Alpha",
                    phone="9990000001",
                    assigned_to="client_a",
                    status=LeadStatus.NEW,
                ),
                Lead(
                    id="lead_b1",
                    company_name="B Biz Beta",
                    phone="9990000003",
                    assigned_to="client_b",
                    status=LeadStatus.NEW,
                ),
            ]
        )
        s.commit()
    finally:
        s.close()


def test_dashboard_leads_scoped_to_own_client(monkeypatch):
    Session = _iso_db(monkeypatch)
    _seed_two_clients(Session)
    from app.api.customer_dashboard_builders import _build_from_db

    resp_a = _build_from_db(client_id="client_a", campaign=None)
    assert resp_a is not None, "DB path should build a response from the seeded test DB"
    biz_a = [lr.business for lr in resp_a.leads]
    assert "A Biz Alpha" in biz_a, "client_a must see its own lead"
    assert "B Biz Beta" not in biz_a, "client_a must NEVER see client_b's lead"

    resp_b = _build_from_db(client_id="client_b", campaign=None)
    assert resp_b is not None
    biz_b = [lr.business for lr in resp_b.leads]
    assert "B Biz Beta" in biz_b, "client_b must see its own lead"
    assert "A Biz Alpha" not in biz_b, "client_b must NEVER see client_a's lead"


def test_dashboard_zero_for_client_with_no_data(monkeypatch):
    """A client with no rows gets an honest empty list — never another tenant's leads."""
    Session = _iso_db(monkeypatch)
    _seed_two_clients(Session)
    from app.api.customer_dashboard_builders import _build_from_db

    resp_c = _build_from_db(client_id="client_c_no_data", campaign=None)
    biz_c = [lr.business for lr in (resp_c.leads if resp_c else [])]
    assert "A Biz Alpha" not in biz_c and "B Biz Beta" not in biz_c, (
        "a client with no data must never inherit another tenant's leads"
    )
