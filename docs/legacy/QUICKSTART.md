# 🚀 LeadGen AI Voice Agent - Quick Start Guide

This guide will get you from zero to deployed in under 30 minutes.

## Prerequisites

- Python 3.11+
- Docker Desktop
- Google Cloud SDK (`gcloud`)
- A GCP account with billing enabled

---

## Step 1: Get Your API Keys (10 min)

### Required APIs

| Service | Get Key | Cost |
|---------|---------|------|
| **Gemini** | [Google AI Studio](https://aistudio.google.com/apikey) | Free tier: 60 req/min |
| **Deepgram** | [Deepgram Console](https://console.deepgram.com/) | Free tier: $200 credit |
| **Twilio** | [Twilio Console](https://console.twilio.com/) | Pay-as-you-go |

### Optional APIs (for enhanced features)

| Service | Get Key | Purpose |
|---------|---------|---------|
| **ElevenLabs** | [elevenlabs.io](https://elevenlabs.io/) | Premium voices |
| **HubSpot** | [HubSpot Developer](https://developers.hubspot.com/) | CRM integration |
| **Sentry** | [sentry.io](https://sentry.io/) | Error monitoring |

---

## Step 2: Configure Environment (2 min)

```powershell
# Copy example and edit
copy .env.example .env

# Or update your existing .env with the keys you obtained:
```

Edit `.env` and fill in these **required** values:

```env
# REQUIRED - Get from Google AI Studio
GEMINI_API_KEY=AIza...your-key-here

# REQUIRED - Get from Deepgram Console  
DEEPGRAM_API_KEY=your-deepgram-key

# REQUIRED - Get from Twilio Console
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_PHONE_NUMBER=+1234567890
```

---

## Step 3: Set Up GCP Project (5 min)

### Option A: Automated Setup (Recommended)

```powershell
# Login to GCP
gcloud auth login

# Run automated setup
python scripts/setup_gcp.py --project-id your-project-id
```

### Option B: Manual Setup

```powershell
# 1. Login
gcloud auth login

# 2. Create project (or use existing)
gcloud projects create leadgen-ai-prod --name="LeadGen AI Voice Agent"

# 3. Set as default
gcloud config set project leadgen-ai-prod

# 4. Enable required APIs
gcloud services enable `
    run.googleapis.com `
    secretmanager.googleapis.com `
    cloudbuild.googleapis.com `
    artifactregistry.googleapis.com `
    sqladmin.googleapis.com `
    redis.googleapis.com

# 5. Create Artifact Registry
gcloud artifacts repositories create leadgen-repo `
    --repository-format=docker `
    --location=asia-south1
```

---

## Step 4: Configure Secrets (3 min)

```powershell
# Interactive mode - will prompt for each secret
python scripts/setup_secrets.py --project-id your-project-id --env production --interactive

# Or from .env file
python scripts/setup_secrets.py --project-id your-project-id --env production --from-env .env
```

---

## Step 5: Deploy (5 min)

### Option A: One-Command Deploy

```powershell
./scripts/deploy.sh production
```

### Option B: Via Cloud Build

```powershell
gcloud builds submit --config=cloudbuild.yaml
```

### Option C: Via GitHub Actions (CI/CD)

Just push to `main` branch - deployment is automatic:

```powershell
git push origin main
```

---

## Step 6: Verify Deployment

```powershell
# Get service URL
$SERVICE_URL = gcloud run services describe leadgen-ai-agent --region=asia-south1 --format="value(status.url)"

# Health check
Invoke-RestMethod -Uri "$SERVICE_URL/api/health"

# Should return:
# status: healthy
# version: x.x.x
# uptime: ...
```

---

## Local Development

### Run Locally

```powershell
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Run server
uvicorn app.main:app --reload --port 8000
```

### Run with Docker

```powershell
docker-compose up -d
```

### Run Tests

```powershell
pytest tests/ -v
```

---

## Quick Reference Commands

| Command | Purpose |
|---------|---------|
| `make dev` | Start local development server |
| `make test` | Run all tests |
| `make validate` | Pre-deployment validation |
| `make deploy-full` | Full production deployment |
| `make logs` | View production logs |

---

## Troubleshooting

### "GEMINI_API_KEY not set"
Get a key from [Google AI Studio](https://aistudio.google.com/apikey)

### "Database connection failed"
For local dev, SQLite is used. For production, ensure PostgreSQL is configured.

### "gcloud: command not found"
Install [Google Cloud SDK](https://cloud.google.com/sdk/docs/install)

### CI/CD failing
Check GitHub Actions logs and ensure all secrets are set in repository settings.

---

## Support

- 📖 [Full Documentation](./README.md)
- 🐛 [Report Issues](https://github.com/sumitrevolt/leadgenrationaivoiceagent/issues)
- 📊 [Production Checklist](./PRODUCTION_CHECKLIST.md)
