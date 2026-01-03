# AuraLeads AI Voice Agent - Deployment Guide

## 🚀 Production Deployment to Google Cloud Platform

This guide walks you through deploying the AuraLeads AI Voice Agent platform to production on Google Cloud Platform.

---

## Prerequisites

1. **Google Cloud Account** with billing enabled
2. **gcloud CLI** installed and authenticated
3. **Docker** installed locally
4. **Terraform** (optional, for infrastructure as code)
5. **Domain name** configured with DNS access

---

## Quick Start (One-Command Deploy)

```bash
# Set your GCP project
export GCP_PROJECT_ID="your-project-id"
export GCP_REGION="asia-south1"

# Deploy
bash scripts/deploy_production.sh
```

---

## Step-by-Step Deployment

### Step 1: Configure GCP Project

```bash
# Authenticate with GCP
gcloud auth login

# Set project
gcloud config set project $GCP_PROJECT_ID

# Enable required APIs
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  storage.googleapis.com \
  aiplatform.googleapis.com
```

### Step 2: Set Up Secrets

```bash
# Create secrets (replace with your actual values)
echo -n "your-jwt-secret" | gcloud secrets create jwt-secret --data-file=-
echo -n "your-db-url" | gcloud secrets create database-url --data-file=-
echo -n "your-redis-url" | gcloud secrets create redis-url --data-file=-
echo -n "your-gemini-key" | gcloud secrets create gemini-api-key --data-file=-
echo -n "your-twilio-token" | gcloud secrets create twilio-auth-token --data-file=-

# Grant Cloud Run access to secrets
gcloud secrets add-iam-policy-binding jwt-secret \
  --member="serviceAccount:$GCP_PROJECT_ID@appspot.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### Step 3: Set Up Cloud SQL (PostgreSQL)

```bash
# Create instance
gcloud sql instances create auraleads-db \
  --database-version=POSTGRES_15 \
  --tier=db-custom-2-4096 \
  --region=$GCP_REGION \
  --storage-auto-increase \
  --backup-start-time=02:00

# Create database
gcloud sql databases create auraleads --instance=auraleads-db

# Create user
gcloud sql users create auraleads_user \
  --instance=auraleads-db \
  --password=your-secure-password
```

### Step 4: Set Up Redis (Memorystore)

```bash
# Create Redis instance
gcloud redis instances create auraleads-redis \
  --size=1 \
  --region=$GCP_REGION \
  --redis-version=redis_7_0 \
  --tier=standard

# Get Redis IP
gcloud redis instances describe auraleads-redis --region=$GCP_REGION --format="value(host)"
```

### Step 5: Set Up Cloud Storage

```bash
# Create buckets
gsutil mb -l $GCP_REGION gs://$GCP_PROJECT_ID-profile-pictures
gsutil mb -l $GCP_REGION gs://$GCP_PROJECT_ID-voice-recordings
gsutil mb -l $GCP_REGION gs://$GCP_PROJECT_ID-ml-models

# Set public access for profile pictures
gsutil iam ch allUsers:objectViewer gs://$GCP_PROJECT_ID-profile-pictures
```

### Step 6: Build and Push Container

```bash
# Build using Cloud Build
gcloud builds submit \
  --config=cloudbuild.yaml \
  --substitutions=_VERSION=$(date +%Y%m%d%H%M%S)

# Or build locally
docker build -t gcr.io/$GCP_PROJECT_ID/auraleads-api:latest -f Dockerfile.production .
docker push gcr.io/$GCP_PROJECT_ID/auraleads-api:latest
```

### Step 7: Deploy to Cloud Run

```bash
gcloud run deploy auraleads-api \
  --image gcr.io/$GCP_PROJECT_ID/auraleads-api:latest \
  --region $GCP_REGION \
  --platform managed \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --min-instances 1 \
  --max-instances 20 \
  --timeout 300 \
  --concurrency 80 \
  --set-env-vars="APP_ENV=production" \
  --set-env-vars="GOOGLE_CLOUD_PROJECT_ID=$GCP_PROJECT_ID" \
  --set-secrets="DATABASE_URL=database-url:latest" \
  --set-secrets="REDIS_URL=redis-url:latest" \
  --set-secrets="JWT_SECRET_KEY=jwt-secret:latest" \
  --add-cloudsql-instances=$GCP_PROJECT_ID:$GCP_REGION:auraleads-db
```

### Step 8: Run Database Migrations

```bash
# Get Cloud Run URL
SERVICE_URL=$(gcloud run services describe auraleads-api --region $GCP_REGION --format="value(status.url)")

# Run migrations via API or connect directly
# Option 1: Add migration to startup
# Option 2: Run locally with Cloud SQL Proxy
cloud_sql_proxy -instances=$GCP_PROJECT_ID:$GCP_REGION:auraleads-db=tcp:5432 &
alembic upgrade head
```

### Step 9: Configure Custom Domain

```bash
# Map custom domain
gcloud run domain-mappings create \
  --service auraleads-api \
  --domain api.auraleads.ai \
  --region $GCP_REGION

# Update DNS with provided records
```

### Step 10: Set Up Monitoring

```bash
# Create uptime check
gcloud monitoring uptime-check-configs create auraleads-health \
  --display-name="AuraLeads API Health" \
  --http-check-path="/health" \
  --hostname="api.auraleads.ai"

# Create alert policy
gcloud alpha monitoring policies create \
  --display-name="AuraLeads High Error Rate" \
  --condition-display-name="Error rate > 1%" \
  --condition-filter='metric.type="run.googleapis.com/request_count" AND resource.type="cloud_run_revision" AND metric.labels.response_code_class="5xx"'
```

---

## Infrastructure as Code (Terraform)

For repeatable infrastructure:

```bash
cd infrastructure/terraform

# Initialize
terraform init

# Plan
terraform plan -var="project_id=$GCP_PROJECT_ID" -out=tfplan

# Apply
terraform apply tfplan
```

---

## Environment Variables Reference

| Variable | Description | Required |
|----------|-------------|----------|
| `APP_ENV` | Environment (production/development) | Yes |
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `REDIS_URL` | Redis connection string | Yes |
| `JWT_SECRET_KEY` | JWT signing key | Yes |
| `GOOGLE_CLOUD_PROJECT_ID` | GCP project ID | Yes |
| `GEMINI_API_KEY` | Gemini API key | Yes |
| `TWILIO_ACCOUNT_SID` | Twilio SID | For calls |
| `TWILIO_AUTH_TOKEN` | Twilio token | For calls |
| `ELEVENLABS_API_KEY` | ElevenLabs key | For TTS |
| `DEEPGRAM_API_KEY` | Deepgram key | For STT |

---

## Webhooks Configuration

### Twilio Webhooks

Configure in Twilio Console:
- **Voice URL**: `https://api.auraleads.ai/api/webhooks/twilio/voice`
- **Status Callback**: `https://api.auraleads.ai/api/webhooks/twilio/status`

### WhatsApp Webhooks

Configure in Meta Business:
- **Callback URL**: `https://api.auraleads.ai/api/webhooks/whatsapp`
- **Verify Token**: Your configured token

---

## Scaling Configuration

### Auto-Scaling Settings

```yaml
Min instances: 1  # Keep warm for low latency
Max instances: 20  # Scale for peak load
Concurrency: 80  # Requests per container
CPU: 2  # For voice processing
Memory: 2Gi  # For ML models
```

### Cost Optimization

1. **Use committed use discounts** for Cloud SQL
2. **Enable Cloud Run CPU allocation** only during requests
3. **Set up budget alerts** at 50%, 80%, 100%
4. **Use preemptible VMs** for batch processing

---

## Monitoring & Alerting

### Key Metrics to Monitor

1. **Response Time**: < 500ms p95
2. **Error Rate**: < 1%
3. **Call Success Rate**: > 95%
4. **Database Connections**: < 80% capacity
5. **Redis Memory**: < 70%

### Dashboards

Import the included dashboard:
```bash
gcloud monitoring dashboards create --config-from-file=infrastructure/monitoring/dashboard.json
```

---

## Troubleshooting

### Common Issues

1. **Cold Start Latency**
   - Increase min instances
   - Use CPU always allocated

2. **Database Timeouts**
   - Check connection pool size
   - Verify VPC connector

3. **Secret Access Denied**
   - Grant `secretmanager.secretAccessor` role

4. **Memory Errors**
   - Increase memory allocation
   - Optimize ML model loading

### Viewing Logs

```bash
# Stream logs
gcloud run services logs tail auraleads-api --region $GCP_REGION

# Search logs
gcloud logging read "resource.type=cloud_run_revision AND severity>=ERROR" --limit=50
```

---

## Security Checklist

- [ ] All secrets in Secret Manager (not env vars)
- [ ] HTTPS only (enforced by Cloud Run)
- [ ] Rate limiting enabled
- [ ] SQL injection protection
- [ ] CORS configured for your domains
- [ ] Authentication on admin endpoints
- [ ] Audit logging enabled
- [ ] Vulnerability scanning in CI/CD

---

## Support

- **Documentation**: https://docs.auraleads.ai
- **Email**: support@auraleads.ai
- **Status Page**: https://status.auraleads.ai
