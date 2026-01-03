# LeadGen AI Voice Agent - API Documentation

## Overview

RESTful API for the LeadGen AI Voice Agent platform. All endpoints return JSON responses.

**Base URL**: `https://api.leadgenai.com` (production) or `http://localhost:8000` (development)

## Authentication

### API Key Authentication

Include the API key in the `X-API-Key` header:

```bash
curl -H "X-API-Key: your-api-key" https://api.leadgenai.com/api/leads/
```

### Rate Limits

| Tier | Requests/Minute | Requests/Hour |
|------|-----------------|---------------|
| Free | 30 | 500 |
| Starter | 60 | 1,000 |
| Growth | 100 | 2,000 |
| Enterprise | 300 | 10,000 |

Rate limit headers are included in responses:
- `X-RateLimit-Limit`: Maximum requests allowed
- `X-RateLimit-Remaining`: Requests remaining
- `X-RateLimit-Reset`: Unix timestamp when limit resets

---

## Endpoints

### Health & Status

#### GET /health
Check API health status.

**Response**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T00:00:00Z",
  "version": "1.0.0",
  "environment": "production"
}
```

#### GET /health/ready
Readiness check (verifies database and Redis).

#### GET /health/live
Liveness check (returns 200 if process is running).

---

### Leads

#### GET /api/leads/
List all leads with optional filtering.

**Query Parameters**
| Parameter | Type | Description |
|-----------|------|-------------|
| status | string | Filter by status (new, contacted, qualified, etc.) |
| city | string | Filter by city |
| niche | string | Filter by industry niche |
| is_hot_lead | boolean | Filter hot leads only |
| limit | integer | Max results (default: 100) |
| offset | integer | Pagination offset |

**Response**
```json
[
  {
    "id": "lead_abc123",
    "company_name": "ABC Solutions",
    "contact_name": "Rahul Sharma",
    "phone": "+919876543210",
    "email": "rahul@abc.com",
    "city": "Mumbai",
    "status": "new",
    "lead_score": 75,
    "is_hot_lead": true,
    "created_at": "2024-01-01T00:00:00Z"
  }
]
```

#### POST /api/leads/
Create a new lead.

**Request Body**
```json
{
  "company_name": "ABC Solutions",
  "contact_name": "Rahul Sharma",
  "phone": "+919876543210",
  "email": "rahul@abc.com",
  "city": "Mumbai",
  "category": "Real Estate",
  "niche": "real_estate"
}
```

**Response**: `201 Created`
```json
{
  "id": "lead_abc123",
  "status": "new",
  "lead_score": 0,
  "created_at": "2024-01-01T00:00:00Z"
}
```

#### GET /api/leads/{lead_id}
Get a specific lead.

#### PUT /api/leads/{lead_id}
Update a lead.

#### DELETE /api/leads/{lead_id}
Delete a lead.

---

### Campaigns

#### GET /api/campaigns/
List all campaigns.

#### POST /api/campaigns/
Create a new campaign.

**Request Body**
```json
{
  "name": "Mumbai Real Estate Q1",
  "niche": "real_estate",
  "client_name": "ABC Properties",
  "client_service": "Premium Apartments",
  "target_cities": ["Mumbai", "Pune"],
  "target_lead_count": 500,
  "daily_call_limit": 100
}
```

#### POST /api/campaigns/{campaign_id}/start
Start a campaign (begins scraping and calling).

#### POST /api/campaigns/{campaign_id}/pause
Pause a running campaign.

#### POST /api/campaigns/{campaign_id}/resume
Resume a paused campaign.

#### GET /api/campaigns/{campaign_id}/stats
Get campaign statistics.

**Response**
```json
{
  "id": "campaign_123",
  "name": "Mumbai Real Estate Q1",
  "status": "running",
  "leads_scraped": 450,
  "leads_called": 320,
  "leads_qualified": 85,
  "appointments_booked": 12,
  "connection_rate": 0.71,
  "qualification_rate": 0.27,
  "conversion_rate": 0.14
}
```

---

### Platform Management

#### GET /api/platform/stats
Get platform-wide statistics.

**Response**
```json
{
  "total_tenants": 25,
  "active_tenants": 18,
  "trial_tenants": 5,
  "total_calls_made": 15420,
  "total_leads_generated": 8500,
  "is_running": true
}
```

#### POST /api/platform/start
Start the platform automation.

#### POST /api/platform/stop
Stop the platform automation.

#### GET /api/platform/tenants
List all tenants.

#### POST /api/platform/tenants
Create a new tenant.

**Request Body**
```json
{
  "company_name": "XYZ Solar",
  "contact_name": "Amit Kumar",
  "contact_phone": "+919876543210",
  "contact_email": "amit@xyzsolar.com",
  "industry": "solar",
  "target_niches": ["residential_solar", "commercial_solar"],
  "target_cities": ["Mumbai", "Delhi", "Bangalore"]
}
```

#### POST /api/platform/tenants/{tenant_id}/upgrade
Upgrade tenant subscription.

**Request Body**
```json
{
  "tier": "growth"
}
```

---

### Webhooks

#### POST /api/webhooks/twilio/incoming
Twilio call webhook endpoint.

#### POST /api/webhooks/exotel/incoming
Exotel call webhook endpoint.

---

### ML Training

#### GET /api/ml/training/status
Get ML training status.

#### POST /api/ml/training/trigger
Manually trigger model training.

#### GET /api/ml/performance
Get model performance metrics.

---

## Error Responses

All errors follow this format:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": {
      "errors": [
        {
          "field": "phone",
          "message": "Invalid phone number format",
          "type": "value_error"
        }
      ]
    },
    "request_id": "req_abc123"
  }
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| VALIDATION_ERROR | 422 | Invalid request data |
| AUTHENTICATION_ERROR | 401 | Invalid or missing API key |
| AUTHORIZATION_ERROR | 403 | Insufficient permissions |
| NOT_FOUND | 404 | Resource not found |
| RATE_LIMIT_EXCEEDED | 429 | Too many requests |
| QUOTA_EXCEEDED | 429 | Monthly quota exceeded |
| INTERNAL_ERROR | 500 | Server error |

---

## SDKs & Examples

### Python
```python
import httpx

client = httpx.Client(
    base_url="https://api.leadgenai.com",
    headers={"X-API-Key": "your-api-key"}
)

# Create a lead
lead = client.post("/api/leads/", json={
    "company_name": "Test Company",
    "phone": "+919876543210"
}).json()

# List campaigns
campaigns = client.get("/api/campaigns/").json()
```

### JavaScript
```javascript
const response = await fetch('https://api.leadgenai.com/api/leads/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': 'your-api-key'
  },
  body: JSON.stringify({
    company_name: 'Test Company',
    phone: '+919876543210'
  })
});

const lead = await response.json();
```

### cURL
```bash
# Create a lead
curl -X POST https://api.leadgenai.com/api/leads/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"company_name": "Test", "phone": "+919876543210"}'
```

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for API version history.
