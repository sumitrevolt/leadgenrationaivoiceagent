#!/bin/bash
# =============================================================================
# LeadGen AI Voice Agent - GCP Production Deployment Script
# =============================================================================
# This script sets up the complete GCP infrastructure for production
# Run: bash scripts/deploy_gcp_production.sh
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-leadgen-ai-production}"
REGION="${GCP_REGION:-asia-south1}"
ZONE="${GCP_ZONE:-asia-south1-a}"
SERVICE_NAME="leadgen-ai-api"
DB_INSTANCE_NAME="leadgen-db"
REDIS_INSTANCE_NAME="leadgen-redis"
VPC_CONNECTOR_NAME="leadgen-vpc-connector"
ARTIFACT_REPO="leadgen-ai"

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   LeadGen AI Voice Agent - GCP Deployment${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# -----------------------------------------------------------------------------
# Step 1: Enable Required APIs
# -----------------------------------------------------------------------------
echo -e "${YELLOW}Step 1: Enabling required GCP APIs...${NC}"

gcloud services enable \
    run.googleapis.com \
    sqladmin.googleapis.com \
    redis.googleapis.com \
    secretmanager.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    vpcaccess.googleapis.com \
    compute.googleapis.com \
    servicenetworking.googleapis.com \
    monitoring.googleapis.com \
    logging.googleapis.com \
    --project=${PROJECT_ID}

echo -e "${GREEN}✓ APIs enabled${NC}"

# -----------------------------------------------------------------------------
# Step 2: Create VPC Network
# -----------------------------------------------------------------------------
echo -e "${YELLOW}Step 2: Setting up VPC network...${NC}"

# Check if VPC exists
if ! gcloud compute networks describe leadgen-vpc --project=${PROJECT_ID} &>/dev/null; then
    gcloud compute networks create leadgen-vpc \
        --project=${PROJECT_ID} \
        --subnet-mode=auto
    echo -e "${GREEN}✓ VPC network created${NC}"
else
    echo -e "${GREEN}✓ VPC network already exists${NC}"
fi

# Create VPC connector for Cloud Run
if ! gcloud compute networks vpc-access connectors describe ${VPC_CONNECTOR_NAME} --region=${REGION} --project=${PROJECT_ID} &>/dev/null; then
    gcloud compute networks vpc-access connectors create ${VPC_CONNECTOR_NAME} \
        --region=${REGION} \
        --network=leadgen-vpc \
        --range=10.8.0.0/28 \
        --project=${PROJECT_ID}
    echo -e "${GREEN}✓ VPC connector created${NC}"
else
    echo -e "${GREEN}✓ VPC connector already exists${NC}"
fi

# -----------------------------------------------------------------------------
# Step 3: Create Cloud SQL PostgreSQL
# -----------------------------------------------------------------------------
echo -e "${YELLOW}Step 3: Setting up Cloud SQL PostgreSQL...${NC}"

if ! gcloud sql instances describe ${DB_INSTANCE_NAME} --project=${PROJECT_ID} &>/dev/null; then
    gcloud sql instances create ${DB_INSTANCE_NAME} \
        --database-version=POSTGRES_15 \
        --tier=db-custom-2-7680 \
        --region=${REGION} \
        --network=leadgen-vpc \
        --no-assign-ip \
        --storage-type=SSD \
        --storage-size=50GB \
        --storage-auto-increase \
        --backup-start-time=02:00 \
        --maintenance-window-day=SUN \
        --maintenance-window-hour=03 \
        --project=${PROJECT_ID}
    
    echo -e "${GREEN}✓ Cloud SQL instance created${NC}"
    
    # Create database
    gcloud sql databases create leadgen_ai \
        --instance=${DB_INSTANCE_NAME} \
        --project=${PROJECT_ID}
    
    # Generate strong password
    DB_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | head -c 32)
    
    # Create database user
    gcloud sql users create leadgen_user \
        --instance=${DB_INSTANCE_NAME} \
        --password=${DB_PASSWORD} \
        --project=${PROJECT_ID}
    
    # Store password in Secret Manager
    echo -n ${DB_PASSWORD} | gcloud secrets create db-password \
        --data-file=- \
        --replication-policy="automatic" \
        --project=${PROJECT_ID}
    
    echo -e "${GREEN}✓ Database and user created${NC}"
else
    echo -e "${GREEN}✓ Cloud SQL instance already exists${NC}"
fi

# Get DB private IP
DB_PRIVATE_IP=$(gcloud sql instances describe ${DB_INSTANCE_NAME} \
    --project=${PROJECT_ID} \
    --format='value(ipAddresses[0].ipAddress)')

# -----------------------------------------------------------------------------
# Step 4: Create Memorystore Redis
# -----------------------------------------------------------------------------
echo -e "${YELLOW}Step 4: Setting up Memorystore Redis...${NC}"

if ! gcloud redis instances describe ${REDIS_INSTANCE_NAME} --region=${REGION} --project=${PROJECT_ID} &>/dev/null; then
    gcloud redis instances create ${REDIS_INSTANCE_NAME} \
        --size=2 \
        --region=${REGION} \
        --zone=${ZONE} \
        --redis-version=redis_7_0 \
        --network=leadgen-vpc \
        --connect-mode=PRIVATE_SERVICE_ACCESS \
        --project=${PROJECT_ID}
    
    echo -e "${GREEN}✓ Redis instance created${NC}"
else
    echo -e "${GREEN}✓ Redis instance already exists${NC}"
fi

# Get Redis host
REDIS_HOST=$(gcloud redis instances describe ${REDIS_INSTANCE_NAME} \
    --region=${REGION} \
    --project=${PROJECT_ID} \
    --format='value(host)')

# -----------------------------------------------------------------------------
# Step 5: Create Secrets in Secret Manager
# -----------------------------------------------------------------------------
echo -e "${YELLOW}Step 5: Setting up Secret Manager...${NC}"

create_secret() {
    local secret_name=$1
    local secret_value=$2
    
    if ! gcloud secrets describe ${secret_name} --project=${PROJECT_ID} &>/dev/null; then
        echo -n "${secret_value}" | gcloud secrets create ${secret_name} \
            --data-file=- \
            --replication-policy="automatic" \
            --project=${PROJECT_ID}
        echo -e "${GREEN}✓ Created secret: ${secret_name}${NC}"
    else
        echo -e "${YELLOW}→ Secret ${secret_name} already exists${NC}"
    fi
}

# Generate app secret key
APP_SECRET_KEY=$(openssl rand -base64 48 | tr -d '/+=' | head -c 64)
create_secret "app-secret-key" "${APP_SECRET_KEY}"

# Generate JWT secret
JWT_SECRET=$(openssl rand -base64 32)
create_secret "jwt-secret-key" "${JWT_SECRET}"

# Create placeholder secrets (user must update these)
create_secret "gemini-api-key" "REPLACE_WITH_YOUR_GEMINI_API_KEY"
create_secret "twilio-account-sid" "REPLACE_WITH_YOUR_TWILIO_SID"
create_secret "twilio-auth-token" "REPLACE_WITH_YOUR_TWILIO_TOKEN"
create_secret "twilio-phone-number" "REPLACE_WITH_YOUR_TWILIO_PHONE"
create_secret "deepgram-api-key" "REPLACE_WITH_YOUR_DEEPGRAM_KEY"
create_secret "stripe-secret-key" "REPLACE_WITH_YOUR_STRIPE_KEY"
create_secret "razorpay-key-id" "REPLACE_WITH_YOUR_RAZORPAY_ID"
create_secret "razorpay-key-secret" "REPLACE_WITH_YOUR_RAZORPAY_SECRET"

echo -e "${GREEN}✓ Secrets configured${NC}"

# -----------------------------------------------------------------------------
# Step 6: Create Artifact Registry
# -----------------------------------------------------------------------------
echo -e "${YELLOW}Step 6: Setting up Artifact Registry...${NC}"

if ! gcloud artifacts repositories describe ${ARTIFACT_REPO} --location=${REGION} --project=${PROJECT_ID} &>/dev/null; then
    gcloud artifacts repositories create ${ARTIFACT_REPO} \
        --repository-format=docker \
        --location=${REGION} \
        --project=${PROJECT_ID}
    echo -e "${GREEN}✓ Artifact Registry created${NC}"
else
    echo -e "${GREEN}✓ Artifact Registry already exists${NC}"
fi

# -----------------------------------------------------------------------------
# Step 7: Create Service Account
# -----------------------------------------------------------------------------
echo -e "${YELLOW}Step 7: Setting up service account...${NC}"

SA_NAME="production-cloud-run-sa"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe ${SA_EMAIL} --project=${PROJECT_ID} &>/dev/null; then
    gcloud iam service-accounts create ${SA_NAME} \
        --display-name="Production Cloud Run Service Account" \
        --project=${PROJECT_ID}
    echo -e "${GREEN}✓ Service account created${NC}"
else
    echo -e "${GREEN}✓ Service account already exists${NC}"
fi

# Grant required roles
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor" \
    --quiet

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/cloudsql.client" \
    --quiet

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/redis.viewer" \
    --quiet

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/aiplatform.user" \
    --quiet

echo -e "${GREEN}✓ Service account permissions configured${NC}"

# -----------------------------------------------------------------------------
# Step 8: Build and Push Docker Image
# -----------------------------------------------------------------------------
echo -e "${YELLOW}Step 8: Building and pushing Docker image...${NC}"

IMAGE_URL="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPO}/${SERVICE_NAME}"

# Configure Docker for Artifact Registry
gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet

# Build image
docker build -t ${IMAGE_URL}:latest -f Dockerfile.production .

# Push image
docker push ${IMAGE_URL}:latest

echo -e "${GREEN}✓ Docker image pushed${NC}"

# -----------------------------------------------------------------------------
# Step 9: Deploy to Cloud Run
# -----------------------------------------------------------------------------
echo -e "${YELLOW}Step 9: Deploying to Cloud Run...${NC}"

# Construct DATABASE_URL
DATABASE_URL="postgresql+asyncpg://leadgen_user:\$(gcloud secrets versions access latest --secret=db-password --project=${PROJECT_ID})@${DB_PRIVATE_IP}:5432/leadgen_ai"

gcloud run deploy ${SERVICE_NAME} \
    --image=${IMAGE_URL}:latest \
    --region=${REGION} \
    --platform=managed \
    --service-account=${SA_EMAIL} \
    --vpc-connector=${VPC_CONNECTOR_NAME} \
    --vpc-egress=private-ranges-only \
    --allow-unauthenticated \
    --min-instances=1 \
    --max-instances=100 \
    --cpu=2 \
    --memory=4Gi \
    --timeout=300s \
    --concurrency=80 \
    --port=8000 \
    --set-env-vars="APP_ENV=production" \
    --set-env-vars="DEBUG=false" \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" \
    --set-env-vars="REDIS_URL=redis://${REDIS_HOST}:6379/0" \
    --set-secrets="SECRET_KEY=app-secret-key:latest" \
    --set-secrets="JWT_SECRET_KEY=jwt-secret-key:latest" \
    --set-secrets="GEMINI_API_KEY=gemini-api-key:latest" \
    --set-secrets="TWILIO_ACCOUNT_SID=twilio-account-sid:latest" \
    --set-secrets="TWILIO_AUTH_TOKEN=twilio-auth-token:latest" \
    --set-secrets="TWILIO_PHONE_NUMBER=twilio-phone-number:latest" \
    --set-secrets="DEEPGRAM_API_KEY=deepgram-api-key:latest" \
    --set-secrets="STRIPE_SECRET_KEY=stripe-secret-key:latest" \
    --set-secrets="RAZORPAY_KEY_ID=razorpay-key-id:latest" \
    --set-secrets="RAZORPAY_KEY_SECRET=razorpay-key-secret:latest" \
    --set-env-vars="^@^DATABASE_URL=${DATABASE_URL}" \
    --project=${PROJECT_ID}

echo -e "${GREEN}✓ Cloud Run deployment complete${NC}"

# Get service URL
SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} \
    --region=${REGION} \
    --project=${PROJECT_ID} \
    --format='value(status.url)')

# -----------------------------------------------------------------------------
# Step 10: Run Database Migrations
# -----------------------------------------------------------------------------
echo -e "${YELLOW}Step 10: Running database migrations...${NC}"

# Run migrations via Cloud Run job
gcloud run jobs create migrate-db \
    --image=${IMAGE_URL}:latest \
    --region=${REGION} \
    --service-account=${SA_EMAIL} \
    --vpc-connector=${VPC_CONNECTOR_NAME} \
    --set-env-vars="^@^DATABASE_URL=${DATABASE_URL}" \
    --command="alembic" \
    --args="upgrade,head" \
    --max-retries=2 \
    --project=${PROJECT_ID} 2>/dev/null || true

gcloud run jobs execute migrate-db --region=${REGION} --project=${PROJECT_ID} --wait

echo -e "${GREEN}✓ Database migrations complete${NC}"

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   Deployment Complete!${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""
echo -e "${GREEN}Service URL: ${SERVICE_URL}${NC}"
echo -e "${GREEN}API Docs: ${SERVICE_URL}/docs${NC}"
echo -e "${GREEN}Health Check: ${SERVICE_URL}/health${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Update secrets in Secret Manager with real API keys:"
echo "   gcloud secrets versions add gemini-api-key --data-file=- <<< 'YOUR_KEY'"
echo "   gcloud secrets versions add twilio-account-sid --data-file=- <<< 'YOUR_SID'"
echo "   gcloud secrets versions add deepgram-api-key --data-file=- <<< 'YOUR_KEY'"
echo ""
echo "2. Configure Twilio webhook URL:"
echo "   ${SERVICE_URL}/api/webhooks/twilio"
echo ""
echo "3. Set up custom domain (optional):"
echo "   gcloud run domain-mappings create --service=${SERVICE_NAME} --domain=api.yourdomain.com"
echo ""
echo -e "${GREEN}Deployment successful!${NC}"
