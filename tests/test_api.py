"""
Tests for the Leads API (app/api/leads.py).

CRUD (create/list/get/update/delete a single lead) was removed 2026-07-01 — it
only ever touched an in-memory dict with zero real callers (see the module
docstring in app/api/leads.py). These tests cover what remains — /stats/summary
— and guard against the removed CRUD routes silently reappearing.
"""

from fastapi.testclient import TestClient


class TestLeadsAPI:
    """Test the surviving (non-CRUD) leads endpoints"""

    def test_leads_summary(self, client: TestClient):
        """stats/summary responds with the expected shape even with nothing scraped yet"""
        response = client.get("/api/leads/stats/summary")
        assert response.status_code == 200

        data = response.json()
        assert "total" in data
        assert "by_status" in data
        assert "by_source" in data

    def test_leads_summary_reflects_leads_storage(self, client: TestClient):
        """The only writer left is /scrape — seed leads_storage directly (as scrape does)
        and confirm summary counts reflect it."""
        import app.api.leads as leads_mod

        leads_mod.leads_storage["t_1"] = {
            "id": "t_1",
            "status": "qualified",
            "lead_score": 80,
            "source": "google_maps",
            "city": "Mumbai",
        }
        try:
            response = client.get("/api/leads/stats/summary")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] >= 1
            assert data["by_status"]["qualified"] >= 1
        finally:
            leads_mod.leads_storage.pop("t_1", None)

    def test_crud_routes_removed(self, client: TestClient):
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
