# LeadGen AI Voice Agent - API Documentation

## Overview

RESTful API for the LeadGen AI Voice Agent platform. All endpoints return JSON responses.

**Base URL**: `https://leadsgenai.in` (production) or `http://localhost:8000` (development)

## Authentication

### API Key Authentication

Include the API key in the `X-API-Key` header:

```bash
curl -H "X-API-Key: your-api-key" https://leadsgenai.in/api/leads/
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
    base_url="https://leadsgenai.in",
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
const response = await fetch('https://leadsgenai.in/api/leads/', {
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
curl -X POST https://leadsgenai.in/api/leads/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"company_name": "Test", "phone": "+919876543210"}'
```

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for API version history.

---

<!-- AUTO-OPENAPI:START -->

## Endpoint Index — auto-generated from OpenAPI (1005 operations)

> Regenerate: `python scripts/sync_api_docs.py` · Full live spec: `/openapi.json` · Interactive: `/docs`. Edits between the AUTO markers are overwritten.

### (untagged)  (1)

- `GET   ` `/api/status` — Api Status

### AI  (7)

- `POST  ` `/api/ai/ab-test-variant` — Generate Ab Test Variant
- `POST  ` `/api/ai/command` — Nl Command
- `POST  ` `/api/ai/generate-script` — Generate Sales Script
- `POST  ` `/api/ai/generate-transcript` — Generate Call Transcript
- `GET   ` `/api/ai/health` — Ai Health Check
- `POST  ` `/api/ai/qualify-call` — Qualify Call
- `POST  ` `/api/ai/strategy-suggestion` — Get Strategy Suggestion

### Admin  (14)

- `GET   ` `/api/admin/audit-logs` — Get Audit Logs
- `POST  ` `/api/admin/auth/login` — Login
- `POST  ` `/api/admin/auth/logout` — Logout
- `GET   ` `/api/admin/health` — Get System Health
- `GET   ` `/api/admin/me` — Get Current User Info
- `GET   ` `/api/admin/settings` — Get Platform Settings
- `GET   ` `/api/admin/stats` — Get Admin Stats
- `GET   ` `/api/admin/users` — List Users
- `POST  ` `/api/admin/users` — Create User
- `DELETE` `/api/admin/users/{user_id}` — Delete User
- `GET   ` `/api/admin/users/{user_id}` — Get User
- `PATCH ` `/api/admin/users/{user_id}` — Update User
- `DELETE` `/api/admin/users/{user_id}/picture` — Delete Profile Picture
- `POST  ` `/api/admin/users/{user_id}/picture` — Upload Profile Picture

### Admin Customers  (1)

- `POST  ` `/api/admin/customers/onboard` — Onboard Customer

### Admin DB Explorer  (3)

- `GET   ` `/api/admin/db/table/{name}` — Browse rows of one table (read-only, paginated, redacted)
- `GET   ` `/api/admin/db/table/{name}/export.csv` — Export one table to CSV (read-only, capped, redacted)
- `GET   ` `/api/admin/db/tables` — List all DB tables (read-only explorer)

### Admin Dashboard  (15)

- `GET   ` `/api/admin/activity-feed` — Get Activity Feed
- `GET   ` `/api/admin/agents` — Admin Agents
- `POST  ` `/api/admin/clients/bulk-email` — Bulk Email Clients
- `POST  ` `/api/admin/clients/dedupe` — Admin Dedupe Clients
- `POST  ` `/api/admin/clients/{client_id}/delete` — Admin Delete Client
- `GET   ` `/api/admin/clients/{client_id}/timeline` — Get Client Timeline
- `GET   ` `/api/admin/dashboard` — Get Admin Dashboard
- `GET   ` `/api/admin/hourly-activity` — Get Hourly Activity
- `GET   ` `/api/admin/live-stats` — Get Live Stats
- `GET   ` `/api/admin/ops-snapshot` — Get Ops Snapshot
- `POST  ` `/api/admin/ops/celery-trim` — Trim Celery Queue
- `GET   ` `/api/admin/prospects-preview` — Get Prospects Preview
- `GET   ` `/api/admin/revenue-analytics` — Get Revenue Analytics
- `GET   ` `/api/admin/revenue-trend` — Get Revenue Trend
- `GET   ` `/api/admin/sync-health` — Admin Sync Health

### Admin Ops  (20)

- `GET   ` `/api/admin/calls/recent` — Recent call outcomes / qualified summary
- `POST  ` `/api/admin/campaign/launch` — Launch outbound call campaign
- `GET   ` `/api/admin/campaign/status` — Last campaign run status
- `POST  ` `/api/admin/campaign/stop` — Stop the currently running campaign
- `POST  ` `/api/admin/flow/seed-templates` — Apply all Flow Runner starter templates (FLOW_RUNNER=1)
- `GET   ` `/api/admin/leads/ready` — Uncontacted leads ready to call (campaign pre-flight)
- `GET   ` `/api/admin/office` — Admin Office — consolidated 'Sumit ke kaam' pending actions
- `GET   ` `/api/admin/system/summary` — System snapshot for God Mode panel
- `POST  ` `/api/admin/trust/configure-posthog` — Set PostHog API key + host (no restart)
- `POST  ` `/api/admin/trust/configure-sentry` — Set Sentry DSN (lazy web init; worker restart recommended)
- `POST  ` `/api/admin/trust/configure-turnstile` — Set Turnstile keys (no restart)
- `GET   ` `/api/admin/trust/status` — Turnstile + Sentry + PostHog armed status
- `POST  ` `/api/admin/upi/activate` — Activate plan after UPI screenshot verified
- `GET   ` `/api/admin/upi/clients` — Search clients for manual UPI activate
- `POST  ` `/api/admin/upi/configure` — Set platform UPI VPA (data file — no container restart)
- `GET   ` `/api/admin/upi/pending` — Clients waiting for UPI screenshot activation
- `GET   ` `/api/admin/voice/bookings` — Appointments the AI voice agent booked (durable ledger)
- `GET   ` `/api/admin/voice/gemini-keys` — Voice Gemini key pool status (masked)
- `POST  ` `/api/admin/voice/gemini-keys` — Validate + save voice Gemini keys (no restart)
- `GET   ` `/api/admin/voice/latency` — Voice agent per-turn latency rollup (P50/P95) — proves call speed

### AgentCapacity  (2)

- `POST  ` `/api/agents-ext/capacity/risk-score` — Capacity Risk Score
- `GET   ` `/api/agents-ext/capacity/status` — Capacity Status

### AgentGovernance  (6)

- `GET   ` `/api/agents-ext/custom-agents` — Get Custom Agents
- `POST  ` `/api/agents-ext/custom-agents` — Add Custom Agent
- `GET   ` `/api/agents-ext/hooks` — Get Hooks
- `POST  ` `/api/agents-ext/hooks` — Add Hook
- `GET   ` `/api/agents-ext/permissions` — Get Permissions
- `POST  ` `/api/agents-ext/permissions` — Set Permission

### AgentScale  (5)

- `POST  ` `/api/agents-ext/batch` — Batch Run
- `GET   ` `/api/agents-ext/batch/runs` — Batch Runs
- `POST  ` `/api/agents-ext/browser/fetch` — Browser Fetch
- `POST  ` `/api/agents-ext/exec` — Code Exec Run
- `GET   ` `/api/agents-ext/status` — Agent Scale Status

### Agents  (13)

- `POST  ` `/api/agents/coordinate` — Coordinate Agents
- `POST  ` `/api/agents/coordinate-advanced` — Coordinate Advanced Agents
- `POST  ` `/api/agents/coordinate-agentverse` — Coordinate Agentverse Agents
- `POST  ` `/api/agents/coordinate-engineering` — Coordinate Engineering Agents
- `POST  ` `/api/agents/coordinate-hierarchical` — Coordinate Hierarchical Agents
- `POST  ` `/api/agents/council` — Council Agents
- `GET   ` `/api/agents/council/members` — Council Members
- `POST  ` `/api/agents/debate` — Debate Agents
- `POST  ` `/api/agents/fanout` — Fanout Agents
- `GET   ` `/api/agents/memory` — Agents Memory
- `GET   ` `/api/agents/roster` — Agents Roster
- `POST  ` `/api/agents/run` — Run Agent Task
- `GET   ` `/api/agents/status` — Agents Status

### Analytics  (13)

- `GET   ` `/api/analytics/calls` — Get Call Metrics
- `GET   ` `/api/analytics/calls/by-day` — Get Calls By Day
- `GET   ` `/api/analytics/calls/by-outcome` — Get Calls By Outcome
- `GET   ` `/api/analytics/dashboard` — Get Dashboard Stats
- `GET   ` `/api/analytics/hourly-distribution` — Get Hourly Distribution
- `GET   ` `/api/analytics/leads` — Get Lead Metrics
- `GET   ` `/api/analytics/leads/by-city` — Get Leads By City
- `GET   ` `/api/analytics/leads/by-source` — Get Leads By Source
- `GET   ` `/api/analytics/performance/agents` — Get Agent Performance
- `GET   ` `/api/analytics/performance/campaigns` — Get Campaign Performance
- `GET   ` `/api/analytics/reports/daily` — Get Daily Report
- `GET   ` `/api/analytics/reports/monthly` — Get Monthly Report
- `GET   ` `/api/analytics/reports/weekly` — Get Weekly Report

### Billing  (19)

- `GET   ` `/api/billing/balance` — Get Account Balance
- `POST  ` `/api/billing/balance/add` — Add Account Balance
- `POST  ` `/api/billing/checkout` — Create Checkout Session
- `GET   ` `/api/billing/invoices` — Get Invoices
- `GET   ` `/api/billing/invoices/{invoice_id}` — Get Invoice Details
- `GET   ` `/api/billing/payment-methods` — Get Payment Methods
- `GET   ` `/api/billing/plans` — Get Pricing Plans
- `GET   ` `/api/billing/plans/{plan_id}` — Get Plan Details
- `GET   ` `/api/billing/plans/{plan_id}/pricing` — Calculate Plan Pricing
- `POST  ` `/api/billing/portal` — Create Billing Portal
- `GET   ` `/api/billing/subscription` — Get Current Subscription
- `POST  ` `/api/billing/subscription/cancel` — Cancel Subscription
- `POST  ` `/api/billing/subscription/pause` — Pause Subscription
- `POST  ` `/api/billing/subscription/resume` — Resume Subscription
- `POST  ` `/api/billing/subscription/upgrade` — Upgrade Subscription
- `GET   ` `/api/billing/usage` — Get Current Usage
- `GET   ` `/api/billing/usage/history` — Get Usage History
- `POST  ` `/api/billing/webhook` — Unified Payment Webhook
- `POST  ` `/api/billing/webhooks/stripe` — Stripe Webhook

### Booking  (3)

- `POST  ` `/api/booking/book` — Book Slot
- `POST  ` `/api/booking/cancel` — Cancel Booking
- `GET   ` `/api/booking/slots` — Get Slots

### Brain  (3)

- `GET   ` `/api/admin/brain/recent` — Recently-written brain notes (optional folder filter)
- `GET   ` `/api/admin/brain/search` — Search the second brain (word-overlap over vault notes)
- `GET   ` `/api/admin/brain/stats` — Brain health: note counts per folder + freshness

### Brand Assets  (9)

- `GET   ` `/api/brand/card/{slug}` — Card Html
- `GET   ` `/api/brand/card/{slug}.vcf` — Card Vcf
- `POST  ` `/api/brand/frames/compose` — Frames Compose
- `GET   ` `/api/brand/frames/daily` — Frames Daily
- `POST  ` `/api/brand/resize` — Magic Resize Endpoint
- `GET   ` `/api/brand/resize-file/{name}` — Resize File
- `POST  ` `/api/brand/review-post` — Review Post
- `GET   ` `/api/brand/sticker-file/{slug}/{name}` — Sticker File
- `POST  ` `/api/brand/stickers` — Stickers

### Call Recordings  (2)

- `GET   ` `/api/admin/call-recordings` — List call recordings grouped by date
- `GET   ` `/api/admin/call-recordings/{date}/{filename}` — Stream a single WAV recording

### Campaigns  (9)

- `GET   ` `/api/campaigns/` — List Campaigns
- `POST  ` `/api/campaigns/` — Create Campaign
- `GET   ` `/api/campaigns/cities/available` — Get Available Cities
- `GET   ` `/api/campaigns/niches/available` — Get Available Niches
- `GET   ` `/api/campaigns/{campaign_id}` — Get Campaign
- `POST  ` `/api/campaigns/{campaign_id}/pause` — Pause Campaign
- `POST  ` `/api/campaigns/{campaign_id}/resume` — Resume Campaign
- `POST  ` `/api/campaigns/{campaign_id}/start` — Start Campaign
- `GET   ` `/api/campaigns/{campaign_id}/stats` — Get Campaign Stats

### ClientCRM  (10)

- `GET   ` `/api/clientcrm/catalog/{slug}` — Catalog List
- `POST  ` `/api/clientcrm/catalog/{slug}` — Catalog Add
- `DELETE` `/api/clientcrm/catalog/{slug}/{product_id}` — Catalog Delete
- `POST  ` `/api/clientcrm/catalog/{slug}/{product_id}` — Catalog Update
- `GET   ` `/api/clientcrm/customers/{client_id}` — Get Customers
- `POST  ` `/api/clientcrm/customers/{client_id}` — Add Customer
- `POST  ` `/api/clientcrm/customers/{client_id}/import` — Import Customers
- `GET   ` `/api/clientcrm/occasions/today` — Occasions Today
- `GET   ` `/api/clientcrm/wishes/drafts` — Wishes Drafts
- `POST  ` `/api/clientcrm/wishes/run` — Wishes Run

### ClientOps  (21)

- `POST  ` `/api/clientops/approval` — Submit Approval
- `GET   ` `/api/clientops/approvals` — List Approvals
- `POST  ` `/api/clientops/approvals/{approval_id}/decide` — Admin Decide Approval
- `GET   ` `/api/clientops/approve/{token}` — Public Approve
- `GET   ` `/api/clientops/p/{token}` — Proposal Open
- `GET   ` `/api/clientops/proposal-views` — Proposal Views
- `GET   ` `/api/clientops/routing` — Routing Get
- `POST  ` `/api/clientops/routing` — Routing Set
- `POST  ` `/api/clientops/routing/assign` — Routing Assign
- `GET   ` `/api/clientops/routing/assignments` — Routing Assignments
- `GET   ` `/api/clientops/snapshots` — Snapshot List
- `POST  ` `/api/clientops/snapshots/apply-niche` — Snapshot Apply Niche
- `POST  ` `/api/clientops/snapshots/capture` — Snapshot Capture
- `POST  ` `/api/clientops/snapshots/capture-niche` — Snapshot Capture Niche
- `GET   ` `/api/clientops/snapshots/{snapshot_id}` — Snapshot Get
- `POST  ` `/api/clientops/snapshots/{snapshot_id}/apply` — Snapshot Apply
- `GET   ` `/api/clientops/speed-to-lead` — Speed To Lead
- `POST  ` `/api/clientops/track-proposal` — Track Proposal
- `GET   ` `/api/clientops/video-ads` — Video Ads List
- `POST  ` `/api/clientops/video-ads/generate` — Video Ads Generate
- `POST  ` `/api/clientops/video-ads/{approval_id}/request-changes` — Video Ads Request Changes

### Clients  (7)

- `GET   ` `/api/clients` — List All Clients
- `POST  ` `/api/clients` — Create Client
- `GET   ` `/api/clients/{cid}` — Get One Client
- `GET   ` `/api/clients/{cid}/content` — Get Client Content
- `POST  ` `/api/clients/{cid}/content/run` — Run Client Content
- `POST  ` `/api/clients/{cid}/content/{item_id}/status` — Set Content Item Status
- `PATCH ` `/api/clients/{cid}/status` — Set Client Status

### Combo Product  (3)

- `GET   ` `/api/combo/niches` — Combo Niches
- `GET   ` `/api/combo/packages` — Combo Packages
- `GET   ` `/api/combo/plans` — Combo Plans

### ContentAuto  (10)

- `POST  ` `/api/contentauto/month-plan` — Month Plan
- `POST  ` `/api/contentauto/pulse` — Brand Pulse Scan
- `GET   ` `/api/contentauto/pulse/runs` — Brand Pulse Runs
- `POST  ` `/api/contentauto/push/send` — Push Send
- `GET   ` `/api/contentauto/push/status` — Push Status
- `POST  ` `/api/contentauto/push/subscribe` — Push Subscribe
- `GET   ` `/api/contentauto/push/subscribe.js` — Push Subscribe Js
- `POST  ` `/api/contentauto/repurpose` — Repurpose Pack
- `GET   ` `/api/contentauto/team-report` — Team Report
- `POST  ` `/api/contentauto/team-report/run` — Team Report Run

### ContentPlus  (12)

- `POST  ` `/api/contentplus/avatar-video` — Avatar Video
- `GET   ` `/api/contentplus/clip-file/{job}/{name}` — Clip File
- `POST  ` `/api/contentplus/clips` — Start Clips
- `GET   ` `/api/contentplus/clips/{job_id}` — Clips Status
- `POST  ` `/api/contentplus/gif` — Make Gif
- `GET   ` `/api/contentplus/gif-file/{slug}/{name}` — Gif File
- `GET   ` `/api/contentplus/gif-presets` — Gif Presets
- `GET   ` `/api/contentplus/outreach-variants` — Outreach Variant Stats
- `POST  ` `/api/contentplus/outreach-variants/reply` — Outreach Variant Reply
- `POST  ` `/api/contentplus/service-cycle` — Add Service Cycle
- `GET   ` `/api/contentplus/service-due` — Service Due
- `POST  ` `/api/contentplus/service-run` — Service Run

### Conversion Admin  (2)

- `GET   ` `/api/conversion/widget-form/{slug}` — Widget Form Get
- `POST  ` `/api/conversion/widget-form/{slug}` — Widget Form Set

### Conversion Public  (3)

- `POST  ` `/api/public/lead-in` — Lead In
- `GET   ` `/api/public/trial-status` — Get Trial Status
- `POST  ` `/api/public/widget-chat` — Widget Chat

### Creative  (4)

- `POST  ` `/api/creative/bg-remove` — Bg Remove Endpoint
- `POST  ` `/api/creative/jingle` — Create Jingle
- `GET   ` `/api/creative/jingle-file/{name}` — Jingle File
- `GET   ` `/api/creative/status` — Creative Status

### Customer Auth  (5)

- `POST  ` `/api/customer/2fa/confirm` — Confirm
- `POST  ` `/api/customer/2fa/disable` — Disable
- `POST  ` `/api/customer/2fa/enroll` — Enroll
- `GET   ` `/api/customer/2fa/status` — Status
- `POST  ` `/api/customer/2fa/verify` — Verify

### Customer Dashboard  (16)

- `GET   ` `/api/customer/approvals/pending` — Customer Pending Approvals
- `POST  ` `/api/customer/approvals/{approval_id}/decide` — Customer Decide Approval
- `GET   ` `/api/customer/branded-feed` — Customer Branded Feed
- `GET   ` `/api/customer/creatives` — Customer Creatives
- `GET   ` `/api/customer/dashboard` — Get Customer Dashboard
- `POST  ` `/api/customer/dashboard/send-to-crm` — Send Dashboard Leads To Crm
- `GET   ` `/api/customer/gbp/questions` — Customer Gbp Questions
- `POST  ` `/api/customer/gbp/score` — Customer Gbp Score
- `GET   ` `/api/customer/health` — Customer Dashboard Health
- `PATCH ` `/api/customer/leads/{lead_id}` — Patch Lead Status
- `GET   ` `/api/customer/office` — Get Customer Office
- `GET   ` `/api/customer/report` — Customer Monthly Report
- `GET   ` `/api/customer/routing` — Customer Routing Get
- `POST  ` `/api/customer/routing` — Customer Routing Set
- `GET   ` `/api/customer/speed-to-lead` — Customer Speed To Lead
- `GET   ` `/api/customer/team` — Get Customer Team

### Customer Flows  (10)

- `POST  ` `/api/customer/flow` — Cf Save
- `GET   ` `/api/customer/flow-templates` — Cf Templates
- `POST  ` `/api/customer/flow-templates/{tid}/apply` — Cf Apply Template
- `GET   ` `/api/customer/flow/run/{run_id}` — Cf Run Status
- `POST  ` `/api/customer/flow/run/{run_id}/approve` — Cf Approve
- `POST  ` `/api/customer/flow/run/{run_id}/reject` — Cf Reject
- `DELETE` `/api/customer/flow/{flow_id}` — Cf Delete
- `GET   ` `/api/customer/flow/{flow_id}` — Cf Get
- `POST  ` `/api/customer/flow/{flow_id}/run` — Cf Run
- `GET   ` `/api/customer/flows` — Cf List

### Customer Marketing Studio  (88)

- `POST  ` `/api/customer/studio/ads` — Studio Ads
- `GET   ` `/api/customer/studio/aeo-checklist` — Studio Aeo Checklist
- `GET   ` `/api/customer/studio/ai-inbox` — Studio Ai Inbox
- `POST  ` `/api/customer/studio/appointment-assistant` — Studio Appointment Assistant
- `GET   ` `/api/customer/studio/best-time` — Studio Best Time
- `POST  ` `/api/customer/studio/bio-page` — Studio Bio Page
- `POST  ` `/api/customer/studio/blog` — Studio Blog
- `GET   ` `/api/customer/studio/booking-link` — Studio Booking Link
- `GET   ` `/api/customer/studio/brand-palette` — Studio Brand Palette
- `POST  ` `/api/customer/studio/budget-suggest` — Studio Budget Suggest
- `GET   ` `/api/customer/studio/business-card` — Studio Business Card
- `GET   ` `/api/customer/studio/business-description` — Studio Business Description
- `POST  ` `/api/customer/studio/calendar` — Studio Calendar
- `POST  ` `/api/customer/studio/carousel` — Studio Carousel
- `GET   ` `/api/customer/studio/case-study` — Studio Case Study
- `POST  ` `/api/customer/studio/catalog` — Studio Catalog
- `GET   ` `/api/customer/studio/click-to-whatsapp-ad` — Studio Click To Whatsapp Ad
- `GET   ` `/api/customer/studio/community-content` — Studio Community Content
- `POST  ` `/api/customer/studio/competitor` — Studio Competitor
- `GET   ` `/api/customer/studio/complaint-recovery` — Studio Complaint Recovery
- `GET   ` `/api/customer/studio/conversion-tracking` — Studio Conversion Tracking
- `POST  ` `/api/customer/studio/coupon` — Studio Coupon
- `GET   ` `/api/customer/studio/customer-avatar` — Studio Customer Avatar
- `POST  ` `/api/customer/studio/customer-reminder` — Studio Customer Reminder
- `GET   ` `/api/customer/studio/email-signature` — Studio Email Signature
- `GET   ` `/api/customer/studio/evergreen-ideas` — Studio Evergreen Ideas
- `GET   ` `/api/customer/studio/faq-page` — Studio Faq Page
- `POST  ` `/api/customer/studio/faq-reply` — Studio Faq Reply
- `POST  ` `/api/customer/studio/festival-post` — Studio Festival Post
- `POST  ` `/api/customer/studio/followup-sequence` — Studio Followup Sequence
- `POST  ` `/api/customer/studio/gbp-text` — Studio Gbp Text
- `GET   ` `/api/customer/studio/gbp-tips` — Studio Gbp Tips
- `GET   ` `/api/customer/studio/grid-planner` — Studio Grid Planner
- `GET   ` `/api/customer/studio/growth-coach` — Studio Growth Coach
- `POST  ` `/api/customer/studio/hashtags` — Studio Hashtags
- `GET   ` `/api/customer/studio/highlights` — Studio Highlights
- `POST  ` `/api/customer/studio/landing-audit` — Studio Landing Audit
- `POST  ` `/api/customer/studio/lead-magnet` — Studio Lead Magnet
- `GET   ` `/api/customer/studio/listings` — Studio Listings
- `GET   ` `/api/customer/studio/local-event-campaign` — Studio Local Event
- `GET   ` `/api/customer/studio/lost-lead-reason` — Studio Lost Lead Reason
- `GET   ` `/api/customer/studio/loyalty-program` — Studio Loyalty Program
- `POST  ` `/api/customer/studio/meme` — Studio Meme
- `POST  ` `/api/customer/studio/minisite` — Studio Minisite
- `GET   ` `/api/customer/studio/missed-call-reply` — Studio Missed Call Reply
- `POST  ` `/api/customer/studio/month-planner` — Studio Month Planner
- `POST  ` `/api/customer/studio/multilang-post` — Studio Multilang Post
- `POST  ` `/api/customer/studio/negative-review-rescue` — Studio Negative Review Rescue
- `GET   ` `/api/customer/studio/newsletter-outline` — Studio Newsletter Outline
- `GET   ` `/api/customer/studio/next-best-action` — Studio Next Best Action
- `GET   ` `/api/customer/studio/niche-pack` — Studio Niche Pack
- `GET   ` `/api/customer/studio/nps-survey` — Studio Nps Survey
- `POST  ` `/api/customer/studio/objection-handler` — Studio Objection Handler
- `GET   ` `/api/customer/studio/owner-brief` — Studio Owner Brief
- `GET   ` `/api/customer/studio/partnerships` — Studio Partnerships
- `GET   ` `/api/customer/studio/photo-reminder` — Studio Photo Reminder
- `POST  ` `/api/customer/studio/post` — Studio Post
- `POST  ` `/api/customer/studio/poster` — Studio Poster
- `POST  ` `/api/customer/studio/quote-draft` — Studio Quote Draft
- `GET   ` `/api/customer/studio/rank-check-guide` — Studio Rank Check Guide
- `GET   ` `/api/customer/studio/re-engagement` — Studio Re Engagement
- `POST  ` `/api/customer/studio/reel-script` — Studio Reel Script
- `POST  ` `/api/customer/studio/referral` — Studio Referral
- `POST  ` `/api/customer/studio/repurpose` — Studio Repurpose
- `POST  ` `/api/customer/studio/review-kit` — Studio Review Kit
- `POST  ` `/api/customer/studio/review-reply` — Studio Review Reply
- `POST  ` `/api/customer/studio/review-request` — Studio Review Request
- `GET   ` `/api/customer/studio/reviews-widget` — Studio Reviews Widget
- `POST  ` `/api/customer/studio/roi-calculator` — Studio Roi Calculator
- `GET   ` `/api/customer/studio/schema-markup` — Studio Schema Markup
- `GET   ` `/api/customer/studio/seasonal-offers` — Studio Seasonal Offers
- `POST  ` `/api/customer/studio/sentiment` — Studio Sentiment
- `POST  ` `/api/customer/studio/service-area` — Studio Service Area
- `POST  ` `/api/customer/studio/service-menu` — Studio Service Menu
- `GET   ` `/api/customer/studio/sms-pack` — Studio Sms Pack
- `POST  ` `/api/customer/studio/speed-followup` — Studio Speed Followup
- `POST  ` `/api/customer/studio/templates` — Studio Templates
- `POST  ` `/api/customer/studio/testimonial` — Studio Testimonial
- `GET   ` `/api/customer/studio/tools` — Studio Tools
- `GET   ` `/api/customer/studio/trends` — Studio Trends
- `GET   ` `/api/customer/studio/ugc-request` — Studio Ugc Request
- `POST  ` `/api/customer/studio/variations` — Studio Variations
- `POST  ` `/api/customer/studio/voiceover` — Studio Voiceover
- `GET   ` `/api/customer/studio/website-widget` — Studio Website Widget
- `POST  ` `/api/customer/studio/whatsapp` — Studio Whatsapp
- `GET   ` `/api/customer/studio/whatsapp-catalog` — Studio Whatsapp Catalog
- `POST  ` `/api/customer/studio/win-back` — Studio Win Back
- `POST  ` `/api/customer/studio/youtube-metadata` — Studio Youtube Metadata

### Customer Pipeline  (1)

- `GET   ` `/api/customer/pipeline` — Customer Pipeline

### Customer Portal  (11)

- `POST  ` `/api/customer/auth/login` — Customer Login
- `GET   ` `/api/customer/auth/magic-link/config` — Magic Link Config
- `POST  ` `/api/customer/auth/magic-link/request` — Magic Link Request
- `POST  ` `/api/customer/auth/magic-link/verify` — Magic Link Verify
- `GET   ` `/api/customer/auth/me` — Me
- `GET   ` `/api/customer/auth/portal/content` — Portal Content
- `GET   ` `/api/customer/auth/portal/dashboard` — Portal Dashboard
- `GET   ` `/api/customer/auth/portal/invoice-html` — Portal Invoice Html
- `GET   ` `/api/customer/auth/portal/invoices` — Portal Invoices
- `POST  ` `/api/customer/auth/set-password` — Set Password
- `POST  ` `/api/customer/auth/signup` — Customer Signup

### Customer Studio Media  (9)

- `POST  ` `/api/customer/studio/img-bgremove` — Studio Img Bgremove
- `POST  ` `/api/customer/studio/img-gif` — Studio Img Gif
- `POST  ` `/api/customer/studio/img-resize` — Studio Img Resize
- `POST  ` `/api/customer/studio/img-sticker` — Studio Img Sticker
- `GET   ` `/api/customer/studio/media-tools` — Studio Media Tools
- `GET   ` `/api/customer/studio/media/{media_id}` — Studio Serve Media
- `POST  ` `/api/customer/studio/upload` — Studio Upload
- `POST  ` `/api/customer/studio/video-reel` — Studio Video Reel
- `GET   ` `/api/customer/studio/video-status/{job_id}` — Studio Video Status

### Customer Webhooks  (10)

- `GET   ` `/api/customer/webhooks` — List
- `POST  ` `/api/customer/webhooks` — Create
- `GET   ` `/api/customer/webhooks/_meta` — Meta
- `GET   ` `/api/customer/webhooks/_verifier-examples` — Verifier Examples
- `DELETE` `/api/customer/webhooks/{webhook_id}` — Delete
- `PATCH ` `/api/customer/webhooks/{webhook_id}` — Update
- `GET   ` `/api/customer/webhooks/{webhook_id}/deliveries` — Deliveries
- `POST  ` `/api/customer/webhooks/{webhook_id}/deliveries/{delivery_id}/retry` — Retry Delivery
- `POST  ` `/api/customer/webhooks/{webhook_id}/rotate-secret` — Rotate Secret
- `POST  ` `/api/customer/webhooks/{webhook_id}/test` — Test Fire

### Dashboard Assessment  (6)

- `GET   ` `/api/assessment/diff` — Get Diff
- `GET   ` `/api/assessment/history` — List History
- `GET   ` `/api/assessment/latest` — Get Latest
- `GET   ` `/api/assessment/report` — Get Report Markdown
- `POST  ` `/api/assessment/run` — Run Assessment
- `GET   ` `/api/assessment/scores` — Get Scores

### Data Intelligence  (14)

- `GET   ` `/api/data/api-keys` — List Api Keys
- `POST  ` `/api/data/api-keys` — Create Api Key
- `DELETE` `/api/data/api-keys/{key_id}` — Revoke Api Key
- `GET   ` `/api/data/cities` — Get Available Cities
- `GET   ` `/api/data/companies` — Search Companies
- `POST  ` `/api/data/companies/export` — Export Companies
- `GET   ` `/api/data/companies/{company_id}` — Get Company Details
- `GET   ` `/api/data/credits` — Get Credit Balance
- `GET   ` `/api/data/credits/pricing` — Get Credit Pricing
- `GET   ` `/api/data/niches` — Get Available Niches
- `POST  ` `/api/data/niches` — Create Custom Niche
- `DELETE` `/api/data/niches/{niche_key}` — Delete Custom Niche
- `POST  ` `/api/data/reports` — Generate Report
- `GET   ` `/api/data/usage` — Get Usage Stats

### Email Tracking  (3)

- `GET   ` `/api/admin/email-tracking/stats` — Email Tracking Stats
- `GET   ` `/t/c/{token}` — Track Click
- `GET   ` `/t/o/{token}` — Track Open

### EngAgents  (6)

- `POST  ` `/api/agents-ext/checkpoint` — Checkpoint Create
- `GET   ` `/api/agents-ext/checkpoints` — Checkpoints List
- `POST  ` `/api/agents-ext/code-review` — Code Review
- `GET   ` `/api/agents-ext/recall` — Recall Search
- `POST  ` `/api/agents-ext/recall` — Recall Record
- `POST  ` `/api/agents-ext/rollback/{ckpt_id}` — Checkpoint Rollback

### Engage  (8)

- `POST  ` `/api/engage/alerts/test` — Alerts Test
- `POST  ` `/api/engage/links` — Create Link
- `GET   ` `/api/engage/links/stats` — Link Stats
- `GET   ` `/api/engage/reviews-snippet` — Reviews Snippet
- `GET   ` `/api/engage/reviews-widget.js/{slug}` — Reviews Widget Js
- `GET   ` `/api/engage/reviews-widget/{slug}` — Reviews Widget Page
- `POST  ` `/api/engage/upi-qr` — Upi Qr Pack
- `GET   ` `/r/{code}` — Short Redirect

### Events  (2)

- `POST  ` `/api/events/publish` — Publish Event
- `GET   ` `/api/events/stream` — Events Stream

### Frontend  (55)

- `GET   ` `/app/admin` — Admin Dashboard Page
- `GET   ` `/app/admin-login` — Admin Login Page
- `GET   ` `/app/admin/db` — Admin Db Explorer Page
- `GET   ` `/app/agent-tools` — Agent Tools Page
- `GET   ` `/app/agents` — Agents Page
- `GET   ` `/app/analytics` — Analytics Page
- `GET   ` `/app/assistant` — Assistant Page
- `GET   ` `/app/automation` — Automation Page
- `GET   ` `/app/battlecard` — Battlecard Page
- `GET   ` `/app/brain` — Brain Page
- `GET   ` `/app/calendar` — Calendar Page
- `GET   ` `/app/clients` — Clients Page
- `GET   ` `/app/command-center` — Command Center Page
- `GET   ` `/app/conversations` — Conversations Page
- `GET   ` `/app/customer` — Customer Dashboard Page
- `GET   ` `/app/customer/flows` — Customer Flows Page
- `GET   ` `/app/customer/marketing` — Customer Marketing Page
- `GET   ` `/app/customer/pipeline` — Customer Pipeline Page
- `GET   ` `/app/customer/voice` — Customer Voice Page
- `GET   ` `/app/dashboards` — Dashboards Page
- `GET   ` `/app/deals` — Deals Page
- `GET   ` `/app/dialer` — Dialer Page
- `GET   ` `/app/explorer` — Architecture Explorer Page
- `GET   ` `/app/growth-tools` — Growth Tools Page
- `GET   ` `/app/impersonate` — Impersonate Page
- `GET   ` `/app/inbox` — Inbox Page
- `GET   ` `/app/journeys` — Journeys Page
- `GET   ` `/app/login` — Customer Login Page
- `GET   ` `/app/marketing` — Marketing Page
- `GET   ` `/app/minisite-builder` — Minisite Builder Page
- `GET   ` `/app/onboard` — Onboard Page
- `GET   ` `/app/ops` — Ops Page
- `GET   ` `/app/outreach` — Outreach Page
- `GET   ` `/app/segments` — Segments Page
- `GET   ` `/app/studio` — Studio Page
- `GET   ` `/app/team` — Team Dashboard Page
- `GET   ` `/app/team-access` — Team Access Page
- `GET   ` `/app/test-call` — Web Call Test Page
- `GET   ` `/app/voice-keys` — Voice Keys Page
- `GET   ` `/app/whatsapp` — Whatsapp Page
- `GET   ` `/audit` — Public Audit Page
- `GET   ` `/compare` — Public Compare Page
- `GET   ` `/demo` — Public Demo Page
- `GET   ` `/geo-check` — Public Geo Check Page
- `GET   ` `/manifest.json` — Pwa Manifest
- `GET   ` `/pricing` — Pricing Page
- `GET   ` `/privacy` — Privacy Page
- `GET   ` `/refund` — Refund Page
- `GET   ` `/reseller` — Reseller Page
- `GET   ` `/site-audit` — Public Site Audit Page
- `GET   ` `/start` — Start Alias Page
- `GET   ` `/status` — Status Page
- `GET   ` `/sw.js` — Pwa Service Worker
- `GET   ` `/terms` — Terms Page
- `GET   ` `/voice-agent` — Voice Agent Product Page

### Growth  (203)

- `POST  ` `/api/growth/affiliate/register` — Affiliate Register
- `GET   ` `/api/growth/affiliate/stats` — Affiliate Stats
- `GET   ` `/api/growth/approvals/drafts` — Approvals Drafts
- `POST  ` `/api/growth/approvals/drafts/{source}/{item_id}/decide` — Approvals Draft Decide
- `GET   ` `/api/growth/attribution/summary` — Attribution Summary
- `POST  ` `/api/growth/bookings/no-show` — Bookings No Show
- `POST  ` `/api/growth/bookings/remind-run` — Bookings Remind Run
- `GET   ` `/api/growth/bookings/upcoming` — Bookings Upcoming
- `GET   ` `/api/growth/cadence` — Cadence Status
- `POST  ` `/api/growth/cadence/enroll` — Cadence Enroll
- `POST  ` `/api/growth/cadence/run` — Cadence Run
- `POST  ` `/api/growth/campaign/optimize` — Campaign Optimize Run
- `GET   ` `/api/growth/campaign/optimize/proposals` — Campaign Optimize Proposals
- `POST  ` `/api/growth/campaign/optimize/proposals/{proposal_id}/approve` — Campaign Optimize Approve
- `GET   ` `/api/growth/campaign/optimize/runs` — Campaign Optimize Runs
- `GET   ` `/api/growth/campaign/optimize/status` — Campaign Optimize Status
- `GET   ` `/api/growth/campaign/variants` — Campaign Variants List
- `POST  ` `/api/growth/campaign/variants/promote` — Campaign Variants Promote
- `GET   ` `/api/growth/campaign/variants/summary` — Campaign Variants Summary
- `GET   ` `/api/growth/client-data/summary` — Client Data Summary
- `GET   ` `/api/growth/client-keys` — Client Keys List
- `POST  ` `/api/growth/client-keys` — Client Key Issue
- `DELETE` `/api/growth/client-keys/{hash_prefix}` — Client Key Revoke
- `POST  ` `/api/growth/community/batch` — Community Batch
- `POST  ` `/api/growth/community/draft` — Community Draft
- `POST  ` `/api/growth/content/carousel` — Content Carousel
- `POST  ` `/api/growth/content/feedback` — Content Feedback Record
- `GET   ` `/api/growth/content/feedback/stats` — Content Feedback Stats
- `POST  ` `/api/growth/content/meme` — Content Meme
- `POST  ` `/api/growth/content/multilang` — Content Multilang
- `POST  ` `/api/growth/content/personalize` — Content Personalize
- `POST  ` `/api/growth/content/reel-video` — Content Reel Video
- `GET   ` `/api/growth/content/templates` — Content Templates
- `GET   ` `/api/growth/content/trends` — Content Trends
- `POST  ` `/api/growth/crm/config` — Crm Config
- `GET   ` `/api/growth/crm/log` — Crm Log
- `POST  ` `/api/growth/crm/pull` — Crm Pull Status
- `GET   ` `/api/growth/crm/status` — Crm Status
- `POST  ` `/api/growth/crm/sync-lead` — Crm Sync Lead
- `POST  ` `/api/growth/crm/test` — Crm Test
- `GET   ` `/api/growth/deliverability` — Deliverability Check
- `GET   ` `/api/growth/deliverability/summary` — Deliverability Summary
- `GET   ` `/api/growth/enrich/opencorporates` — Enrich Opencorporates
- `GET   ` `/api/growth/experiments` — Experiments Overview
- `POST  ` `/api/growth/experiments/outcome` — Experiments Outcome
- `POST  ` `/api/growth/experiments/run` — Experiments Run
- `GET   ` `/api/growth/fde/agents` — Fde Agents
- `POST  ` `/api/growth/fde/deploy` — Fde Deploy
- `POST  ` `/api/growth/flow` — Flow Save
- `GET   ` `/api/growth/flow-templates` — Flow Templates List
- `POST  ` `/api/growth/flow-templates/{tid}/apply` — Flow Template Apply
- `DELETE` `/api/growth/flow/{flow_id}` — Flow Delete
- `GET   ` `/api/growth/flow/{flow_id}` — Flow Get
- `GET   ` `/api/growth/flows` — Flows List
- `POST  ` `/api/growth/harvest/enrich` — Harvest Enrich
- `GET   ` `/api/growth/harvest/gtm-coverage` — Harvest Gtm Coverage
- `POST  ` `/api/growth/harvest/indiamart-run` — Harvest Indiamart Run
- `POST  ` `/api/growth/harvest/run` — Harvest Run
- `GET   ` `/api/growth/harvest/runs` — Harvest Runs
- `GET   ` `/api/growth/harvest/sources` — Harvest Sources
- `POST  ` `/api/growth/harvest/udyam-run` — Harvest Udyam Run
- `POST  ` `/api/growth/icp/generate` — Icp Generate
- `POST  ` `/api/growth/identity/backfill` — Identity Backfill
- `GET   ` `/api/growth/identity/duplicates` — Identity Duplicates
- `POST  ` `/api/growth/identity/merge` — Identity Merge
- `GET   ` `/api/growth/inbox` — Action Inbox
- `GET   ` `/api/growth/infra/automation-health` — Infra Automation Health
- `DELETE` `/api/growth/infra/dlq` — Infra Dlq Purge
- `GET   ` `/api/growth/infra/dlq` — Infra Dlq
- `POST  ` `/api/growth/infra/dlq/retry` — Infra Dlq Retry
- `POST  ` `/api/growth/infra/dlq/sweep` — Infra Dlq Sweep
- `GET   ` `/api/growth/infra/explorer-drift` — Infra Explorer Drift
- `GET   ` `/api/growth/infra/feature-flags` — List Feature Flags
- `POST  ` `/api/growth/infra/feature-flags` — Upsert Feature Flag
- `DELETE` `/api/growth/infra/feature-flags/{key}` — Delete Feature Flag
- `GET   ` `/api/growth/infra/feature-flags/{key}` — Get Feature Flag
- `GET   ` `/api/growth/infra/feature-flags/{key}/check` — Check Feature Flag
- `GET   ` `/api/growth/infra/flags` — Infra Flags
- `GET   ` `/api/growth/infra/hermes` — Infra Hermes
- `GET   ` `/api/growth/infra/hermes/scans` — Infra Hermes Scans
- `GET   ` `/api/growth/infra/integrations` — Infra Integrations
- `GET   ` `/api/growth/infra/judge-calibration` — Infra Judge Calibration
- `GET   ` `/api/growth/infra/llm` — Infra Llm Metrics
- `POST  ` `/api/growth/infra/rag-retrieval-ab` — Infra Rag Retrieval Ab
- `GET   ` `/api/growth/infra/telephony-readiness` — Infra Telephony Readiness
- `GET   ` `/api/growth/interactions/timeline` — Interactions Timeline
- `GET   ` `/api/growth/leads/hot` — Hot Leads
- `POST  ` `/api/growth/leads/rescore` — Rescore Leads
- `POST  ` `/api/growth/leads/score` — Score One
- `POST  ` `/api/growth/linkedin/draft` — Linkedin Draft
- `GET   ` `/api/growth/loyalty` — Loyalty Stats
- `POST  ` `/api/growth/loyalty/campaign` — Loyalty Create
- `GET   ` `/api/growth/loyalty/check/{code}` — Loyalty Check
- `POST  ` `/api/growth/loyalty/redeem` — Loyalty Redeem
- `POST  ` `/api/growth/missed-call` — Missed Call
- `GET   ` `/api/growth/niche/pack/{niche_key}` — Niche Pack One
- `POST  ` `/api/growth/niche/packs` — Niche Packs
- `POST  ` `/api/growth/niche/scrape` — Niche Scrape
- `GET   ` `/api/growth/niches` — List Niches
- `POST  ` `/api/growth/notify/test` — Notify Test
- `GET   ` `/api/growth/nps/request-drafts` — Nps Request Drafts
- `GET   ` `/api/growth/nps/stats` — Nps Stats
- `POST  ` `/api/growth/nps/submit` — Nps Submit
- `GET   ` `/api/growth/objections/recent` — Objections Recent
- `POST  ` `/api/growth/objections/scan` — Objections Scan
- `GET   ` `/api/growth/optimizer/analysis` — Optimizer Analysis
- `POST  ` `/api/growth/optimizer/run` — Optimizer Run
- `GET   ` `/api/growth/optimizer/runs` — Optimizer Runs
- `GET   ` `/api/growth/outreach/warmup` — Outreach Warmup Status
- `POST  ` `/api/growth/outreach/warmup/bounce` — Outreach Warmup Bounce
- `POST  ` `/api/growth/outreach/warmup/resume` — Outreach Warmup Resume
- `GET   ` `/api/growth/overview/today` — Overview Today
- `POST  ` `/api/growth/partnership/batch` — Partnership Batch
- `POST  ` `/api/growth/partnership/draft` — Partnership Draft
- `GET   ` `/api/growth/partnership/types` — Partnership Types
- `GET   ` `/api/growth/process/definitions` — Process Definitions
- `GET   ` `/api/growth/process/run/{run_id}` — Process Run Detail
- `POST  ` `/api/growth/process/run/{run_id}/approve` — Process Approve
- `POST  ` `/api/growth/process/run/{run_id}/reject` — Process Reject
- `GET   ` `/api/growth/process/runs` — Process Runs
- `POST  ` `/api/growth/process/start` — Process Start
- `POST  ` `/api/growth/prospects/find-email` — Prospects Find Email
- `POST  ` `/api/growth/prospects/find-email-batch` — Prospects Find Email Batch
- `POST  ` `/api/growth/prospects/import` — Prospects Import
- `GET   ` `/api/growth/prospects/lists` — Prospects Lists
- `POST  ` `/api/growth/prospects/lists` — Prospects Create List
- `POST  ` `/api/growth/prospects/lists/{list_id}/enroll-cadence` — Prospects List Enroll
- `GET   ` `/api/growth/prospects/search` — Prospects Search
- `POST  ` `/api/growth/reply/feedback` — Reply Feedback
- `GET   ` `/api/growth/reply/feedback/stats` — Reply Feedback Stats
- `GET   ` `/api/growth/research/search` — Research Search
- `POST  ` `/api/growth/revenue/client-report` — Client Report Build
- `POST  ` `/api/growth/revenue/client-reports/run` — Client Reports Run
- `POST  ` `/api/growth/revenue/digest/run` — Revenue Digest Run
- `GET   ` `/api/growth/revenue/dunning` — Dunning Overview
- `POST  ` `/api/growth/revenue/dunning/case` — Dunning Open Case
- `POST  ` `/api/growth/revenue/dunning/run` — Dunning Run
- `GET   ` `/api/growth/revenue/health/clients` — Client Health Report
- `POST  ` `/api/growth/revenue/health/run` — Client Health Run
- `POST  ` `/api/growth/revenue/invoice` — Revenue Invoice Create
- `GET   ` `/api/growth/revenue/invoice-html` — Revenue Invoice Html
- `GET   ` `/api/growth/revenue/invoices` — Revenue Invoices
- `GET   ` `/api/growth/revenue/invoices.csv` — Revenue Invoices Csv
- `GET   ` `/api/growth/revenue/lifecycle` — Lifecycle Overview
- `POST  ` `/api/growth/revenue/lifecycle/enroll` — Lifecycle Enroll
- `POST  ` `/api/growth/revenue/lifecycle/run` — Lifecycle Run
- `GET   ` `/api/growth/revenue/summary` — Revenue Summary
- `POST  ` `/api/growth/revenue/topup-link` — Revenue Topup Link
- `GET   ` `/api/growth/revenue/topup-packs` — Revenue Topup Packs
- `GET   ` `/api/growth/revenue/usage-alerts` — Usage Alerts Recent
- `POST  ` `/api/growth/revenue/usage-alerts/run` — Usage Alerts Run
- `POST  ` `/api/growth/review/request` — Review Request
- `GET   ` `/api/growth/review/requests` — Review Requests
- `GET   ` `/api/growth/reviews/drafts` — Reviews Drafts
- `POST  ` `/api/growth/reviews/monitor-run` — Reviews Monitor Run
- `POST  ` `/api/growth/sales/assistant` — Sales Assistant Reply
- `POST  ` `/api/growth/sales/deal` — Sales Deal
- `POST  ` `/api/growth/sales/deal/{deal_id}/stage` — Sales Stage
- `GET   ` `/api/growth/sales/deals` — Sales Deals
- `POST  ` `/api/growth/sales/proposal` — Sales Proposal
- `GET   ` `/api/growth/sales/prospect-analyses` — Sales Prospect Analyses
- `POST  ` `/api/growth/sales/prospect-analysis` — Sales Prospect Analysis
- `POST  ` `/api/growth/sales/run` — Sales Run
- `POST  ` `/api/growth/sales/team-run` — Sales Team Run
- `GET   ` `/api/growth/selfimprove/actions` — Selfimprove Actions
- `PATCH ` `/api/growth/selfimprove/approval/{task_id}/approve` — Approve Selfimprove Task
- `PATCH ` `/api/growth/selfimprove/approval/{task_id}/reject` — Reject Selfimprove Task
- `GET   ` `/api/growth/selfimprove/approvals-pending` — Selfimprove Approvals
- `GET   ` `/api/growth/selfimprove/cost-status` — Selfimprove Cost
- `POST  ` `/api/growth/selfimprove/run` — Selfimprove Run
- `GET   ` `/api/growth/selfimprove/status` — Selfimprove Status
- `POST  ` `/api/growth/selfimprove/task` — Selfimprove Add Task
- `POST  ` `/api/growth/seo/batch` — Seo Batch
- `POST  ` `/api/growth/seo/indexnow` — Seo Indexnow
- `POST  ` `/api/growth/seo/page` — Seo Page
- `POST  ` `/api/growth/skills/lesson` — Skills Add Lesson
- `GET   ` `/api/growth/skills/library` — Skills Library
- `GET   ` `/api/growth/skills/pack` — Skills Pack List
- `POST  ` `/api/growth/skills/pack/author` — Skills Pack Author
- `POST  ` `/api/growth/skills/pack/ingest` — Skills Pack Ingest
- `GET   ` `/api/growth/skills/pack/{name}` — Skills Pack Get
- `POST  ` `/api/growth/sms/send` — Sms Send
- `POST  ` `/api/growth/social/batch` — Social Batch
- `GET   ` `/api/growth/social/channels` — Social Channels List
- `POST  ` `/api/growth/social/draft` — Social Draft
- `GET   ` `/api/growth/speed-to-lead/breakdown` — Speed To Lead Breakdown
- `GET   ` `/api/growth/speed-to-lead/summary` — Speed To Lead Summary
- `POST  ` `/api/growth/tools/google-score` — Tool Google Score
- `POST  ` `/api/growth/tools/lead-cost` — Tool Lead Cost
- `POST  ` `/api/growth/tools/missed-call-revenue` — Tool Missed Call
- `POST  ` `/api/growth/tools/website-audit` — Website Audit Public
- `GET   ` `/api/growth/upgrader/code-search` — Upgrader Code Search
- `POST  ` `/api/growth/upgrader/diagnostics` — Upgrader Diagnostics
- `GET   ` `/api/growth/upgrader/patches` — Upgrader Patches
- `POST  ` `/api/growth/upgrader/patches/{patch_id}/status` — Upgrader Patch Status
- `POST  ` `/api/growth/upgrader/scan` — Upgrader Scan
- `GET   ` `/api/growth/voice/qualifications` — Voice Qualifications List
- `POST  ` `/api/growth/voice/qualifications/ask` — Voice Qualifications Ask
- `GET   ` `/api/growth/weather-angle` — Weather Angle Ep
- `GET   ` `/api/growth/webhooks` — Webhooks List
- `POST  ` `/api/growth/webhooks/register` — Webhooks Register
- `DELETE` `/api/growth/webhooks/{webhook_id}` — Webhooks Remove
- `POST  ` `/api/growth/whatsapp/flow/send` — Whatsapp Flow Send

### Health  (7)

- `GET   ` `/api/v1/status` — Api Status
- `GET   ` `/health` — Health Check
- `GET   ` `/health/deep` — Deep Health Check
- `GET   ` `/health/live` — Liveness Check
- `GET   ` `/health/platform` — Platform Detailed Health
- `GET   ` `/health/ready` — Readiness Check
- `GET   ` `/metrics` — Prometheus Metrics

### Impersonation  (4)

- `GET   ` `/api/impersonate/config` — Impersonation Config
- `POST  ` `/api/impersonate/start` — Impersonation Start
- `POST  ` `/api/impersonate/stop` — Impersonation Stop
- `GET   ` `/api/impersonate/targets` — Impersonation Targets

### Infrastructure  (18)

- `GET   ` `/api/activation/readiness` — Activation Readiness
- `GET   ` `/api/activation/summary` — Activation Summary Public
- `GET   ` `/api/activation/wizard` — Activation Wizard
- `GET   ` `/api/admin/system-health-detail` — System Health Detail
- `GET   ` `/api/agent-memory/inspect` — Inspect
- `POST  ` `/api/agent-memory/purge` — Purge
- `GET   ` `/api/agent-memory/stats` — Stats
- `GET   ` `/api/engineer-agents/all` — Run All
- `GET   ` `/api/engineer-agents/{role}` — Run One
- `GET   ` `/api/engineer-agents/{role}/history` — History
- `POST  ` `/api/engineer-agents/{role}/run` — Run Now
- `GET   ` `/api/eval-gate/recent` — Eval Gate Recent
- `POST  ` `/api/eval-gate/reset` — Reset
- `GET   ` `/api/eval-gate/summary` — Eval Gate Summary
- `GET   ` `/api/h4/dr-status` — Dr Status
- `GET   ` `/api/h4/litellm-health` — Litellm Health
- `GET   ` `/api/h4/litellm-spend` — Litellm Spend
- `GET   ` `/api/h4/margin-alerts` — Margin Alerts

### Journeys  (7)

- `GET   ` `/api/journeys` — Get Journeys
- `POST  ` `/api/journeys` — Create Journey
- `POST  ` `/api/journeys/emit` — Emit Event
- `GET   ` `/api/journeys/runs` — List Runs
- `POST  ` `/api/journeys/seed` — Seed Defaults
- `DELETE` `/api/journeys/{jid}` — Delete Journey
- `POST  ` `/api/journeys/{jid}/toggle` — Toggle Journey

### Leads  (8)

- `GET   ` `/api/leads/` — List Leads
- `POST  ` `/api/leads/` — Create Lead
- `POST  ` `/api/leads/scrape` — Scrape Leads
- `GET   ` `/api/leads/scrape/{task_id}` — Get Scrape Status
- `GET   ` `/api/leads/stats/summary` — Get Leads Summary
- `DELETE` `/api/leads/{lead_id}` — Delete Lead
- `GET   ` `/api/leads/{lead_id}` — Get Lead
- `PUT   ` `/api/leads/{lead_id}` — Update Lead

### Lifecycle  (14)

- `GET   ` `/api/lifecycle/email-signature` — Email Signature
- `POST  ` `/api/lifecycle/lead-magnet` — Lead Magnet Generate
- `GET   ` `/api/lifecycle/lead-magnet-file/{name}` — Lead Magnet File
- `GET   ` `/api/lifecycle/newsletter/preview` — Newsletter Preview
- `GET   ` `/api/lifecycle/newsletter/rss-digest` — Newsletter Rss Digest
- `POST  ` `/api/lifecycle/newsletter/run` — Newsletter Run
- `GET   ` `/api/lifecycle/newsletter/subscribers` — Newsletter Subscribers List
- `POST  ` `/api/lifecycle/newsletter/subscribers` — Newsletter Subscribers Import
- `GET   ` `/api/lifecycle/newsletter/unsub/{token}` — Newsletter Unsub
- `GET   ` `/api/lifecycle/outreach-unsub/{token}` — Outreach Unsub Get
- `POST  ` `/api/lifecycle/outreach-unsub/{token}` — Outreach Unsub Post
- `GET   ` `/api/lifecycle/winback/drafts` — Winback Drafts
- `GET   ` `/api/lifecycle/winback/inactive` — Winback Inactive
- `POST  ` `/api/lifecycle/winback/run` — Winback Run

### Local-SEO  (7)

- `POST  ` `/api/localseo/geo-check` — Geo Check
- `GET   ` `/api/localseo/geo-checks` — Geo Checks
- `POST  ` `/api/localseo/grid-rank` — Grid Rank Check
- `GET   ` `/api/localseo/grid-runs` — Grid Runs
- `GET   ` `/api/localseo/listings-checklist` — Listings Checklist
- `GET   ` `/api/localseo/listings-status` — Listings Status Get
- `POST  ` `/api/localseo/listings-status` — Listings Status Save

### MCP Product  (12)

- `GET   ` `/.well-known/agent.json` — A2A Agent Card
- `GET   ` `/api/admin/mcp-keys` — Admin List
- `POST  ` `/api/admin/mcp-keys` — Admin Issue
- `DELETE` `/api/admin/mcp-keys/{key_id}` — Admin Revoke
- `PATCH ` `/api/admin/mcp-keys/{key_id}` — Admin Toggle
- `GET   ` `/api/admin/mcp/audit` — Admin Mcp Audit
- `GET   ` `/api/admin/mcp/health` — Admin Mcp Health
- `POST  ` `/api/admin/mcp/health/run` — Admin Mcp Health Run
- `GET   ` `/api/mcp-product/v1/discover` — Discover
- `GET   ` `/api/mcp-product/v1/niches` — Niches
- `POST  ` `/api/mcp-product/v1/qualifier` — Qualifier Run
- `POST  ` `/api/mcp-product/v1/score-lead` — Score Lead

### ML Training  (31)

- `POST  ` `/api/ml/ab-test` — Create Ab Test
- `GET   ` `/api/ml/ab-test/{test_id}` — Get Ab Test Results
- `GET   ` `/api/ml/best-responses` — Get Best Responses
- `POST  ` `/api/ml/brain/feedback` — Record Brain Feedback
- `GET   ` `/api/ml/brain/health` — Get Brain Health
- `GET   ` `/api/ml/brain/metrics` — Get Brain Metrics
- `GET   ` `/api/ml/brain/status` — Get Brain Training Status
- `POST  ` `/api/ml/brain/train` — Train Brains
- `POST  ` `/api/ml/brain/train/now` — Train Brains Immediate
- `GET   ` `/api/ml/data-stats` — Get Data Statistics
- `POST  ` `/api/ml/feedback` — Submit Call Feedback
- `GET   ` `/api/ml/insights` — Get Ml Insights
- `GET   ` `/api/ml/metrics` — Get Ml Metrics
- `GET   ` `/api/ml/objection-handlers` — Get Objection Handlers
- `POST  ` `/api/ml/scheduler/start` — Start Scheduler
- `POST  ` `/api/ml/scheduler/stop` — Stop Scheduler
- `GET   ` `/api/ml/status` — Get Ml Status
- `POST  ` `/api/ml/train` — Trigger Training
- `GET   ` `/api/ml/training-history` — Get Training History
- `GET   ` `/api/ml/unified/status` — Get Unified Training Status
- `GET   ` `/api/ml/unified/sub-agents` — Get Sub Agents Status
- `POST  ` `/api/ml/unified/sub-agents/train` — Train All Sub Agents
- `POST  ` `/api/ml/unified/train` — Unified Train All
- `POST  ` `/api/ml/unified/train/now` — Unified Train All Now
- `POST  ` `/api/ml/vertex/behavior` — Record Vertex Behavior
- `POST  ` `/api/ml/vertex/continuous/start` — Start Vertex Continuous
- `POST  ` `/api/ml/vertex/continuous/stop` — Stop Vertex Continuous
- `GET   ` `/api/ml/vertex/production-readiness` — Get Production Readiness
- `GET   ` `/api/ml/vertex/status` — Get Vertex Training Status
- `POST  ` `/api/ml/vertex/train` — Trigger Vertex Training
- `POST  ` `/api/ml/vertex/train/now` — Vertex Train Now

### Marketing  (53)

- `POST  ` `/api/marketing/ads-pack` — Generate Ads Pack
- `POST  ` `/api/marketing/ai-image` — Generate Ai Image
- `GET   ` `/api/marketing/ai-image-proxy` — Ai Image Proxy
- `GET   ` `/api/marketing/ai-img-file/{name}` — Ai Img File
- `GET   ` `/api/marketing/audit/questions` — Get Audit Questions
- `POST  ` `/api/marketing/audit/score` — Score Gbp Audit
- `GET   ` `/api/marketing/blog` — List Blog Articles
- `POST  ` `/api/marketing/blog/run` — Run Blog Publish
- `GET   ` `/api/marketing/blog/{slug}` — Get Blog Article
- `POST  ` `/api/marketing/brand-logo` — Marketing Brand Logo
- `GET   ` `/api/marketing/brand/{client_id}` — Get Client Brand
- `POST  ` `/api/marketing/brand/{client_id}` — Save Client Brand
- `POST  ` `/api/marketing/calendar` — Generate Content Calendar
- `POST  ` `/api/marketing/catalog` — Generate Catalog
- `POST  ` `/api/marketing/chatbot` — Marketing Chatbot
- `POST  ` `/api/marketing/competitor` — Generate Competitor Tips
- `POST  ` `/api/marketing/complete-post` — Generate Complete Post
- `POST  ` `/api/marketing/content-pack` — Generate Client Content Pack
- `GET   ` `/api/marketing/crm/{client_id}/customers` — List Crm Customers
- `POST  ` `/api/marketing/crm/{client_id}/customers` — Add Crm Customers
- `GET   ` `/api/marketing/crm/{client_id}/wishes` — Get Todays Wishes
- `POST  ` `/api/marketing/drip` — Generate Drip Sequence
- `GET   ` `/api/marketing/embed-snippet` — Embed Snippet
- `POST  ` `/api/marketing/evergreen/{client_id}` — Recycle Evergreen Content
- `POST  ` `/api/marketing/festival-autoschedule` — Festival Autoschedule
- `POST  ` `/api/marketing/festival-posts` — Generate Festival Posts
- `GET   ` `/api/marketing/festivals` — Get Festivals
- `POST  ` `/api/marketing/gbp-texts` — Generate Gbp Texts
- `GET   ` `/api/marketing/gbp-tips` — Get Gbp Tips
- `POST  ` `/api/marketing/hashtags` — Marketing Hashtags
- `GET   ` `/api/marketing/lead-scores` — Get Lead Scores
- `POST  ` `/api/marketing/missed-call-reply` — Generate Missed Call Reply
- `GET   ` `/api/marketing/packages` — Get Marketing Packages
- `POST  ` `/api/marketing/page-kit` — Generate Page Kit
- `POST  ` `/api/marketing/photo-poster` — Photo Poster
- `POST  ` `/api/marketing/post` — Generate Marketing Post
- `POST  ` `/api/marketing/post-variations` — Generate Post Variations
- `POST  ` `/api/marketing/poster` — Generate Svg Poster
- `GET   ` `/api/marketing/poster/templates` — Get Poster Templates
- `POST  ` `/api/marketing/reactivation` — Generate Reactivation Campaign
- `POST  ` `/api/marketing/reels` — Generate Reels Scripts
- `POST  ` `/api/marketing/referral` — Generate Referral Kit
- `GET   ` `/api/marketing/referral/stats` — Get Referral Stats
- `GET   ` `/api/marketing/report` — Get Monthly Report
- `POST  ` `/api/marketing/review-kit` — Generate Review Kit
- `POST  ` `/api/marketing/review-reply` — Generate Review Replies
- `GET   ` `/api/marketing/schedule` — Get Scheduled
- `POST  ` `/api/marketing/schedule` — Schedule Content
- `POST  ` `/api/marketing/schedule/run` — Run Schedule
- `POST  ` `/api/marketing/sentiment` — Marketing Sentiment
- `POST  ` `/api/marketing/upi-kit` — Generate Upi Kit
- `POST  ` `/api/marketing/upi-qr` — Generate Upi Qr
- `POST  ` `/api/marketing/whatsapp-pack` — Generate Whatsapp Pack

### Memory  (9)

- `GET   ` `/api/memory/entities` — Entities
- `GET   ` `/api/memory/entity` — Entity
- `PUT   ` `/api/memory/entity` — Entity Edit
- `GET   ` `/api/memory/prep` — Prep
- `POST  ` `/api/memory/sync` — Sync Now
- `GET   ` `/api/memory/topics` — Topics
- `POST  ` `/api/memory/topics` — Topic Add
- `DELETE` `/api/memory/topics/{topic_id}` — Topic Remove
- `POST  ` `/api/memory/topics/{topic_id}/refresh` — Topic Refresh

### Mini-site Builder  (12)

- `GET   ` `/api/minisite/config` — Read Config
- `POST  ` `/api/minisite/config` — Write Config
- `POST  ` `/api/minisite/logo` — Upload Logo
- `POST  ` `/api/minisite/logo-url` — Set Logo Url
- `GET   ` `/api/minisite/logo/{filename}` — Serve Logo
- `GET   ` `/api/minisite/palettes` — Get Palettes
- `GET   ` `/api/minisite/preview` — Preview Site
- `GET   ` `/api/minisite/reviews` — Admin List Reviews
- `POST  ` `/api/minisite/reviews/moderate` — Admin Moderate Review
- `GET   ` `/api/minisite/reviews/public` — Public Reviews
- `POST  ` `/api/minisite/reviews/submit` — Public Submit Review
- `GET   ` `/api/minisite/snippet` — Get Widget Snippet

### Niche Database  (10)

- `GET   ` `/api/niche/prospects` — List prospects
- `POST  ` `/api/niche/prospects` — Add single prospect
- `POST  ` `/api/niche/prospects/bulk` — Bulk import prospects
- `GET   ` `/api/niche/prospects/next-to-call` — Next prospects to call
- `PATCH ` `/api/niche/prospects/{lead_id}` — Post-call update
- `POST  ` `/api/niche/queue-call` — Push niche prospects into call queue
- `GET   ` `/api/niche/schema/{niche_key}` — Get niche call schema
- `GET   ` `/api/niche/schemas` — All niche schemas
- `GET   ` `/api/niche/stats` — Niche prospects stats
- `GET   ` `/api/niche/voice-niches` — All voice niches list

### OrchestrationExt  (4)

- `POST  ` `/api/agents-ext/consensus` — Consensus Vote
- `GET   ` `/api/agents-ext/trajectories` — Trajectories Best
- `POST  ` `/api/agents-ext/trajectory/export` — Trajectory Export
- `POST  ` `/api/agents-ext/trajectory/record` — Trajectory Record

### Platform  (17)

- `POST  ` `/api/platform/clients` — Create Client
- `GET   ` `/api/platform/clients/{client_id}/agents` — List Client Agents
- `POST  ` `/api/platform/clients/{client_id}/provision-agents` — Provision Client Agents
- `GET   ` `/api/platform/dashboard` — Get Dashboard
- `GET   ` `/api/platform/health` — Health Check
- `POST  ` `/api/platform/scrape/platform` — Trigger Platform Scrape
- `POST  ` `/api/platform/scrape/tenant/{tenant_id}` — Trigger Tenant Scrape
- `POST  ` `/api/platform/start` — Start Platform Api
- `GET   ` `/api/platform/stats` — Get Platform Stats
- `POST  ` `/api/platform/stop` — Stop Platform Api
- `GET   ` `/api/platform/tenants` — List Tenants
- `POST  ` `/api/platform/tenants` — Create Tenant
- `DELETE` `/api/platform/tenants/{tenant_id}` — Delete Tenant
- `GET   ` `/api/platform/tenants/{tenant_id}` — Get Tenant
- `POST  ` `/api/platform/tenants/{tenant_id}/pause` — Pause Tenant
- `POST  ` `/api/platform/tenants/{tenant_id}/resume` — Resume Tenant
- `POST  ` `/api/platform/tenants/{tenant_id}/upgrade` — Upgrade Tenant

### Privacy DPDP  (10)

- `POST  ` `/api/privacy/anonymize` — Anonymize
- `POST  ` `/api/privacy/dsar/delete` — Dsar Delete
- `POST  ` `/api/privacy/dsar/export` — Dsar Export
- `POST  ` `/api/privacy/erase` — Erase
- `POST  ` `/api/privacy/export` — Export
- `POST  ` `/api/privacy/find` — Find
- `POST  ` `/api/privacy/request` — Submit Privacy Request
- `GET   ` `/api/privacy/requests` — Get Requests
- `POST  ` `/api/privacy/requests/{request_id}/done` — Request Done
- `POST  ` `/api/privacy/retention/run` — Retention Run

### Public  (8)

- `POST  ` `/api/public/ai-demo` — Ai Demo
- `GET   ` `/api/public/audit/questions` — Audit Questions
- `POST  ` `/api/public/audit/score` — Audit Score
- `GET   ` `/api/public/inquiries` — List Inquiries
- `POST  ` `/api/public/inquiry` — Submit Inquiry
- `GET   ` `/api/public/pay-info` — Pay Info
- `POST  ` `/api/public/signup` — Public Signup
- `GET   ` `/api/public/turnstile/config` — Turnstile Config

### Reseller  (5)

- `GET   ` `/api/reseller/applications` — Reseller Applications
- `POST  ` `/api/reseller/applications/{aid}/approve` — Reseller Approve
- `POST  ` `/api/reseller/applications/{aid}/reject` — Reseller Reject
- `POST  ` `/api/reseller/apply` — Reseller Apply
- `GET   ` `/api/reseller/info` — Reseller Info

### SEO-Ops  (10)

- `GET   ` `/api/seoops/conversations` — Conversations List
- `GET   ` `/api/seoops/conversations/{key}` — Conversation Thread
- `POST  ` `/api/seoops/conversations/{key}/reply` — Conversation Reply
- `POST  ` `/api/seoops/dialer/disposition` — Dialer Disposition
- `GET   ` `/api/seoops/dialer/stats` — Dialer Stats
- `POST  ` `/api/seoops/rank/check` — Rank Check
- `GET   ` `/api/seoops/rank/config` — Rank Configs
- `POST  ` `/api/seoops/rank/config` — Rank Config
- `GET   ` `/api/seoops/rank/history` — Rank History
- `POST  ` `/api/seoops/rank/run` — Rank Run

### Segments  (6)

- `GET   ` `/api/segments` — List Segments
- `POST  ` `/api/segments` — Create Segment
- `GET   ` `/api/segments/_meta` — Segments Meta
- `DELETE` `/api/segments/{segment_id}` — Delete Segment
- `GET   ` `/api/segments/{segment_id}` — Get Segment
- `GET   ` `/api/segments/{segment_id}/preview` — Preview Segment

### Team  (14)

- `GET   ` `/api/platform/team` — Get Team Status
- `POST  ` `/api/platform/team/email-followups/run` — Run Email Followups Now
- `POST  ` `/api/platform/team/email-outreach/run` — Run Email Outreach Now
- `GET   ` `/api/platform/team/email-outreach/stats` — Get Email Outreach Stats
- `GET   ` `/api/platform/team/events` — Get Team Events
- `GET   ` `/api/platform/team/growth` — Get Growth
- `POST  ` `/api/platform/team/growth/run` — Run Growth Now
- `GET   ` `/api/platform/team/outreach-activity` — Get Outreach Activity
- `GET   ` `/api/platform/team/prospects` — Get Prospects
- `POST  ` `/api/platform/team/prospects/run` — Run Prospecting Now
- `POST  ` `/api/platform/team/prospects/{pid}/status` — Set Prospect Status
- `POST  ` `/api/platform/team/reply-triage/run` — Run Reply Triage Now
- `POST  ` `/api/platform/team/run/{member}` — Run Team Member
- `GET   ` `/api/platform/team/stats` — Get Team Stats

### Team Access  (7)

- `POST  ` `/api/team-access/auth/change-password` — Change Own Password
- `GET   ` `/api/team-access/me` — My Access
- `GET   ` `/api/team-access/members` — List Members
- `POST  ` `/api/team-access/members` — Create Member
- `PATCH ` `/api/team-access/members/{user_id}/modules` — Set Modules
- `POST  ` `/api/team-access/members/{user_id}/reset-password` — Reset Password
- `GET   ` `/api/team-access/modules` — List Modules

### Telephony  (3)

- `GET   ` `/api/telephony/vobiz/status` — Vobiz Status
- `POST  ` `/api/telephony/vobiz/stream-call` — Place Stream Call
- `POST  ` `/api/telephony/vobiz/test-call` — Place Test Call

### Telephony Webhooks  (6)

- `GET   ` `/api/webhooks/health` — Telephony Health
- `POST  ` `/api/webhooks/twilio/status/{call_id}` — Twilio Status Webhook
- `POST  ` `/api/webhooks/twilio/voice/{call_id}` — Twilio Voice Webhook
- `POST  ` `/api/webhooks/vobiz/answer` — Vobiz Answer Webhook
- `POST  ` `/api/webhooks/vobiz/inbound` — Vobiz Inbound Webhook
- `POST  ` `/api/webhooks/vobiz/status` — Vobiz Status Webhook

### UPI Payments  (4)

- `GET   ` `/api/upi/pending` — Admin: pending UPI submissions queue
- `POST  ` `/api/upi/pending/{pid}/approve` — Admin: approve a UPI submission
- `POST  ` `/api/upi/pending/{pid}/reject` — Admin: reject a UPI submission
- `POST  ` `/api/upi/submit` — Customer self-serve: maine pay kiya (UPI ref submit)

### Voice AI  (11)

- `POST  ` `/api/voiceai/ask` — Ask Calls
- `GET   ` `/api/voiceai/call-stats` — Call Stats
- `GET   ` `/api/voiceai/consent/history` — Consent History
- `POST  ` `/api/voiceai/consent/opt-in` — Consent Opt In
- `POST  ` `/api/voiceai/consent/opt-out` — Consent Opt Out
- `POST  ` `/api/voiceai/consent/record` — Consent Record
- `POST  ` `/api/voiceai/consent/retention-sweep` — Consent Retention Sweep
- `GET   ` `/api/voiceai/consent/suppressed` — Consent Suppressed
- `GET   ` `/api/voiceai/leaderboard` — Dialer Leaderboard
- `POST  ` `/api/voiceai/transfer` — Transfer Call
- `GET   ` `/api/voiceai/transfers` — Recent Transfers

### Voice Product  (6)

- `GET   ` `/api/voice/agents` — Voice Agents
- `GET   ` `/api/voice/niches` — Voice Niches
- `GET   ` `/api/voice/packages` — Voice Packages
- `GET   ` `/api/voice/quota` — Voice Quota
- `POST  ` `/api/voice/record-lead` — Record Lead
- `POST  ` `/api/voice/topup-link` — Lead Topup Link

### Web Call (Test Mode)  (3)

- `GET   ` `/api/web-call/config` — Web Call Config
- `GET   ` `/api/web-call/history` — Web Call History
- `GET   ` `/api/web-call/session/{session_id}` — Web Call Session Detail

### Web Test Calls (Admin)  (2)

- `GET   ` `/api/admin/web-calls` — List saved web test-call transcripts (all browsers)
- `GET   ` `/api/admin/web-calls/{session_id}` — One web test-call + full transcript

### Webhooks  (5)

- `POST  ` `/api/webhooks/stripe` — Stripe Webhook
- `POST  ` `/api/webhooks/twilio/incoming` — Twilio Webhook
- `POST  ` `/api/webhooks/twilio/status` — Twilio Status Webhook
- `GET   ` `/api/webhooks/whatsapp` — Whatsapp Webhook Verify
- `POST  ` `/api/webhooks/whatsapp` — Whatsapp Webhook Inbound

### WhatsApp  (15)

- `POST  ` `/api/wa/campaign/run` — Run Campaigns
- `POST  ` `/api/wa/campaign/schedule` — Schedule Campaign
- `GET   ` `/api/wa/campaigns` — List Campaigns
- `GET   ` `/api/wa/selfhost/qr` — Selfhost Qr
- `POST  ` `/api/wa/selfhost/start` — Selfhost Start
- `GET   ` `/api/wa/selfhost/status` — Selfhost Status
- `POST  ` `/api/wa/selfhost/webhook` — Selfhost Webhook
- `GET   ` `/api/wa/status` — Wa Status
- `GET   ` `/api/wa/suppression` — List Suppression
- `POST  ` `/api/wa/suppression` — Edit Suppression
- `GET   ` `/api/wa/templates` — List Templates
- `POST  ` `/api/wa/templates` — Register Template
- `POST  ` `/api/wa/templates/status` — Set Template Status
- `GET   ` `/api/wa/webhook` — Webhook Verify
- `POST  ` `/api/wa/webhook` — Webhook Inbound

### Widgets  (13)

- `POST  ` `/api/widgets/beacon` — Beacon Collect
- `GET   ` `/api/widgets/beacon-snippet` — Beacon Snippet
- `GET   ` `/api/widgets/beacon.js` — Beacon Js
- `GET   ` `/api/widgets/bio-config` — Bio Config Get
- `POST  ` `/api/widgets/bio-config` — Bio Config Save
- `GET   ` `/api/widgets/bio-stats` — Bio Stats
- `GET   ` `/api/widgets/bio/{slug}/c/{block_id}` — Bio Click
- `GET   ` `/api/widgets/popup-config` — Popup Config Get
- `POST  ` `/api/widgets/popup-config` — Popup Config Save
- `GET   ` `/api/widgets/popup-snippet` — Popup Snippet
- `POST  ` `/api/widgets/popup-wheel-coupons` — Popup Wheel Coupons
- `GET   ` `/api/widgets/popup.js` — Popup Js
- `GET   ` `/api/widgets/site-stats` — Site Stats

<!-- AUTO-OPENAPI:END -->
