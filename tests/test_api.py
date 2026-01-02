"""
Tests for Leads API
"""
import pytest
from fastapi.testclient import TestClient


class TestLeadsAPI:
    """Test leads endpoints"""
    
    def test_create_lead(self, client: TestClient, sample_lead):
        """Test lead creation"""
        response = client.post("/api/leads/", json=sample_lead)
        assert response.status_code == 200
        
        data = response.json()
        assert data["company_name"] == sample_lead["company_name"]
        assert data["phone"] == sample_lead["phone"]
        assert data["status"] == "new"
        assert "id" in data
    
    def test_list_leads(self, client: TestClient, sample_lead):
        """Test listing leads"""
        # Create a lead first
        client.post("/api/leads/", json=sample_lead)
        
        response = client.get("/api/leads/")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_lead(self, client: TestClient, sample_lead):
        """Test getting a specific lead"""
        # Create a lead
        create_response = client.post("/api/leads/", json=sample_lead)
        lead_id = create_response.json()["id"]
        
        # Get the lead
        response = client.get(f"/api/leads/{lead_id}")
        assert response.status_code == 200
        assert response.json()["id"] == lead_id
    
    def test_get_lead_not_found(self, client: TestClient):
        """Test 404 for non-existent lead"""
        response = client.get("/api/leads/non-existent-id")
        assert response.status_code == 404
    
    def test_update_lead(self, client: TestClient, sample_lead):
        """Test updating a lead"""
        # Create a lead
        create_response = client.post("/api/leads/", json=sample_lead)
        lead_id = create_response.json()["id"]
        
        # Update the lead
        update_data = {"status": "contacted", "lead_score": 50}
        response = client.put(f"/api/leads/{lead_id}", json=update_data)
        
        assert response.status_code == 200
        assert response.json()["status"] == "contacted"
        assert response.json()["lead_score"] == 50
    
    def test_delete_lead(self, client: TestClient, sample_lead):
        """Test deleting a lead"""
        # Create a lead
        create_response = client.post("/api/leads/", json=sample_lead)
        lead_id = create_response.json()["id"]
        
        # Delete the lead
        response = client.delete(f"/api/leads/{lead_id}")
        assert response.status_code == 200
        
        # Verify it's deleted
        get_response = client.get(f"/api/leads/{lead_id}")
        assert get_response.status_code == 404
    
    def test_filter_leads_by_city(self, client: TestClient, sample_lead):
        """Test filtering leads by city"""
        # Create leads in different cities
        sample_lead["city"] = "Mumbai"
        client.post("/api/leads/", json=sample_lead)
        
        sample_lead["city"] = "Delhi"
        client.post("/api/leads/", json=sample_lead)
        
        # Filter by Mumbai
        response = client.get("/api/leads/?city=Mumbai")
        assert response.status_code == 200
        
        data = response.json()
        for lead in data:
            assert lead["city"].lower() == "mumbai"
    
    def test_leads_summary(self, client: TestClient, sample_lead):
        """Test leads summary endpoint"""
        # Create some leads
        for _ in range(5):
            client.post("/api/leads/", json=sample_lead)
        
        response = client.get("/api/leads/stats/summary")
        assert response.status_code == 200
        
        data = response.json()
        assert "total" in data
        assert "by_status" in data
        assert "by_source" in data
