"""Tests for the Leads API (app/api/leads.py).

CRUD (create/list/get/update/delete a single lead) was removed 2026-07-01 — it
only ever touched an in-memory dict with zero real callers (see the module
docstring in app/api/leads.py). These tests cover what remains — /stats/summary
(backed by the REAL `Lead` table) and the removed-CRUD guards.

They also prove the P0-2 fix: scraped leads are persisted into the `Lead` table
(not a volatile dict) and survive a process restart, and /stats/summary reads
real DB rows back through the app's own session.
"""

from app.models.lead import Lead, LeadSource, LeadStatus


class TestLeadsAPI:
    """Test the surviving (non-CRUD) leads endpoints"""

    def test_leads_summary(self, client):
        """stats/summary responds with the expected shape (real DB, possibly empty)"""
        response = client.get("/api/leads/stats/summary")
        assert response.status_code == 200

        data = response.json()
        assert "total" in data
        assert "by_status" in data
        assert "by_source" in data

    def test_stats_summary_reads_real_db(self, client, db_session, monkeypatch):
        """P0-2 regression: /stats/summary reads the REAL `Lead` table, not a
        volatile dict. Point the app's base sync session at the same engine the
        test reads/writes so the HTTP route and the insert share one DB."""
        import app.models.base as base_mod
        from sqlalchemy.orm import sessionmaker

        _engine = db_session.bind
        _SessionLocal = sessionmaker(bind=_engine)
        # Base.metadata.create_all already done by the `db` fixture on this engine.
        monkeypatch.setattr(base_mod, "_get_sync_engine", lambda: _engine)
        monkeypatch.setattr(base_mod, "_SessionLocal", _SessionLocal)

        from app.api import leads as leads_mod

        leads_mod._save_scraped_lead_to_db(
            {
                "phone": "+919876500001",
                "company_name": "Acme Co",
                "source": "google_maps",
                "city": "Mumbai",
            }
        )
        leads_mod._save_scraped_lead_to_db(
            {
                "phone": "+919876500002",
                "company_name": "Biz B",
                "source": "google_maps",
                "city": "Delhi",
            }
        )
        leads_mod._save_scraped_lead_to_db(
            {
                "phone": "+919876500003",
                "company_name": "Biz C",
                "source": "website",
                "city": "Mumbai",
            }
        )
        db_session.commit()

        response = client.get("/api/leads/stats/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert data["by_source"].get("google_maps") == 2
        assert data["by_source"].get("website") == 1
        assert data["by_city"].get("Mumbai") == 2
        # All DB-backed scraped leads default to NEW status.
        assert data["by_status"]["new"] == 3

    def test_scraped_lead_persists_not_volatile(self, db_session, monkeypatch):
        """P0-2 regression: a scraped lead persists as a durable `Lead` row and
        dedups a repeat phone to the same existing row (no duplicate)."""
        import app.models.base as base_mod
        from sqlalchemy.orm import sessionmaker

        _engine = db_session.bind
        _SessionLocal = sessionmaker(bind=_engine)
        monkeypatch.setattr(base_mod, "_get_sync_engine", lambda: _engine)
        monkeypatch.setattr(base_mod, "_SessionLocal", _SessionLocal)

        from app.api import leads as leads_mod

        id1 = leads_mod._save_scraped_lead_to_db(
            {"phone": "+919876500010", "company_name": "Persist Co", "source": "google_maps"}
        )
        id2 = leads_mod._save_scraped_lead_to_db(
            {"phone": "+919876500010", "company_name": "Persist Co", "source": "google_maps"}
        )
        db_session.commit()
        assert id1 is not None
        assert id1 == id2, "repeat phone must reuse the existing Lead row (dedup)"

        rows = db_session.query(Lead).filter(Lead.phone == "+919876500010").all()
        assert len(rows) == 1, "scraped lead must persist as exactly one DB row"
        assert rows[0].source == LeadSource.GOOGLE_MAPS
        assert rows[0].status == LeadStatus.NEW

    def test_crud_routes_removed(self, client):
        """POST / GET / PUT / DELETE on /api/leads(/{id}) were dead in-memory
        endpoints with zero callers (empty frontend + API grep, no other module
        referenced them) — removed 2026-07-01. This guards against them
        silently reappearing. No route matches these paths anymore: GET falls
        through to the app's static-file catch-all (404 not found on disk),
        while POST/PUT/DELETE hit that same catch-all's method restriction
        (405 — matches this app's existing behavior for ANY undefined
        POST/PUT/DELETE path, not something specific to leads)."""
        sample_lead = {
            "company_name": "Test Co",
            "phone": "+919876543210",
            "city": "Mumbai",
            "category": "Real Estate",
        }
        assert client.post("/api/leads/", json=sample_lead).status_code == 405
        assert client.get("/api/leads/").status_code == 404
        assert client.get("/api/leads/some-id").status_code == 404
        assert client.put("/api/leads/some-id", json={"status": "contacted"}).status_code == 405
        assert client.delete("/api/leads/some-id").status_code == 405
