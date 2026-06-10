# =============================================================================
# LeadGen AI Voice Agent - Production Environment Template
# =============================================================================
# Copy this file to .env and fill in your values
# For Cloud Run, secrets are injected via Secret Manager
# =============================================================================

# -----------------------------------------------------------------------------
# Core Application Settings
# -----------------------------------------------------------------------------
APP_ENV=production
DEBUG=false
SECRET_KEY=  # Generate: python -c "import secrets; print(secrets.token_urlsafe(48))"

# -----------------------------------------------------------------------------
# Database Configuration (Cloud SQL PostgreSQL)
# -----------------------------------------------------------------------------
# Local development:
# DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/voice_agent
#
# Cloud Run (using Cloud SQL private IP):
# DATABASE_URL=postgresql+asyncpg://leadgen_user:PASSWORD@10.x.x.x:5432/leadgen_ai
DATABASE_URL=

# -----------------------------------------------------------------------------
# Redis Configuration (Memorystore)
# -----------------------------------------------------------------------------
# Local development:
# REDIS_URL=redis://localhost:6379/0
#
# Cloud Run (using Memorystore private IP):
# REDIS_URL=redis://10.x.x.x:6379/0
REDIS_URL=

# -----------------------------------------------------------------------------
# AI/LLM Configuration - Gemini (Primary)
# -----------------------------------------------------------------------------
# Get your API key from: https://aistudio.google.com/apikey
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash
GEMINI_MAX_TOKENS=4096
GEMINI_TEMPERATURE=0.7

# For Vertex AI (enterprise):
# GOOGLE_CLOUD_PROJECT=your-project-id
# VERTEX_AI_LOCATION=asia-south1

# Fallback LLM (optional)
# OPENAI_API_KEY=
# ANTHROPIC_API_KEY=

# -----------------------------------------------------------------------------
# Speech-to-Text (Deepgram) - REQUIRED for voice calls
# -----------------------------------------------------------------------------
# Sign up at: https://console.deepgram.com
# Pricing: ~$0.0043/minute for Nova-2
DEEPGRAM_API_KEY=
DEEPGRAM_MODEL=nova-2
DEEPGRAM_LANGUAGE=en-IN

# -----------------------------------------------------------------------------
# Text-to-Speech Configuration
# -----------------------------------------------------------------------------
# Option 1: Edge TTS (FREE - Default)
TTS_PROVIDER=edge
EDGE_TTS_VOICE=en-IN-NeerjaNeural

# Option 2: ElevenLabs (Premium voice cloning)
# TTS_PROVIDER=elevenlabs
# ELEVENLABS_API_KEY=
# ELEVENLABS_VOICE_ID=

# Option 3: Azure Cognitive Services
# TTS_PROVIDER=azure
# AZURE_SPEECH_KEY=
# AZURE_SPEECH_REGION=centralindia

# -----------------------------------------------------------------------------
# Telephony - Twilio Configuration - REQUIRED for voice calls
# -----------------------------------------------------------------------------
# Sign up at: https://console.twilio.com
# Get your credentials from: https://console.twilio.com/project/settings
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=  # Format: +1234567890

# Twilio Webhook URL (set after Cloud Run deployment)
# TWILIO_WEBHOOK_URL=https://your-service-xxxxx-el.a.run.app/api/webhooks/twilio

# -----------------------------------------------------------------------------
# Telephony - Exotel Configuration (India-focused alternative)
# -----------------------------------------------------------------------------
# Sign up at: https://exotel.com
# EXOTEL_SID=
# EXOTEL_TOKEN=
# EXOTEL_PHONE_NUMBER=

# -----------------------------------------------------------------------------
# Payment Gateway - Stripe (International)
# -----------------------------------------------------------------------------
# Sign up at: https://dashboard.stripe.com
# Get API keys: https://dashboard.stripe.com/apikeys
STRIPE_SECRET_KEY=  # sk_live_... or sk_test_...
STRIPE_PUBLISHABLE_KEY=  # pk_live_... or pk_test_...
STRIPE_WEBHOOK_SECRET=  # whsec_...

# -----------------------------------------------------------------------------
# Payment Gateway - Razorpay (India)
# -----------------------------------------------------------------------------
# Sign up at: https://dashboard.razorpay.com
# Get API keys: https://dashboard.razorpay.com/app/keys
RAZORPAY_KEY_ID=  # rzp_live_... or rzp_test_...
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=

# -----------------------------------------------------------------------------
# CRM Integrations
# -----------------------------------------------------------------------------
# HubSpot - https://app.hubspot.com/api-key
HUBSPOT_API_KEY=
HUBSPOT_PORTAL_ID=

# Zoho CRM - https://api-console.zoho.com
ZOHO_CLIENT_ID=
ZOHO_CLIENT_SECRET=
ZOHO_REFRESH_TOKEN=

# Google Sheets (for lead export)
GOOGLE_SHEETS_CREDENTIALS_FILE=  # Path to service account JSON

# -----------------------------------------------------------------------------
# WhatsApp Business API
# -----------------------------------------------------------------------------
# Option 1: Twilio WhatsApp
# WHATSAPP_PROVIDER=twilio
# (Uses TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN above)

# Option 2: Meta Business API
# WHATSAPP_PROVIDER=meta
# META_WHATSAPP_TOKEN=
# META_WHATSAPP_PHONE_ID=

# -----------------------------------------------------------------------------
# Email Configuration
# -----------------------------------------------------------------------------
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=  # Use App Password for Gmail
SMTP_FROM_EMAIL=noreply@yourdomain.com

# -----------------------------------------------------------------------------
# Security & Rate Limiting
# -----------------------------------------------------------------------------
JWT_SECRET_KEY=  # Generate: python -c "import secrets; print(secrets.token_urlsafe(32))"
JWT_ALGORITHM=HS256
JWT_EXPIRY_HOURS=24

# Rate limits (requests per minute)
RATE_LIMIT_PUBLIC=60
RATE_LIMIT_AUTHENTICATED=300
RATE_LIMIT_ADMIN=1000

# -----------------------------------------------------------------------------
# Monitoring & Logging
# -----------------------------------------------------------------------------
LOG_LEVEL=INFO
LOG_FORMAT=json

# Sentry (optional - error tracking)
# SENTRY_DSN=https://xxx@sentry.io/xxx

# -----------------------------------------------------------------------------
# Multi-Tenancy Configuration
# -----------------------------------------------------------------------------
MAX_TENANTS=1000
MAX_USERS_PER_TENANT=50
MAX_LEADS_FREE_TIER=100
MAX_CALLS_FREE_TIER=50

# -----------------------------------------------------------------------------
# Voice Agent Configuration
# -----------------------------------------------------------------------------
# Call settings
MAX_CALL_DURATION_SECONDS=300
CALL_RECORDING_ENABLED=true
BARGE_IN_ENABLED=true
SILENCE_TIMEOUT_MS=2000

# Answering machine detection
AMD_ENABLED=true
AMD_TIMEOUT_MS=3000

# Latency budgets (ms)
ASR_LATENCY_BUDGET_MS=500
TTS_LATENCY_BUDGET_MS=300
LLM_LATENCY_BUDGET_MS=2000

# -----------------------------------------------------------------------------
# Lead Scraper Configuration
# -----------------------------------------------------------------------------
SCRAPER_CONCURRENCY=5
SCRAPER_DELAY_MS=2000
DND_CHECK_ENABLED=true

# -----------------------------------------------------------------------------
# Celery Worker Configuration
# -----------------------------------------------------------------------------
CELERY_BROKER_URL=${REDIS_URL}
CELERY_RESULT_BACKEND=${REDIS_URL}
CELERY_CONCURRENCY=4

# -----------------------------------------------------------------------------
# GCP-Specific Settings (for Cloud Run)
# -----------------------------------------------------------------------------
GOOGLE_CLOUD_PROJECT=
GCP_REGION=asia-south1

# Cloud SQL connection (alternative to DATABASE_URL for Cloud Run)
# CLOUD_SQL_CONNECTION_NAME=project:region:instance

# =============================================================================
# QUICK START CHECKLIST
# =============================================================================
# □ Set SECRET_KEY and JWT_SECRET_KEY (generate random values)
# □ Set DATABASE_URL (PostgreSQL connection string)
# □ Set REDIS_URL (Redis connection string)
# □ Set GEMINI_API_KEY (from Google AI Studio)
# □ Set TWILIO_* credentials (for voice calls)
# □ Set DEEPGRAM_API_KEY (for speech-to-text)
# □ Set STRIPE_* or RAZORPAY_* (for payments)
# □ Configure TTS provider (Edge TTS is free default)
# =============================================================================
