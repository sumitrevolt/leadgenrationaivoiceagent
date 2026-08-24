# LeadGen AI Voice Agent - API Documentation

## Overview

RESTful API for the LeadGen AI Voice Agent platform. All endpoints return JSON responses.

**Base URL**: `https://leadsgenai.in` (production) or `http://localhost:8000` (development)

## Authentication

### API Key Authentication

Include the API key in the `X-API-Key` header:

```bash
curl -H "X-API-Key: your-api-key" https://leadsgenai.in/api/campaigns/
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

Lead scraping only — `POST /api/leads/scrape` (background scrape job) and
`GET /api/leads/stats/summary`. There is no CRUD here; real leads live in the
`Lead` DB model and are created via `/api/public/inquiry`, the lead harvester,
or campaign scraping (see `/api/campaigns` below).

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

# Create a campaign
campaign = client.post("/api/campaigns/", json={
    "name": "Mumbai Real Estate Q1",
    "niche": "real_estate"
}).json()

# List campaigns
campaigns = client.get("/api/campaigns/").json()
```

### JavaScript
```javascript
const response = await fetch('https://leadsgenai.in/api/campaigns/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': 'your-api-key'
  },
  body: JSON.stringify({
    name: 'Mumbai Real Estate Q1',
    niche: 'real_estate'
  })
});

const campaign = await response.json();
```

### cURL
```bash
# Create a campaign
curl -X POST https://leadsgenai.in/api/campaigns/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{"name": "Mumbai Real Estate Q1", "niche": "real_estate"}'
```

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for API version history.

---

<!-- AUTO-OPENAPI:START -->

## Endpoint Index — auto-generated from OpenAPI (1374 operations)

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

### Admin  (19)

- `POST  ` `/api/admin/2fa/activate` — Twofa Activate
- `POST  ` `/api/admin/2fa/disable` — Twofa Disable
- `POST  ` `/api/admin/2fa/recovery/regenerate` — Twofa Recovery Regen
- `POST  ` `/api/admin/2fa/setup` — Twofa Setup
- `GET   ` `/api/admin/2fa/status` — Twofa Status
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

### Admin Dashboard  (24)

- `GET   ` `/api/admin/activity-feed` — Get Activity Feed
- `GET   ` `/api/admin/agents` — Admin Agents
- `GET   ` `/api/admin/automation-logs` — Admin Automation Logs
- `GET   ` `/api/admin/boss-autopilot` — Get Boss Autopilot
- `POST  ` `/api/admin/clients/bulk-email` — Bulk Email Clients
- `POST  ` `/api/admin/clients/dedupe` — Admin Dedupe Clients
- `POST  ` `/api/admin/clients/{client_id}/delete` — Admin Delete Client
- `POST  ` `/api/admin/clients/{client_id}/delivery-action` — Admin Delivery Action
- `POST  ` `/api/admin/clients/{client_id}/remove-customer` — Admin Remove Customer
- `GET   ` `/api/admin/clients/{client_id}/timeline` — Get Client Timeline
- `GET   ` `/api/admin/command-center` — Admin Command Center
- `GET   ` `/api/admin/dashboard` — Get Admin Dashboard
- `GET   ` `/api/admin/delivery-assurance` — Admin Delivery Assurance
- `GET   ` `/api/admin/delivery-cockpit` — Admin Delivery Cockpit
- `GET   ` `/api/admin/delivery-logs` — Admin Delivery Logs
- `GET   ` `/api/admin/entitlement-assurance` — Admin Entitlement Assurance
- `GET   ` `/api/admin/hourly-activity` — Get Hourly Activity
- `GET   ` `/api/admin/live-stats` — Get Live Stats
- `GET   ` `/api/admin/ops-snapshot` — Get Ops Snapshot
- `POST  ` `/api/admin/ops/celery-trim` — Trim Celery Queue
- `GET   ` `/api/admin/prospects-preview` — Get Prospects Preview
- `GET   ` `/api/admin/revenue-analytics` — Get Revenue Analytics
- `GET   ` `/api/admin/revenue-trend` — Get Revenue Trend
- `GET   ` `/api/admin/sync-health` — Admin Sync Health

### Admin Ops  (31)

- `GET   ` `/api/admin/calls/recent` — Recent call outcomes / qualified summary
- `GET   ` `/api/admin/calls/{call_id}/detail` — Call transcript + termination detail
- `POST  ` `/api/admin/campaign/launch` — Launch outbound call campaign
- `GET   ` `/api/admin/campaign/status` — Last campaign run status
- `POST  ` `/api/admin/campaign/stop` — Stop the currently running campaign
- `POST  ` `/api/admin/clients/{client_id}/deliver-now` — Human-clicked single-customer delivery unstick
- `POST  ` `/api/admin/clients/{client_id}/onboard/scrape` — Admin-clicked customer website re-scrape
- `POST  ` `/api/admin/clients/{client_id}/password-reset` — Admin-clicked customer password reset
- `POST  ` `/api/admin/flow/seed-templates` — Apply all Flow Runner starter templates (FLOW_RUNNER=1)
- `GET   ` `/api/admin/leads/ready` — Uncontacted leads ready to call (campaign pre-flight)
- `GET   ` `/api/admin/office` — Admin Office — consolidated 'Sumit ke kaam' pending actions
- `GET   ` `/api/admin/swara-enterprise/status` — Swara free-AI sticky routing + STT gate + training loop status
- `GET   ` `/api/admin/system/summary` — System snapshot for God Mode panel
- `POST  ` `/api/admin/trust/configure-posthog` — Set PostHog API key + host (no restart)
- `POST  ` `/api/admin/trust/configure-sentry` — Set Sentry DSN (lazy web init; worker restart recommended)
- `POST  ` `/api/admin/trust/configure-turnstile` — Set Turnstile keys (no restart)
- `GET   ` `/api/admin/trust/status` — Turnstile + Sentry + PostHog armed status
- `POST  ` `/api/admin/upi/activate` — Activate plan after UPI screenshot verified
- `GET   ` `/api/admin/upi/clients` — Search clients for manual UPI activate
- `POST  ` `/api/admin/upi/configure` — Set platform UPI VPA (data file — no container restart)
- `GET   ` `/api/admin/upi/pending` — Clients waiting for UPI screenshot activation
- `POST  ` `/api/admin/voice-launch/kill` — Engage/release the voice-calling kill switch
- `GET   ` `/api/admin/voice-launch/session` — Current voice-launch session status
- `POST  ` `/api/admin/voice-launch/session` — Start a NEW voice-launch session (canonical reset)
- `POST  ` `/api/admin/voice-launch/session/stop` — Emergency-stop the current voice-launch session
- `GET   ` `/api/admin/voice-launch/status` — Controlled voice-calling launch status
- `GET   ` `/api/admin/voice/bookings` — Appointments the AI voice agent booked (durable ledger)
- `GET   ` `/api/admin/voice/gemini-keys` — Voice Gemini key pool status (masked)
- `POST  ` `/api/admin/voice/gemini-keys` — Validate + save voice Gemini keys (no restart)
- `GET   ` `/api/admin/voice/latency` — Voice agent per-turn latency rollup (P50/P95) — proves call speed
- `GET   ` `/api/admin/voice/self-test` — Built-in voice self-test (personas + stack + live)

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
- `POST  ` `/api/billing/webhooks/stripe` — Stripe Webhook Removed

### Blueprint  (5)

- `GET   ` `/api/blueprint/graph` — Blueprint Graph
- `GET   ` `/api/blueprint/meta` — Blueprint Meta
- `GET   ` `/api/blueprint/public` — Blueprint Public
- `GET   ` `/api/blueprint/trace` — Blueprint Trace
- `GET   ` `/api/blueprint/validate` — Blueprint Validate

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

### ClientOps  (38)

- `POST  ` `/api/clientops/approval` — Submit Approval
- `GET   ` `/api/clientops/approvals` — List Approvals
- `POST  ` `/api/clientops/approvals/retire-orphans` — Retire Orphaned Approvals
- `POST  ` `/api/clientops/approvals/{approval_id}/decide` — Admin Decide Approval
- `GET   ` `/api/clientops/approve/{token}` — Public Approve
- `POST  ` `/api/clientops/creative-os/generate` — Creative Os Generate
- `GET   ` `/api/clientops/creative-os/ops` — Creative Os Ops
- `POST  ` `/api/clientops/creative-os/{creative_id}/approve` — Creative Os Approve
- `POST  ` `/api/clientops/creative-os/{creative_id}/changes` — Creative Os Changes
- `GET   ` `/api/clientops/creative-os/{creative_id}/customer-view` — Creative Os Customer View
- `GET   ` `/api/clientops/creative-os/{creative_id}/publish-gate` — Creative Os Publish Gate
- `POST  ` `/api/clientops/creative-os/{creative_id}/quarantine` — Creative Os Quarantine
- `GET   ` `/api/clientops/gsc/overview` — Gsc Overview
- `GET   ` `/api/clientops/p/{token}` — Proposal Open
- `GET   ` `/api/clientops/posthog/funnel` — Posthog Funnel Overview
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
- `POST  ` `/api/clientops/video-production/daily-clear-block` — Video Daily Clear Block
- `POST  ` `/api/clientops/video-production/daily-run` — Video Daily Run
- `GET   ` `/api/clientops/video-production/daily-status` — Video Production Daily Status
- `POST  ` `/api/clientops/video-production/generate` — Video Production Generate
- `GET   ` `/api/clientops/video-production/ops` — Video Production Ops
- `POST  ` `/api/clientops/video-production/{video_ad_id}/approve` — Video Production Approve
- `GET   ` `/api/clientops/video/daily-status` — Video Daily Status

### Clients  (7)

- `GET   ` `/api/clients` — List All Clients
- `POST  ` `/api/clients` — Create Client
- `GET   ` `/api/clients/{cid}` — Get One Client
- `GET   ` `/api/clients/{cid}/content` — Get Client Content
- `POST  ` `/api/clients/{cid}/content/run` — Run Client Content
- `POST  ` `/api/clients/{cid}/content/{item_id}/status` — Set Content Item Status
- `PATCH ` `/api/clients/{cid}/status` — Set Client Status

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

### Control Center  (6)

- `GET   ` `/api/control-center/agents/metrics` — Control Center Agents Metrics
- `GET   ` `/api/control-center/cost-rollup` — Control Center Cost Rollup
- `GET   ` `/api/control-center/node-stats` — Control Center Node Stats
- `GET   ` `/api/control-center/overview` — Control Center Overview
- `GET   ` `/api/control-center/rca` — Control Center Rca
- `GET   ` `/api/control-center/route-hits` — Control Center Route Hits

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

### Customer Dashboard  (40)

- `GET   ` `/api/customer/approvals/pending` — Customer Pending Approvals
- `POST  ` `/api/customer/approvals/{approval_id}/council-decide` — Customer Approval Council Decide
- `POST  ` `/api/customer/approvals/{approval_id}/decide` — Customer Decide Approval
- `GET   ` `/api/customer/autopilot` — Customer Autopilot Drafts
- `GET   ` `/api/customer/branded-feed` — Customer Branded Feed
- `POST  ` `/api/customer/campaigns/generate-first-week` — Customer Generate First Week
- `GET   ` `/api/customer/creative-os` — Customer Creative Os List
- `POST  ` `/api/customer/creative-os/{creative_id}/feedback` — Customer Creative Os Feedback
- `GET   ` `/api/customer/creative-os/{creative_id}/media` — Customer Creative Os Media
- `GET   ` `/api/customer/creatives` — Customer Creatives
- `GET   ` `/api/customer/dashboard` — Get Customer Dashboard
- `POST  ` `/api/customer/dashboard/send-to-crm` — Send Dashboard Leads To Crm
- `GET   ` `/api/customer/delivery-proof` — Customer Delivery Proof
- `POST  ` `/api/customer/gbp/council-suggest` — Customer Gbp Council Suggest
- `GET   ` `/api/customer/gbp/questions` — Customer Gbp Questions
- `POST  ` `/api/customer/gbp/score` — Customer Gbp Score
- `GET   ` `/api/customer/health` — Customer Dashboard Health
- `POST  ` `/api/customer/kb-info` — Customer Kb Info
- `PATCH ` `/api/customer/leads/{lead_id}` — Patch Lead Status
- `GET   ` `/api/customer/office` — Get Customer Office
- `GET   ` `/api/customer/profile` — Customer Get Profile
- `POST  ` `/api/customer/profile` — Customer Update Profile
- `GET   ` `/api/customer/report` — Customer Monthly Report
- `GET   ` `/api/customer/routing` — Customer Routing Get
- `POST  ` `/api/customer/routing` — Customer Routing Set
- `GET   ` `/api/customer/social/accounts` — Customer Social Accounts
- `POST  ` `/api/customer/social/accounts/connect` — Customer Social Accounts Connect
- `DELETE` `/api/customer/social/accounts/{platform}` — Customer Social Accounts Disconnect
- `GET   ` `/api/customer/social/config` — Customer Social Get
- `POST  ` `/api/customer/social/config` — Customer Social Save
- `GET   ` `/api/customer/social/readiness` — Customer Social Readiness
- `GET   ` `/api/customer/speed-to-lead` — Customer Speed To Lead
- `GET   ` `/api/customer/team` — Get Customer Team
- `GET   ` `/api/customer/timeline` — Customer Delivery Timeline
- `GET   ` `/api/customer/videos` — Customer Videos List
- `POST  ` `/api/customer/videos/{video_ad_id}/feedback` — Customer Video Feedback
- `GET   ` `/api/customer/videos/{video_ad_id}/media` — Customer Video Media
- `GET   ` `/api/customer/videos/{video_ad_id}/preview` — Customer Video Preview
- `POST  ` `/api/customer/voice/call-queue` — Customer Voice Call Queue
- `GET   ` `/api/customer/voice/queue-status` — Customer Voice Queue Status

### Customer Flows  (12)

- `POST  ` `/api/customer/flow` — Cf Save
- `GET   ` `/api/customer/flow-templates` — Cf Templates
- `POST  ` `/api/customer/flow-templates/{tid}/apply` — Cf Apply Template
- `GET   ` `/api/customer/flow/run/{run_id}` — Cf Run Status
- `POST  ` `/api/customer/flow/run/{run_id}/approve` — Cf Approve
- `POST  ` `/api/customer/flow/run/{run_id}/reject` — Cf Reject
- `DELETE` `/api/customer/flow/{flow_id}` — Cf Delete
- `GET   ` `/api/customer/flow/{flow_id}` — Cf Get
- `POST  ` `/api/customer/flow/{flow_id}/rollback` — Cf Rollback
- `POST  ` `/api/customer/flow/{flow_id}/run` — Cf Run
- `GET   ` `/api/customer/flow/{flow_id}/versions` — Cf Versions
- `GET   ` `/api/customer/flows` — Cf List

### Customer Marketing Studio  (91)

- `POST  ` `/api/customer/studio/ads` — Studio Ads
- `GET   ` `/api/customer/studio/aeo-checklist` — Studio Aeo Checklist
- `POST  ` `/api/customer/studio/ai-image` — Studio Ai Image
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
- `POST  ` `/api/customer/studio/complete-post` — Studio Complete Post
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
- `POST  ` `/api/customer/studio/upi-qr` — Studio Upi Qr
- `POST  ` `/api/customer/studio/variations` — Studio Variations
- `POST  ` `/api/customer/studio/voiceover` — Studio Voiceover
- `GET   ` `/api/customer/studio/website-widget` — Studio Website Widget
- `POST  ` `/api/customer/studio/whatsapp` — Studio Whatsapp
- `GET   ` `/api/customer/studio/whatsapp-catalog` — Studio Whatsapp Catalog
- `POST  ` `/api/customer/studio/win-back` — Studio Win Back
- `POST  ` `/api/customer/studio/youtube-metadata` — Studio Youtube Metadata

### Customer Pipeline  (1)

- `GET   ` `/api/customer/pipeline` — Customer Pipeline

### Customer Plugins  (1)

- `GET   ` `/api/customer/plugins` — Customer Plugins

### Customer Portal  (13)

- `POST  ` `/api/customer/auth/change-password` — Customer Change Password
- `POST  ` `/api/customer/auth/login` — Customer Login
- `POST  ` `/api/customer/auth/logout` — Logout
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

### DSH Internal  (6)

- `POST  ` `/internal/dsh/approval-proposals` — Approval Proposal
- `POST  ` `/internal/dsh/capabilities/{capability}/submissions` — Capability Submit
- `POST  ` `/internal/dsh/heartbeat` — Dsh Heartbeat
- `GET   ` `/internal/dsh/submissions/{submission_id}` — Capability Status
- `POST  ` `/internal/dsh/submissions/{submission_id}/wait` — Capability Wait
- `POST  ` `/internal/dsh/v1/chat/completions` — Chat Completions

### Dashboard Assessment  (6)

- `GET   ` `/api/assessment/diff` — Get Diff
- `GET   ` `/api/assessment/history` — List History
- `GET   ` `/api/assessment/latest` — Get Latest
- `GET   ` `/api/assessment/report` — Get Report Markdown
- `POST  ` `/api/assessment/run` — Run Assessment
- `GET   ` `/api/assessment/scores` — Get Scores

### Data Intelligence  (18)

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
- `GET   ` `/api/data/niches/pending` — List Pending Niches
- `POST  ` `/api/data/niches/pending` — Submit Pending Niche
- `DELETE` `/api/data/niches/pending/{pending_id}` — Reject Pending Niche
- `POST  ` `/api/data/niches/pending/{pending_id}/approve` — Approve Pending Niche
- `DELETE` `/api/data/niches/{niche_key}` — Delete Custom Niche
- `POST  ` `/api/data/reports` — Generate Report
- `GET   ` `/api/data/usage` — Get Usage Stats

### Deep Research  (2)

- `POST  ` `/api/research/deep/run` — Run
- `GET   ` `/api/research/deep/status` — Status

### Dev Task Control Plane  (34)

- `GET   ` `/api/dev-tasks` — List Tasks
- `POST  ` `/api/dev-tasks` — Create Task
- `POST  ` `/api/dev-tasks/claim-next` — Claim Next Task
- `GET   ` `/api/dev-tasks/missions` — List Missions
- `POST  ` `/api/dev-tasks/missions` — Create Mission
- `POST  ` `/api/dev-tasks/missions/recover-stale` — Missions Recover Stale
- `GET   ` `/api/dev-tasks/missions/status` — Missions Status
- `POST  ` `/api/dev-tasks/missions/{mission_id}/advance` — Mission Advance
- `POST  ` `/api/dev-tasks/missions/{mission_id}/cancel` — Mission Cancel
- `POST  ` `/api/dev-tasks/missions/{mission_id}/claim` — Mission Claim
- `POST  ` `/api/dev-tasks/missions/{mission_id}/heartbeat` — Mission Heartbeat
- `POST  ` `/api/dev-tasks/missions/{mission_id}/preflight` — Mission Preflight
- `POST  ` `/api/dev-tasks/missions/{mission_id}/result` — Mission Result
- `POST  ` `/api/dev-tasks/missions/{mission_id}/retry` — Mission Retry
- `POST  ` `/api/dev-tasks/missions/{mission_id}/review` — Mission Review
- `GET   ` `/api/dev-tasks/missions/{mission_id}/rollback` — Mission Rollback
- `POST  ` `/api/dev-tasks/missions/{mission_id}/run-runner` — Mission Run Runner
- `POST  ` `/api/dev-tasks/missions/{mission_id}/start` — Mission Start
- `GET   ` `/api/dev-tasks/models` — List Models
- `POST  ` `/api/dev-tasks/reconcile` — Reconcile
- `POST  ` `/api/dev-tasks/route-preview` — Preview Route
- `GET   ` `/api/dev-tasks/status` — Dev Status
- `POST  ` `/api/dev-tasks/{task_id}/approve-production` — Approve Production
- `POST  ` `/api/dev-tasks/{task_id}/claim` — Claim Task
- `POST  ` `/api/dev-tasks/{task_id}/finalize-delivery` — Finalize Delivery
- `POST  ` `/api/dev-tasks/{task_id}/governor-review` — Record Governor Review Endpoint
- `POST  ` `/api/dev-tasks/{task_id}/heartbeat` — Heartbeat Task
- `POST  ` `/api/dev-tasks/{task_id}/promote-staging` — Promote Staging
- `POST  ` `/api/dev-tasks/{task_id}/reject-production` — Reject Production
- `POST  ` `/api/dev-tasks/{task_id}/report` — Record Report
- `POST  ` `/api/dev-tasks/{task_id}/request-approval` — Request Approval
- `POST  ` `/api/dev-tasks/{task_id}/run` — Run Task
- `POST  ` `/api/dev-tasks/{task_id}/transition` — Transition Task
- `GET   ` `/api/dev-tasks/{task_id}/usage` — Task Usage

### Docs AI Edit  (3)

- `GET   ` `/api/docs/edit/actions` — List Actions
- `POST  ` `/api/docs/edit/run` — Run Edit
- `GET   ` `/api/docs/edit/status` — Status

### Email Tracking  (3)

- `GET   ` `/api/admin/email-tracking/stats` — Email Tracking Stats
- `GET   ` `/t/c/{token}` — Track Click
- `GET   ` `/t/o/{token}` — Track Open

### EngAgents  (7)

- `POST  ` `/api/agents-ext/checkpoint` — Checkpoint Create
- `GET   ` `/api/agents-ext/checkpoints` — Checkpoints List
- `POST  ` `/api/agents-ext/code-review` — Code Review
- `GET   ` `/api/agents-ext/personas` — Get Agent Personas
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

### Frontend  (77)

- `GET   ` `/admin` — Legacy Alias Admin
- `GET   ` `/app/admin` — Admin Dashboard Page
- `GET   ` `/app/admin-login` — Admin Login Page
- `GET   ` `/app/admin/db` — Admin Db Explorer Page
- `GET   ` `/app/affiliates` — Affiliates Page
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
- `GET   ` `/app/control-center` — Control Center Page
- `GET   ` `/app/conversations` — Conversations Page
- `GET   ` `/app/coordination` — Coordination Hub Page
- `GET   ` `/app/customer` — Customer Dashboard Page
- `GET   ` `/app/customer/billing` — Customer View Alias Billing
- `GET   ` `/app/customer/calendar` — Customer View Alias Calendar
- `GET   ` `/app/customer/delivery` — Customer View Alias Delivery
- `GET   ` `/app/customer/flows` — Customer Flows Page
- `GET   ` `/app/customer/leads` — Customer View Alias Leads
- `GET   ` `/app/customer/marketing` — Customer Marketing Page
- `GET   ` `/app/customer/office` — Customer Office Page
- `GET   ` `/app/customer/pipeline` — Customer Pipeline Page
- `GET   ` `/app/customer/reports` — Customer View Alias Reports
- `GET   ` `/app/customer/setup` — Customer View Alias Setup
- `GET   ` `/app/customer/support` — Customer View Alias Support
- `GET   ` `/app/customer/voice` — Customer Voice Page
- `GET   ` `/app/dashboard` — Legacy Alias App Dashboard
- `GET   ` `/app/dashboards` — Dashboards Page
- `GET   ` `/app/deals` — Deals Page
- `GET   ` `/app/delivery-command-center` — Delivery Command Center Page
- `GET   ` `/app/dev-control` — Dev Control Page
- `GET   ` `/app/dialer` — Dialer Page
- `GET   ` `/app/explorer` — Architecture Explorer Page
- `GET   ` `/app/growth-tools` — Growth Tools Page
- `GET   ` `/app/impersonate` — Impersonate Page
- `GET   ` `/app/inbox` — Inbox Page
- `GET   ` `/app/journeys` — Journeys Page
- `GET   ` `/app/login` — Customer Login Page
- `GET   ` `/app/marketing` — Marketing Page
- `GET   ` `/app/minisite-builder` — Minisite Builder Page
- `GET   ` `/app/office` — Office Map Page
- `GET   ` `/app/onboard` — Onboard Page
- `GET   ` `/app/ops` — Ops Page
- `GET   ` `/app/outreach` — Outreach Page
- `GET   ` `/app/owner` — Owner Os Page
- `GET   ` `/app/plugins` — Customer Plugins Page
- `GET   ` `/app/revenue-kit` — Revenue Kit Page
- `GET   ` `/app/segments` — Segments Page
- `GET   ` `/app/studio` — Studio Page
- `GET   ` `/app/team` — Team Dashboard Page
- `GET   ` `/app/team-access` — Team Access Page
- `GET   ` `/app/test-call` — Web Call Test Page
- `GET   ` `/app/voice-keys` — Voice Keys Page
- `GET   ` `/app/whatsapp` — Whatsapp Page
- `GET   ` `/audit` — Public Audit Page
- `GET   ` `/compare` — Public Compare Page
- `GET   ` `/dashboard` — Legacy Alias Dashboard
- `GET   ` `/demo` — Public Demo Page
- `GET   ` `/geo-check` — Public Geo Check Page
- `GET   ` `/manifest.json` — Pwa Manifest
- `GET   ` `/pay/{order_ref}` — Pay Page
- `GET   ` `/pricing` — Pricing Page
- `GET   ` `/privacy` — Privacy Page
- `GET   ` `/refund` — Refund Page
- `GET   ` `/reseller` — Reseller Page
- `GET   ` `/site-audit` — Public Site Audit Page
- `GET   ` `/start` — Start Alias Page
- `GET   ` `/status` — Status Page
- `GET   ` `/sw.js` — Pwa Service Worker
- `GET   ` `/terms` — Terms Page
- `GET   ` `/voice` — Legacy Alias Voice
- `GET   ` `/voice-agent` — Voice Agent Product Page

### Goals  (5)

- `GET   ` `/api/goals` — List Goals
- `POST  ` `/api/goals` — Create Goal
- `GET   ` `/api/goals/{goal_id}` — Get Goal
- `PATCH ` `/api/goals/{goal_id}` — Update Goal
- `POST  ` `/api/goals/{goal_id}/tasks` — Link Task

### Growth  (224)

- `POST  ` `/api/growth/affiliate/kit` — Affiliate Kit
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
- `POST  ` `/api/growth/infra/dlq/resolve` — Infra Dlq Resolve
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
- `POST  ` `/api/growth/persona/architect` — Build Persona
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
- `GET   ` `/api/growth/reply/hot-queue` — Reply Hot Queue
- `POST  ` `/api/growth/reply/hot-queue/council-decide` — Reply Hot Queue Council Decide
- `POST  ` `/api/growth/reply/hot-queue/done` — Reply Hot Queue Done
- `POST  ` `/api/growth/reply/hot-queue/park` — Reply Hot Queue Park
- `POST  ` `/api/growth/reply/hot-queue/quick-done/{token}` — Reply Hot Queue Quick Done
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
- `POST  ` `/api/growth/revenue/invoice-void` — Revenue Invoice Void
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
- `GET   ` `/api/growth/social/jobs` — Admin Social Jobs
- `POST  ` `/api/growth/social/jobs/{job_id}/cancel` — Admin Social Job Cancel
- `POST  ` `/api/growth/social/jobs/{job_id}/retry` — Admin Social Job Retry
- `POST  ` `/api/growth/social/jobs/{job_id}/run-now` — Admin Social Job Run Now
- `GET   ` `/api/growth/social/latest-events` — Admin Social Latest Events
- `GET   ` `/api/growth/social/pause` — Admin Social Pause Status
- `POST  ` `/api/growth/social/pause` — Admin Social Pause Set
- `POST  ` `/api/growth/social/postiz/configure` — Social Postiz Configure
- `GET   ` `/api/growth/social/postiz/status` — Social Postiz Status
- `POST  ` `/api/growth/social/recover-stale` — Admin Social Recover Stale
- `GET   ` `/api/growth/social/token-health` — Admin Social Token Health
- `GET   ` `/api/growth/speed-to-lead/breakdown` — Speed To Lead Breakdown
- `GET   ` `/api/growth/speed-to-lead/summary` — Speed To Lead Summary
- `POST  ` `/api/growth/tools/google-score` — Tool Google Score
- `POST  ` `/api/growth/tools/lead-cost` — Tool Lead Cost
- `POST  ` `/api/growth/tools/missed-call-revenue` — Tool Missed Call
- `POST  ` `/api/growth/tools/website-audit` — Website Audit Public
- `POST  ` `/api/growth/triage/classify` — Classify Inbound
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

### Health  (8)

- `GET   ` `/api/v1/status` — Api Status
- `GET   ` `/health` — Health Check
- `GET   ` `/health/deep` — Deep Health Check
- `GET   ` `/health/live` — Liveness Check
- `GET   ` `/health/platform` — Platform Detailed Health
- `GET   ` `/health/ready` — Readiness Check
- `GET   ` `/health/signup` — Signup Health
- `GET   ` `/metrics` — Prometheus Metrics

### Impersonation  (4)

- `GET   ` `/api/impersonate/config` — Impersonation Config
- `POST  ` `/api/impersonate/start` — Impersonation Start
- `POST  ` `/api/impersonate/stop` — Impersonation Stop
- `GET   ` `/api/impersonate/targets` — Impersonation Targets

### Infrastructure  (43)

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
- `POST  ` `/api/memory-stack/assemble` — Assemble
- `GET   ` `/api/memory-stack/diagnostics` — Diagnostics
- `GET   ` `/api/memory-stack/governance` — Governance
- `POST  ` `/api/memory-stack/governance/forget` — Governance Forget
- `POST  ` `/api/memory-stack/governance/suppress` — Governance Suppress
- `GET   ` `/api/memory-stack/prospective` — Prospective
- `POST  ` `/api/memory-stack/prospective` — Prospective Add
- `POST  ` `/api/memory-stack/prospective/drain` — Prospective Drain
- `POST  ` `/api/memory-stack/prospective/{entry_id}/cancel` — Prospective Cancel
- `POST  ` `/api/memory-stack/purge` — Purge
- `GET   ` `/api/memory-stack/stats` — Stats
- `GET   ` `/api/rl/arms` — Rl Arms
- `GET   ` `/api/rl/dev` — Rl Dev
- `GET   ` `/api/rl/recent` — Rl Recent
- `GET   ` `/api/rl/summary` — Rl Summary
- `GET   ` `/api/workforce-memory/bindings/{agent_id}` — Bindings
- `GET   ` `/api/workforce-memory/drilldown` — Drilldown
- `POST  ` `/api/workforce-memory/equip` — Equip
- `GET   ` `/api/workforce-memory/equipments` — Equipments
- `GET   ` `/api/workforce-memory/inspect` — Inspect
- `POST  ` `/api/workforce-memory/prune` — Prune
- `POST  ` `/api/workforce-memory/purge` — Purge
- `GET   ` `/api/workforce-memory/recall` — Recall
- `POST  ` `/api/workforce-memory/remember` — Remember
- `GET   ` `/api/workforce-memory/stats` — Stats

### Integrations  (2)

- `GET   ` `/api/admin/integrations/health` — Admin Integrations Health
- `GET   ` `/api/customer/integrations/health` — Customer Integrations Health

### Journeys  (7)

- `GET   ` `/api/journeys` — Get Journeys
- `POST  ` `/api/journeys` — Create Journey
- `POST  ` `/api/journeys/emit` — Emit Event
- `GET   ` `/api/journeys/runs` — List Runs
- `POST  ` `/api/journeys/seed` — Seed Defaults
- `DELETE` `/api/journeys/{jid}` — Delete Journey
- `POST  ` `/api/journeys/{jid}/toggle` — Toggle Journey

### LLM Compare  (5)

- `GET   ` `/api/llm/compare/providers` — List Providers
- `POST  ` `/api/llm/compare/run` — Run Compare
- `GET   ` `/api/llm/compare/stats` — Stats
- `GET   ` `/api/llm/compare/status` — Status
- `POST  ` `/api/llm/compare/vote` — Vote

### Leads  (3)

- `POST  ` `/api/leads/scrape` — Scrape Leads
- `GET   ` `/api/leads/scrape/{task_id}` — Get Scrape Status
- `GET   ` `/api/leads/stats/summary` — Get Leads Summary

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

### ML Training  (32)

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
- `GET   ` `/api/ml/improvement-plan` — Get Agent Improvement Plan
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

### Marketing Features  (28)

- `GET   ` `/api/marketing-features/appointments/list` — List Appointments
- `POST  ` `/api/marketing-features/appointments/schedule` — Schedule Appointment
- `GET   ` `/api/marketing-features/appointments/stats` — Appointment Stats
- `POST  ` `/api/marketing-features/appointments/{reminder_id}/status` — Update Appointment Status
- `POST  ` `/api/marketing-features/email-drips/create` — Create Email Drip
- `GET   ` `/api/marketing-features/email-drips/list` — List Email Drips
- `POST  ` `/api/marketing-features/email-drips/start` — Start Email Drip
- `GET   ` `/api/marketing-features/email-drips/stats` — Email Drip Stats
- `GET   ` `/api/marketing-features/email-drips/templates` — Drip Templates
- `POST  ` `/api/marketing-features/forms/create` — Create Form Endpoint
- `POST  ` `/api/marketing-features/forms/create-from-template` — Create Form From Template
- `GET   ` `/api/marketing-features/forms/list` — List Forms Endpoint
- `GET   ` `/api/marketing-features/forms/stats` — Form Stats
- `POST  ` `/api/marketing-features/forms/submit` — Submit Form
- `GET   ` `/api/marketing-features/forms/templates` — Form Templates
- `GET   ` `/api/marketing-features/health/all` — All Health
- `GET   ` `/api/marketing-features/health/client/{client_id}` — Client Health
- `POST  ` `/api/marketing-features/health/score` — Score Customer Health
- `GET   ` `/api/marketing-features/health/summary` — Health Summary
- `POST  ` `/api/marketing-features/proposals/generate` — Generate Proposal Endpoint
- `GET   ` `/api/marketing-features/proposals/list` — List Proposals Endpoint
- `GET   ` `/api/marketing-features/proposals/stats` — Proposal Stats
- `GET   ` `/api/marketing-features/proposals/templates` — Proposal Templates
- `POST  ` `/api/marketing-features/proposals/{proposal_id}/status` — Update Proposal Status
- `POST  ` `/api/marketing-features/review-automation/reply` — Review Reply
- `GET   ` `/api/marketing-features/review-automation/sequences` — List Review Sequences
- `POST  ` `/api/marketing-features/review-automation/start` — Start Review Sequence
- `GET   ` `/api/marketing-features/review-automation/stats` — Review Stats

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

### Model Cookbook  (4)

- `GET   ` `/api/cookbook/models` — List Models
- `POST  ` `/api/cookbook/recommend` — Recommend
- `GET   ` `/api/cookbook/status` — Status
- `GET   ` `/api/cookbook/tasks` — List Tasks

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

### OKF  (4)

- `POST  ` `/api/admin/okf/dry-run` — Okf Dry Run
- `POST  ` `/api/admin/okf/ingest` — Okf Ingest Route
- `GET   ` `/api/admin/okf/recall` — Okf Recall
- `GET   ` `/api/admin/okf/status` — Okf Status

### Onboarding Pipeline  (6)

- `GET   ` `/api/admin/onboard-pipeline/backpressure` — Backpressure Status
- `GET   ` `/api/admin/onboard-pipeline/metrics` — Capacity Metrics
- `POST  ` `/api/admin/onboard-pipeline/retry/{cid}/{stage}` — Retry Stage
- `POST  ` `/api/admin/onboard-pipeline/run` — Trigger Pipeline
- `GET   ` `/api/admin/onboard-pipeline/status` — List Pipelines
- `GET   ` `/api/admin/onboard-pipeline/status/{cid}` — Get Pipeline Status

### Onboarding Wizard  (4)

- `POST  ` `/api/onboard-wizard/apply` — Apply Wizard Setup
- `GET   ` `/api/onboard-wizard/business-types` — List Business Types
- `GET   ` `/api/onboard-wizard/preview/{business_type}` — Preview Template
- `POST  ` `/api/onboard-wizard/script-preview` — Preview Script

### Operating HQ  (15)

- `GET   ` `/api/platform/office/agent-os-status` — Office Agent Os Status
- `POST  ` `/api/platform/office/agents/{member}/pause` — Office Pause Agent
- `POST  ` `/api/platform/office/agents/{member}/resume` — Office Resume Agent
- `POST  ` `/api/platform/office/agents/{member}/task` — Office Agent Task
- `POST  ` `/api/platform/office/ask` — Office Ask
- `POST  ` `/api/platform/office/boss-review` — Office Boss Review
- `GET   ` `/api/platform/office/briefing` — Office Briefing
- `GET   ` `/api/platform/office/briefing/audio` — Office Briefing Audio
- `POST  ` `/api/platform/office/improve` — Office Improvement Council
- `POST  ` `/api/platform/office/pipeline/item/{item_id}/assign` — Office Assign Owner
- `POST  ` `/api/platform/office/pipeline/item/{item_id}/move` — Office Move Item
- `POST  ` `/api/platform/office/pipeline/item/{item_id}/next-action` — Office Set Next Action
- `POST  ` `/api/platform/office/pipeline/item/{item_id}/resolve-stuck` — Office Resolve Stuck
- `GET   ` `/api/platform/office/pipeline/{stage_id}` — Office Pipeline Stage
- `GET   ` `/api/platform/office/snapshot` — Office Snapshot

### OrchestrationExt  (4)

- `POST  ` `/api/agents-ext/consensus` — Consensus Vote
- `GET   ` `/api/agents-ext/trajectories` — Trajectories Best
- `POST  ` `/api/agents-ext/trajectory/export` — Trajectory Export
- `POST  ` `/api/agents-ext/trajectory/record` — Trajectory Record

### Owner Brief  (1)

- `GET   ` `/api/admin/owner-brief` — Owner Brief

### Owner Copilot  (7)

- `GET   ` `/api/owner-copilot/approvals` — Copilot Approvals
- `GET   ` `/api/owner-copilot/catalogue` — Copilot Catalogue
- `POST  ` `/api/owner-copilot/command` — Copilot Command
- `GET   ` `/api/owner-copilot/commands/{command_id}` — Copilot Get Command
- `GET   ` `/api/owner-copilot/daily-brief` — Copilot Daily Brief
- `POST  ` `/api/owner-copilot/nl` — Copilot Nl
- `GET   ` `/api/owner-copilot/status` — Copilot Status

### Owner Email Canary  (3)

- `GET   ` `/api/admin/owner-email-canary/last` — Owner Email Canary Last
- `GET   ` `/api/admin/owner-email-canary/preflight` — Owner Email Canary Preflight
- `POST  ` `/api/admin/owner-email-canary/send` — Owner Email Canary Send

### Owner OS  (37)

- `GET   ` `/api/admin/owner-os/agents` — Owner Agents
- `GET   ` `/api/admin/owner-os/agents/{agent_id}` — Owner Agent Detail
- `POST  ` `/api/admin/owner-os/agents/{agent_id}/cancel-queued` — Owner Cancel Queued
- `POST  ` `/api/admin/owner-os/agents/{agent_id}/controls` — Owner Set Agent Controls
- `POST  ` `/api/admin/owner-os/agents/{agent_id}/pause` — Owner Pause Agent
- `POST  ` `/api/admin/owner-os/agents/{agent_id}/request-cancel-running` — Owner Request Cancel Running
- `POST  ` `/api/admin/owner-os/agents/{agent_id}/restore-defaults` — Owner Restore Agent Defaults
- `POST  ` `/api/admin/owner-os/agents/{agent_id}/resume` — Owner Resume Agent
- `GET   ` `/api/admin/owner-os/approvals` — Owner Approvals
- `POST  ` `/api/admin/owner-os/approvals/verification` — Owner Create Verification Approval
- `POST  ` `/api/admin/owner-os/approvals/{source}/{item_id}/decide` — Owner Decide Approval
- `GET   ` `/api/admin/owner-os/audit` — Owner Audit
- `GET   ` `/api/admin/owner-os/commands` — Owner List Commands
- `POST  ` `/api/admin/owner-os/commands` — Owner Create Command
- `POST  ` `/api/admin/owner-os/commands/preview` — Owner Preview
- `GET   ` `/api/admin/owner-os/commands/{command_id}` — Owner Get Command
- `POST  ` `/api/admin/owner-os/commands/{command_id}/approve` — Owner Approve
- `POST  ` `/api/admin/owner-os/commands/{command_id}/cancel` — Owner Cancel
- `POST  ` `/api/admin/owner-os/commands/{command_id}/execute` — Owner Execute
- `POST  ` `/api/admin/owner-os/commands/{command_id}/reassign` — Owner Reassign
- `POST  ` `/api/admin/owner-os/commands/{command_id}/retry` — Owner Retry
- `GET   ` `/api/admin/owner-os/home` — Owner Home
- `GET   ` `/api/admin/owner-os/inventory` — Owner Inventory
- `GET   ` `/api/admin/owner-os/kill-switches` — Owner Kills
- `POST  ` `/api/admin/owner-os/kill-switches` — Owner Set Kill
- `GET   ` `/api/admin/owner-os/maturity` — Owner Agent Maturity
- `GET   ` `/api/admin/owner-os/missions` — Owner Missions
- `POST  ` `/api/admin/owner-os/missions/chat` — Owner Mission Chat
- `GET   ` `/api/admin/owner-os/missions/{mission_id}` — Owner Mission One
- `GET   ` `/api/admin/owner-os/routes` — Owner Route Matrix
- `POST  ` `/api/admin/owner-os/routes/health-test` — Owner Route Health Test
- `GET   ` `/api/admin/owner-os/runtime` — Owner Runtime Status
- `POST  ` `/api/admin/owner-os/runtime/run` — Owner Runtime Run
- `GET   ` `/api/admin/owner-os/tasks` — Owner Tasks
- `GET   ` `/api/admin/owner-os/training` — Owner Training
- `GET   ` `/api/admin/owner-os/workflows` — Owner Workflows
- `GET   ` `/api/admin/owner-os/workflows/{workflow_id}` — Owner Workflow Detail

### Owner OS Coordination Hub  (6)

- `GET   ` `/api/admin/owner-os/coordination-hub/events` — Get Events
- `GET   ` `/api/admin/owner-os/coordination-hub/git` — Get Git
- `POST  ` `/api/admin/owner-os/coordination-hub/mutations/refuse` — Refuse Mutation
- `GET   ` `/api/admin/owner-os/coordination-hub/snapshot` — Get Snapshot
- `POST  ` `/api/admin/owner-os/coordination-hub/tools/{tool_id}/heartbeat` — Tool Heartbeat
- `POST  ` `/api/admin/owner-os/coordination-hub/webhooks/buzz` — Buzz Webhook

### Page Agent  (2)

- `GET   ` `/api/page-agent/config` — Page Agent Config
- `POST  ` `/api/page-agent/v1/chat/completions` — Page Agent Chat

### Platform  (22)

- `GET   ` `/api/bot-command-center/state` — Bot Command Center State
- `GET   ` `/api/ops/hotqueue` — Ops Hot Queue
- `POST  ` `/api/ops/hotqueue/action` — Ops Hot Queue Action
- `GET   ` `/api/ops/revenue-summary` — Ops Revenue Summary
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
- `GET   ` `/app/bot-command-center` — Bot Command Center Page

### Plugin Registry  (4)

- `GET   ` `/api/admin/plugins` — List Plugins
- `POST  ` `/api/admin/plugins/drift` — Check Drift
- `GET   ` `/api/admin/plugins/health` — Plugins Health
- `GET   ` `/api/admin/plugins/{plugin_id}` — Get Plugin

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

### Public  (9)

- `POST  ` `/api/public/ai-demo` — Ai Demo
- `GET   ` `/api/public/audit/questions` — Audit Questions
- `POST  ` `/api/public/audit/score` — Audit Score
- `GET   ` `/api/public/business-types` — Public Business Types
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

### Revenue Sprint  (7)

- `POST  ` `/api/admin/promo/create` — Admin: promo code define karo (launch offer, discount)
- `GET   ` `/api/admin/promo/list` — Admin: promo definitions + applied ledger
- `GET   ` `/api/admin/revenue/offers` — Admin: recent offers (issued/paid/superseded)
- `POST  ` `/api/admin/revenue/offers/issue` — Admin: payable offer issue karo → hosted pay-link (WhatsApp close)
- `GET   ` `/api/public/launch-offer` — Public: active launch offer (pricing-page countdown ka server-side deadline)
- `GET   ` `/api/public/offers/{order_ref}` — Public: order resolve → UPI pay-kit (amount-prefilled intent + QR)
- `POST  ` `/api/public/offers/{order_ref}/promo` — Public: order par promo code lagao → discounted supersede offer

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

### Sales Autopilot  (12)

- `GET   ` `/api/sales-autopilot/attempts` — Attempts
- `POST  ` `/api/sales-autopilot/eligibility/preview` — Eligibility Preview
- `POST  ` `/api/sales-autopilot/inbound/classify` — Inbound Classify
- `POST  ` `/api/sales-autopilot/pay-truth/reconcile` — Pay Truth Reconcile
- `GET   ` `/api/sales-autopilot/pay-truth/unpaid` — Pay Truth Unpaid
- `GET   ` `/api/sales-autopilot/policy` — Get Policy
- `GET   ` `/api/sales-autopilot/prospects` — Prospects
- `POST  ` `/api/sales-autopilot/prospects` — Add Prospect
- `POST  ` `/api/sales-autopilot/refill` — Refill Now
- `POST  ` `/api/sales-autopilot/run-canary` — Run Canary
- `POST  ` `/api/sales-autopilot/seed-estique` — Seed Estique
- `GET   ` `/api/sales-autopilot/summary` — Summary

### Segments  (6)

- `GET   ` `/api/segments` — List Segments
- `POST  ` `/api/segments` — Create Segment
- `GET   ` `/api/segments/_meta` — Segments Meta
- `DELETE` `/api/segments/{segment_id}` — Delete Segment
- `GET   ` `/api/segments/{segment_id}` — Get Segment
- `GET   ` `/api/segments/{segment_id}/preview` — Preview Segment

### Social OAuth  (3)

- `GET   ` `/api/social/oauth/state` — Oauth State All
- `GET   ` `/api/social/oauth/{platform}/callback` — Oauth Callback
- `GET   ` `/api/social/oauth/{platform}/start` — Oauth Start

### Team  (24)

- `GET   ` `/api/platform/team` — Get Team Status
- `POST  ` `/api/platform/team/email-followups/run` — Run Email Followups Now
- `POST  ` `/api/platform/team/email-outreach/run` — Run Email Outreach Now
- `GET   ` `/api/platform/team/email-outreach/runs` — Get Email Outreach Runs
- `GET   ` `/api/platform/team/email-outreach/stats` — Get Email Outreach Stats
- `GET   ` `/api/platform/team/events` — Get Team Events
- `GET   ` `/api/platform/team/growth` — Get Growth
- `POST  ` `/api/platform/team/growth/run` — Run Growth Now
- `GET   ` `/api/platform/team/outreach-activity` — Get Outreach Activity
- `GET   ` `/api/platform/team/outreach-pending-review` — Get Outreach Pending Review
- `POST  ` `/api/platform/team/outreach-review-decision` — Post Outreach Review Decision
- `GET   ` `/api/platform/team/outreach-review-decision-counts` — Get Outreach Review Decision Counts
- `GET   ` `/api/platform/team/outreach-review-decisions` — Get Outreach Review Decisions
- `GET   ` `/api/platform/team/prospects` — Get Prospects
- `POST  ` `/api/platform/team/prospects/run` — Run Prospecting Now
- `POST  ` `/api/platform/team/prospects/{pid}/status` — Set Prospect Status
- `POST  ` `/api/platform/team/reply-triage/run` — Run Reply Triage Now
- `POST  ` `/api/platform/team/run/{member}` — Run Team Member
- `GET   ` `/api/platform/team/scheduler` — Get Scheduler Jobs
- `POST  ` `/api/platform/team/scheduler/run-due` — Scheduler Run Due
- `GET   ` `/api/platform/team/scheduler/runs` — Get Scheduler Runs
- `POST  ` `/api/platform/team/scheduler/{job}/run` — Run Scheduler Job Now
- `POST  ` `/api/platform/team/scheduler/{job}/toggle` — Toggle Scheduler Job
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

### Telephony Webhooks  (4)

- `GET   ` `/api/webhooks/health` — Telephony Health
- `POST  ` `/api/webhooks/vobiz/answer` — Vobiz Answer Webhook
- `POST  ` `/api/webhooks/vobiz/inbound` — Vobiz Inbound Webhook
- `POST  ` `/api/webhooks/vobiz/status` — Vobiz Status Webhook

### UPI Payments  (5)

- `GET   ` `/api/upi/pending` — Admin: pending UPI submissions queue
- `POST  ` `/api/upi/pending/{pid}/approve` — Admin: approve a UPI submission
- `POST  ` `/api/upi/pending/{pid}/bind` — Admin: bind a client to an unbound UPI submission
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

### Web Call (Test Mode)  (4)

- `GET   ` `/api/web-call/config` — Web Call Config
- `GET   ` `/api/web-call/history` — Web Call History
- `POST  ` `/api/web-call/recording` — Upload a web test-call audio recording (mixed mic+bot)
- `GET   ` `/api/web-call/session/{session_id}` — Web Call Session Detail

### Web Test Calls (Admin)  (6)

- `GET   ` `/api/admin/web-calls` — List saved web test-call transcripts (all browsers)
- `GET   ` `/api/admin/web-calls/kpis` — Call-center KPIs (Lekha — Call Analytics)
- `GET   ` `/api/admin/web-calls/proposals` — Self-improve proposals (per-call learn gate)
- `POST  ` `/api/admin/web-calls/proposals/{proposal_id}/promote` — Promote a proposal (GATED)
- `POST  ` `/api/admin/web-calls/proposals/{proposal_id}/reject` — Reject a proposal
- `GET   ` `/api/admin/web-calls/{session_id}` — One web test-call + full transcript

### Webhooks  (2)

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
