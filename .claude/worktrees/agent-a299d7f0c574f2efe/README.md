# 🚀 LeadGen AI - B2B Intelligence Platform

> **AI-Powered Business Data & Intelligence Platform**
> 
> A zero-cost B2B data platform that provides company search, enrichment, and market intelligence APIs.
>
> **Live in production**: https://leadsgenai.in

---

## 🎯 Business Model

### B2B Intelligence Platform (Zero Per-Interaction Cost)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     B2B INTELLIGENCE PLATFORM                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                    │
│   │   SCRAPE    │ →  │   ENRICH    │ →  │    SELL     │                    │
│   │   Data      │    │   & Score   │    │   Access    │                    │
│   └─────────────┘    └─────────────┘    └─────────────┘                    │
│                                                                              │
│   Cost: ₹0.10/lead    Cost: ₹0/lead     Revenue: ₹5+/lookup                │
│   (one-time)          (AI scoring)       (per customer)                     │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   📊 REVENUE STREAMS:                                                        │
│   • Company Search API (subscription)                                        │
│   • Data Enrichment (per-credit)                                            │
│   • Market Reports (per-report)                                             │
│   • Bulk Export (per-record)                                                │
│                                                                              │
│   💰 MARGIN: 95%+ (scrape once, sell 100x)                                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Platform Features

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         PLATFORM CAPABILITIES                               │
│                                                                             │
│   🔍 COMPANY SEARCH API                                                     │
│      • Search across 25+ niches                                            │
│      • Filter by city, rating, verification                                │
│      • FREE searches (credits on export/enrich)                            │
│                                                                             │
│   📈 DATA ENRICHMENT                                                        │
│      • Full contact details (phone, email)                                 │
│      • Company metadata (size, industry)                                   │
│      • 2 credits per enrichment                                            │
│                                                                             │
│   📊 MARKET REPORTS                                                         │
│      • Industry analysis                                                   │
│      • Competitive landscape                                               │
│      • AI-generated insights                                               │
│                                                                             │
│   🔑 DEVELOPER API                                                          │
│      • REST API with API key auth                                          │
│      • Webhooks for real-time updates                                      │
│      • CRM integrations (HubSpot, Zoho)                                    │
│                                                                             │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
leadgenrationaivoiceagent/
├── app/
│   ├── main.py                      # FastAPI entry point
│   ├── config.py                    # Application configuration
│   │
│   ├── api/                         # 🌐 API Endpoints
│   │   ├── data.py                 # 🌟 Data Intelligence API
│   │   ├── leads.py                # Lead management
│   │   ├── campaigns.py            # Campaign management
│   │   └── analytics.py            # Analytics endpoints
│   │
│   ├── services/                    # 💼 Business Logic
│   │   └── data_service.py         # Data platform service
│   │
│   ├── models/                      # 📦 Database Models
│   │   ├── lead.py                 # Lead/Company model
│   │   ├── data_credits.py         # Credits & API keys
│   │   └── payment.py              # Billing models
│   │
│   ├── lead_scraper/                # 🔍 Lead Scraping
│   │   ├── google_maps.py          # Google Maps scraper
│   │   ├── indiamart.py            # IndiaMart scraper
│   │   ├── justdial.py             # JustDial scraper
│   │   ├── linkedin.py             # LinkedIn scraper
│   │   └── scraper_manager.py      # Orchestrate all scrapers
│   │
│   ├── integrations/                # 🔗 Third-party Integrations
│   │   ├── whatsapp_handler.py     # WhatsApp Business API
│   │   ├── email_sender.py         # Email notifications
│   │   ├── google_sheets.py        # Google Sheets CRM
│   │   └── hubspot.py              # HubSpot CRM
│   │
│   ├── automation/                  # ⚡ Automation Engine
│   │   ├── campaign_manager.py     # Manage calling campaigns
│   │   └── scheduler.py            # Schedule automated tasks
│   │
│   ├── scripts/                     # 📜 Call Scripts
│   │   ├── script_loader.py        # Load niche-specific scripts
│   │   └── niches/                 # Industry scripts
│   │       ├── solar.py
│   │       ├── real_estate.py
│   │       ├── digital_marketing.py
│   │       └── ...
│   │
│   ├── api/                         # 🌐 REST API
│   │   ├── platform.py             # Platform management endpoints
│   │   ├── leads.py                # Lead CRUD operations
│   │   ├── campaigns.py            # Campaign management
│   │   └── analytics.py            # Analytics & reporting
│   │
│   ├── models/                      # 📊 Database Models
│   │   ├── lead.py
│   │   ├── campaign.py
│   │   ├── call_log.py
│   │   └── client.py
│   │
│   ├── tasks/                       # 📋 Background Tasks (Celery)
│   │   ├── scraping.py
│   │   ├── calling.py
│   │   ├── reporting.py
│   │   └── sync.py
│   │
│   └── utils/                       # 🛠️ Utilities
│       ├── logger.py
│       ├── phone_validator.py
│       └── dnd_checker.py
│
├── tests/                           # 🧪 Test Suite
├── docker-compose.yml              # Docker configuration
├── Dockerfile                      # Application container
├── requirements.txt                # Python dependencies
└── .env.example                    # Environment variables template
```

---

## 🚀 Quick Start

### 1. Clone & Setup

```bash
cd leadgenrationaivoiceagent

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

Create `.env` file from `.env.example`:

```bash
# Required API Keys
GEMINI_API_KEY=your_gemini_key
DEEPGRAM_API_KEY=your_deepgram_key
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_PHONE_NUMBER=+1234567890

# Optional (for full features)
EXOTEL_SID=your_exotel_sid          # For India calls
WHATSAPP_BUSINESS_TOKEN=your_token   # For WhatsApp
HUBSPOT_API_KEY=your_hubspot_key     # For CRM

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/voice_agent
REDIS_URL=redis://localhost:6379/0

# Platform Settings
AUTO_START_PLATFORM=true
PLATFORM_COMPANY_NAME=LeadGen AI Solutions
```

### 3. Start the Platform

```bash
# Start with Docker (recommended)
docker-compose up -d

# Or run directly
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Access the Platform

- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health
- **Platform Stats**: http://localhost:8000/api/platform/stats

---

## 🧠 Three-Brain Architecture (Vertex AI Powered)

The platform uses a revolutionary **Three-Brain System** for self-improving AI:

```
┌─────────────────────────────────────────────────────────────────────┐
│                     BRAIN ORCHESTRATOR                               │
├─────────────────┬─────────────────────┬─────────────────────────────┤
│   BRAIN #1      │     BRAIN #2        │        BRAIN #3             │
│  Sub-Agent      │   Voice Agent       │      Production             │
│    Brain        │      Brain          │        Brain                │
├─────────────────┼─────────────────────┼─────────────────────────────┤
│ 13 dev agents   │ Real-time calls     │ Health & growth             │
│ for coding      │ with lead gen       │ optimization                │
└─────────────────┴─────────────────────┴─────────────────────────────┘
```

| Brain | Purpose |
|-------|---------|
| **Brain #1** | Powers 13 specialized dev sub-agents (Voice AI, Leads, ML, Billing, Security, etc.) |
| **Brain #2** | Handles real-time voice calls with industry-specific scripts and intent detection |
| **Brain #3** | Monitors health, provides scaling recommendations, and growth insights |

```python
from app.ml import get_brain_orchestrator

# Quick health check
health = await get_brain_orchestrator().route_request("health_check", {})

# Production readiness score
readiness = await get_brain_orchestrator().route_request("production_readiness", {})
```

📖 **Architecture**: [docs/Architecture_Research_RAG_Agents_MCP.md](docs/Architecture_Research_RAG_Agents_MCP.md) · **Research index**: `docs/Competitor_Top20_Feature_Gap_2026.md` (archived: `docs/legacy/THREE_BRAIN_ARCHITECTURE.md`)

---

## ⚙️ Platform Controls

### Start/Stop Automation

```bash
# Start 24/7 automation
POST /api/platform/start

# Stop automation
POST /api/platform/stop

# Get platform status
GET /api/platform/stats
```

### Tenant Management

```bash
# List all tenants/clients
GET /api/platform/tenants

# Get tenant details
GET /api/platform/tenants/{tenant_id}

# Manually onboard a client
POST /api/platform/tenants
{
    "company_name": "ABC Solar Solutions",
    "contact_name": "Rahul Sharma",
    "contact_phone": "+919876543210",
    "contact_email": "rahul@abcsolar.com",
    "industry": "solar",
    "target_niches": ["residential_solar", "commercial_solar"],
    "target_cities": ["Mumbai", "Pune", "Nagpur"]
}

# Upgrade tenant subscription
POST /api/platform/tenants/{tenant_id}/upgrade
{
    "tier": "growth"
}

# Pause/Resume tenant automation
POST /api/platform/tenants/{tenant_id}/pause
POST /api/platform/tenants/{tenant_id}/resume
```

---

## 💰 Subscription Tiers

| Tier | Price | Calls/Month | Features |
|------|-------|-------------|----------|
| **Trial** | FREE (7 days) | 100 | Full features, auto-onboard |
| **Starter** | ₹15,000/mo | 500 | Basic automation |
| **Growth** | ₹25,000/mo | 2,000 | Priority support, advanced analytics |
| **Enterprise** | ₹50,000/mo | Unlimited | Custom scripts, dedicated account |

---

## 🔄 Automation Workflows

### Platform Lead Generation (Tier 1)

1. **9:00 AM** - Scrape potential B2B clients from:
   - Google Maps (Digital agencies, Real estate, Solar, etc.)
   - IndiaMart (B2B manufacturers, suppliers)
   - JustDial (Service businesses)

2. **10:00 AM - 6:00 PM** - AI calls leads:
   - Pitches your lead generation service
   - Handles objections automatically
   - Books demo appointments

3. **Interested leads** → Auto-onboarded as trial clients

4. **Daily Reports** - WhatsApp summary of new clients, calls made, conversions

### Client Lead Generation (Tier 2)

Each client tenant automatically gets:

1. **Lead scraping** for their specific niche/industry
2. **AI calling** with customized scripts
3. **WhatsApp alerts** for hot leads
4. **CRM sync** (HubSpot, Google Sheets)
5. **Appointment booking** in their calendar

---

## 🎤 Voice Agent Features

### Supported Languages
- Hindi-English (Hinglish) - Primary
- Pure English
- Pure Hindi

### AI Models
| Purpose | Default | Alternatives |
|---------|---------|--------------|
| LLM | Gemini 2.5 Flash Lite | Other Gemini models, GPT-4o, Claude |
| TTS | Edge TTS (FREE) | ElevenLabs, Azure |
| STT | Deepgram | Google Cloud Speech |

### Call Flow
```
1. Greeting → Permission Ask
2. Value Proposition
3. Qualification Questions
4. Objection Handling (AI-powered)
5. Appointment Booking / Callback Scheduling
6. Follow-up via WhatsApp
```

---

## 📊 Monitoring & Analytics

### Platform Dashboard
- Total tenants & active campaigns
- Calls made today/this month
- Conversion rates
- Revenue metrics

### Per-Tenant Metrics
- Leads scraped
- Calls completed
- Appointments booked
- Hot lead alerts

### Real-time Alerts
- WhatsApp notifications for:
  - Hot leads (interested prospects)
  - Appointments booked
  - Trial expirations
  - Usage warnings

---

## 🔐 Compliance

- **DND Registry Check** - Respects Do-Not-Disturb list (India)
- **Working Hours Only** - 9 AM - 6 PM IST
- **Call Recording Consent** - Built-in disclosure
- **Data Privacy** - GDPR-ready architecture

---

## 🛠️ Technology Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI + Python 3.10+ |
| Database | PostgreSQL + Redis |
| Task Queue | Celery + Redis |
| AI/LLM | Gemini 2.5 Flash Lite (default) |
| Agent Orchestration | LangGraph supervisor (`/api/agents/run`) |
| RAG / Vector Store | Qdrant (payload-partitioned) + fastembed multilingual-e5-small |
| MCP | fastapi_mcp — platform exposed as MCP tools at `/mcp` |
| Voice | Deepgram STT + Edge TTS |
| Telephony | Twilio + Exotel |
| Messaging | WhatsApp Business API |
| Containers | Docker + Docker Compose |

### Agentic Stack (2026)

Live in production at **https://leadsgenai.in**:

- **25 research-finalized niches** (S/A/B tiers, B2C/B2B target types, per-niche pricing bands) in `app/niches.py`, plus a **custom niches API** — `POST /api/data/niches` adds a new niche at runtime with flows, knowledge base, and provisioning auto-wired (the 25 built-ins are delete-protected).
- **Per-client 2-agent auto-provisioning** — every new client (`POST /api/platform/clients`) automatically gets a DATA agent (business profile + niche knowledge, namespace `client:<id>`) and a LEADS agent (end-customer outreach calling per the niche's target type).
- **Qdrant payload-partitioned RAG** — single `kb_main` collection partitioned by namespace, fastembed `multilingual-e5-small` embeddings (Hinglish-capable), with fallback chain Qdrant → Chroma → keyword.
- **LangGraph supervisor** — routes requests to data/leads agent nodes with SQLite checkpointing; run via `POST /api/agents/run`, status at `GET /api/agents/status`.
- **MCP server** — Platform/Data/Agents endpoints exposed as MCP tools at `/mcp` via fastapi_mcp, so AI clients can administer the platform directly.

---

## 📞 Support

For enterprise deployments and custom integrations, contact:
- Email: support@leadgenai.com
- WhatsApp: Configure `SUPPORT_WHATSAPP_NUMBER` in your `.env` file

---

## 📜 License

Proprietary - All Rights Reserved

---

**Built with ❤️ for Indian B2B businesses**
