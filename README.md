# 🤖 LeadGen AI - Multi-Tier B2B Lead Generation Platform

> **AI-Powered Voice Agent Platform for Automated Lead Generation**
> 
> A fully automated, multi-tenant SaaS platform that generates B2B leads using AI voice agents.

---

## 🎯 Business Model

### Two-Tier Automation System

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        TIER 1: PLATFORM LEVEL                                │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  YOUR COMPANY uses the AI to find B2B clients (businesses that     │   │
│  │  need lead generation services)                                      │   │
│  │                                                                       │   │
│  │  Scrape → Call → Pitch Service → Convert to Client                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        TIER 2: CLIENT LEVEL                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  EACH CLIENT gets their own AI voice agent to generate leads       │   │
│  │  for THEIR business                                                  │   │
│  │                                                                       │   │
│  │  Client's Niche → Scrape → Call → Book Appointments for Client      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Automation Flow

```
    ┌────────────────────────────────────────────────────────────────────────┐
    │                    24/7 AUTOMATED OPERATION                            │
    │                                                                        │
    │   1. Platform scrapes potential B2B clients                           │
    │      (Digital agencies, Solar companies, Real estate, etc.)           │
    │                               ↓                                        │
    │   2. AI calls businesses to pitch lead gen service                    │
    │      (Using Hinglish/English scripts)                                 │
    │                               ↓                                        │
    │   3. Interested lead? → AUTO-ONBOARD as trial client                  │
    │      (7-day free trial, 100 calls)                                    │
    │                               ↓                                        │
    │   4. Client's own AI agent starts generating THEIR leads              │
    │      (Scrape → Call → Qualify → Book appointments)                    │
    │                               ↓                                        │
    │   5. Nurturing sequence converts trial → paid subscription            │
    │      (Automated WhatsApp follow-ups)                                  │
    │                               ↓                                        │
    │   6. Repeat forever with minimal human intervention                   │
    │                                                                        │
    └────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
leadgenrationaivoiceagent/
├── app/
│   ├── main.py                      # FastAPI entry point
│   ├── config.py                    # Application configuration
│   │
│   ├── platform/                    # 🌟 Multi-tenant platform core
│   │   ├── __init__.py             # Platform config, tenant types
│   │   ├── orchestrator.py         # 24/7 master automation controller
│   │   ├── tenant_manager.py       # Manage all client tenants
│   │   ├── client_journey.py       # Lead → Client conversion flow
│   │   └── sales_scripts.py        # Scripts for selling YOUR service
│   │
│   ├── voice_agent/                 # 🎤 AI Voice Agent Core
│   │   ├── agent.py                # Main voice agent class
│   │   ├── llm_brain.py            # LLM integration (Gemini/GPT/Claude)
│   │   ├── stt_handler.py          # Speech-to-text (Deepgram/Google)
│   │   ├── tts_handler.py          # Text-to-speech (Edge/ElevenLabs/Azure)
│   │   ├── intent_detector.py      # Detect caller intent
│   │   └── conversation.py         # Manage conversation state
│   │
│   ├── lead_scraper/                # 🔍 Lead Scraping
│   │   ├── google_maps.py          # Google Maps scraper
│   │   ├── indiamart.py            # IndiaMart scraper
│   │   ├── justdial.py             # JustDial scraper
│   │   ├── linkedin.py             # LinkedIn scraper
│   │   └── scraper_manager.py      # Orchestrate all scrapers
│   │
│   ├── telephony/                   # 📞 Telephony Integration
│   │   ├── twilio_handler.py       # Twilio for international
│   │   ├── exotel_handler.py       # Exotel for India
│   │   ├── call_manager.py         # Manage concurrent calls
│   │   └── webhooks.py             # Handle call events
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
| LLM | Gemini 1.5 Flash | GPT-4o, Claude 3 |
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
| AI/LLM | Gemini 1.5 Flash (default) |
| Voice | Deepgram STT + Edge TTS |
| Telephony | Twilio + Exotel |
| Messaging | WhatsApp Business API |
| Containers | Docker + Docker Compose |

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
