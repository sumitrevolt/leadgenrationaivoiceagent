#!/usr/bin/env bash
# =============================================================================
# AuraLeads AI Voice Agent - Production Deployment Script
# Deploy to Google Cloud Run with full production configuration
# =============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-your-project-id}"
REGION="${GCP_REGION:-asia-south1}"
SERVICE_NAME="auraleads-api"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"
VERSION=$(date +%Y%m%d%H%M%S)

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}   AuraLeads AI - Production Deployment    ${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: gcloud CLI is not installed${NC}"
    echo "Install from: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Authenticate if needed
echo -e "${YELLOW}Checking GCP authentication...${NC}"
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -n1 | grep -q "@"; then
    echo -e "${YELLOW}Please authenticate with Google Cloud${NC}"
    gcloud auth login
fi

# Set project
echo -e "${YELLOW}Setting project to: ${PROJECT_ID}${NC}"
gcloud config set project ${PROJECT_ID}

# Enable required APIs
echo -e "${YELLOW}Enabling required GCP APIs...${NC}"
gcloud services enable \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    secretmanager.googleapis.com \
    sqladmin.googleapis.com \
    redis.googleapis.com \
    storage.googleapis.com \
    aiplatform.googleapis.com \
    monitoring.googleapis.com \
    logging.googleapis.com \
    2>/dev/null || true

# Create secrets if they don't exist
echo -e "${YELLOW}Setting up secrets...${NC}"
create_secret_if_not_exists() {
    local secret_name=$1
    local default_value=$2
    if ! gcloud secrets describe ${secret_name} &>/dev/null; then
        echo "Creating secret: ${secret_name}"
        echo -n "${default_value}" | gcloud secrets create ${secret_name} --data-file=-
        gcloud secrets add-iam-policy-binding ${secret_name} \
            --member="serviceAccount:${PROJECT_ID}@appspot.gserviceaccount.com" \
            --role="roles/secretmanager.secretAccessor"
    fi
}

# Check and create required secrets
create_secret_if_not_exists "database-url" "postgresql+asyncpg://user:pass@/dbname?host=/cloudsql/${PROJECT_ID}:${REGION}:auraleads-db"
create_secret_if_not_exists "redis-url" "redis://default:password@redis-host:6379"
create_secret_if_not_exists "jwt-secret" "$(openssl rand -base64 32)"
create_secret_if_not_exists "app-secret-key" "$(openssl rand -base64 32)"

# Create Cloud Storage buckets
echo -e "${YELLOW}Setting up Cloud Storage buckets...${NC}"
gsutil mb -l ${REGION} gs://${PROJECT_ID}-profile-pictures 2>/dev/null || true
gsutil mb -l ${REGION} gs://${PROJECT_ID}-voice-recordings 2>/dev/null || true
gsutil mb -l ${REGION} gs://${PROJECT_ID}-ml-models 2>/dev/null || true

# Make profile pictures bucket public (for avatar URLs)
gsutil iam ch allUsers:objectViewer gs://${PROJECT_ID}-profile-pictures 2>/dev/null || true

# Build the container image
echo -e "${YELLOW}Building Docker image...${NC}"
echo -e "Image: ${IMAGE_NAME}:${VERSION}"
gcloud builds submit --tag ${IMAGE_NAME}:${VERSION} \
    --config=cloudbuild.yaml \
    --substitutions=_VERSION=${VERSION}

# Also tag as latest
docker tag ${IMAGE_NAME}:${VERSION} ${IMAGE_NAME}:latest 2>/dev/null || \
    gcloud container images add-tag ${IMAGE_NAME}:${VERSION} ${IMAGE_NAME}:latest --quiet

# Deploy to Cloud Run
echo -e "${YELLOW}Deploying to Cloud Run...${NC}"
gcloud run deploy ${SERVICE_NAME} \
    --image ${IMAGE_NAME}:${VERSION} \
    --region ${REGION} \
    --platform managed \
    --allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --min-instances 1 \
    --max-instances 10 \
    --timeout 300 \
    --concurrency 80 \
    --set-env-vars="APP_ENV=production" \
    --set-env-vars="GOOGLE_CLOUD_PROJECT_ID=${PROJECT_ID}" \
    --set-env-vars="GOOGLE_CLOUD_LOCATION=${REGION}" \
    --set-env-vars="GCS_BUCKET_NAME=${PROJECT_ID}-profile-pictures" \
    --set-secrets="DATABASE_URL=database-url:latest" \
    --set-secrets="REDIS_URL=redis-url:latest" \
    --set-secrets="JWT_SECRET_KEY=jwt-secret:latest" \
    --set-secrets="SECRET_KEY=app-secret-key:latest" \
    --add-cloudsql-instances=${PROJECT_ID}:${REGION}:auraleads-db

# Get the service URL
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format="value(status.url)")

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}   Deployment Complete!                    ${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "Service URL: ${BLUE}${SERVICE_URL}${NC}"
echo -e "API Docs:    ${BLUE}${SERVICE_URL}/docs${NC}"
echo -e "Health:      ${BLUE}${SERVICE_URL}/health${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Configure your domain with Cloud DNS"
echo "2. Set up SSL certificate with Cloud Load Balancer"
echo "3. Configure monitoring alerts in Cloud Monitoring"
echo "4. Set up Cloud SQL and Redis instances"
echo "5. Configure Twilio/Exotel webhooks to point to ${SERVICE_URL}/api/webhooks"
echo ""

# Health check
echo -e "${YELLOW}Running health check...${NC}"
sleep 10
HEALTH_STATUS=$(curl -s ${SERVICE_URL}/health | jq -r '.status' 2>/dev/null || echo "unknown")
if [ "$HEALTH_STATUS" = "healthy" ]; then
    echo -e "${GREEN}✅ Service is healthy!${NC}"
else
    echo -e "${YELLOW}⚠️  Service may still be starting up. Check logs with:${NC}"
    echo "gcloud run services logs read ${SERVICE_NAME} --region ${REGION}"
fi

echo ""
echo -e "${GREEN}Deployment successful! 🚀${NC}"
