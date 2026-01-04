# =============================================================================
# LeadGen AI Voice Agent - GCP Production Deployment Script (PowerShell)
# =============================================================================
# This script sets up the complete GCP infrastructure for production
# Run: .\scripts\deploy_gcp_production.ps1
# =============================================================================

param(
    [string]$ProjectId = $env:GCP_PROJECT_ID,
    [string]$Region = "asia-south1",
    [string]$Zone = "asia-south1-a"
)

$ErrorActionPreference = "Stop"

# Configuration
if (-not $ProjectId) {
    $ProjectId = Read-Host "Enter your GCP Project ID"
}

$ServiceName = "leadgen-ai-api"
$DbInstanceName = "leadgen-db"
$RedisInstanceName = "leadgen-redis"
$VpcConnectorName = "leadgen-vpc-connector"
$ArtifactRepo = "leadgen-ai"

Write-Host "================================================" -ForegroundColor Blue
Write-Host "   LeadGen AI Voice Agent - GCP Deployment" -ForegroundColor Blue
Write-Host "================================================" -ForegroundColor Blue
Write-Host ""

# -----------------------------------------------------------------------------
# Step 1: Enable Required APIs
# -----------------------------------------------------------------------------
Write-Host "Step 1: Enabling required GCP APIs..." -ForegroundColor Yellow

$apis = @(
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "redis.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "vpcaccess.googleapis.com",
    "compute.googleapis.com",
    "servicenetworking.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com"
)

foreach ($api in $apis) {
    gcloud services enable $api --project=$ProjectId 2>$null
}
Write-Host "✓ APIs enabled" -ForegroundColor Green

# -----------------------------------------------------------------------------
# Step 2: Create VPC Network
# -----------------------------------------------------------------------------
Write-Host "Step 2: Setting up VPC network..." -ForegroundColor Yellow

$vpcExists = gcloud compute networks describe leadgen-vpc --project=$ProjectId 2>&1
if ($LASTEXITCODE -ne 0) {
    gcloud compute networks create leadgen-vpc --project=$ProjectId --subnet-mode=auto
    Write-Host "✓ VPC network created" -ForegroundColor Green
} else {
    Write-Host "✓ VPC network already exists" -ForegroundColor Green
}

# Create VPC connector
$connectorExists = gcloud compute networks vpc-access connectors describe $VpcConnectorName --region=$Region --project=$ProjectId 2>&1
if ($LASTEXITCODE -ne 0) {
    gcloud compute networks vpc-access connectors create $VpcConnectorName `
        --region=$Region `
        --network=leadgen-vpc `
        --range=10.8.0.0/28 `
        --project=$ProjectId
    Write-Host "✓ VPC connector created" -ForegroundColor Green
} else {
    Write-Host "✓ VPC connector already exists" -ForegroundColor Green
}

# -----------------------------------------------------------------------------
# Step 3: Create Cloud SQL PostgreSQL
# -----------------------------------------------------------------------------
Write-Host "Step 3: Setting up Cloud SQL PostgreSQL..." -ForegroundColor Yellow

$dbExists = gcloud sql instances describe $DbInstanceName --project=$ProjectId 2>&1
if ($LASTEXITCODE -ne 0) {
    gcloud sql instances create $DbInstanceName `
        --database-version=POSTGRES_15 `
        --tier=db-custom-2-7680 `
        --region=$Region `
        --network=leadgen-vpc `
        --no-assign-ip `
        --storage-type=SSD `
        --storage-size=50GB `
        --storage-auto-increase `
        --backup-start-time=02:00 `
        --maintenance-window-day=SUN `
        --maintenance-window-hour=03 `
        --project=$ProjectId
    
    Write-Host "✓ Cloud SQL instance created" -ForegroundColor Green
    
    # Create database
    gcloud sql databases create leadgen_ai --instance=$DbInstanceName --project=$ProjectId
    
    # Generate password
    $DbPassword = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})
    
    # Create user
    gcloud sql users create leadgen_user --instance=$DbInstanceName --password=$DbPassword --project=$ProjectId
    
    # Store in Secret Manager
    $DbPassword | gcloud secrets create db-password --data-file=- --replication-policy="automatic" --project=$ProjectId
    
    Write-Host "✓ Database and user created" -ForegroundColor Green
} else {
    Write-Host "✓ Cloud SQL instance already exists" -ForegroundColor Green
}

# Get DB private IP
$DbPrivateIp = gcloud sql instances describe $DbInstanceName --project=$ProjectId --format='value(ipAddresses[0].ipAddress)'

# -----------------------------------------------------------------------------
# Step 4: Create Memorystore Redis
# -----------------------------------------------------------------------------
Write-Host "Step 4: Setting up Memorystore Redis..." -ForegroundColor Yellow

$redisExists = gcloud redis instances describe $RedisInstanceName --region=$Region --project=$ProjectId 2>&1
if ($LASTEXITCODE -ne 0) {
    gcloud redis instances create $RedisInstanceName `
        --size=2 `
        --region=$Region `
        --zone=$Zone `
        --redis-version=redis_7_0 `
        --network=leadgen-vpc `
        --connect-mode=PRIVATE_SERVICE_ACCESS `
        --project=$ProjectId
    
    Write-Host "✓ Redis instance created" -ForegroundColor Green
} else {
    Write-Host "✓ Redis instance already exists" -ForegroundColor Green
}

# Get Redis host
$RedisHost = gcloud redis instances describe $RedisInstanceName --region=$Region --project=$ProjectId --format='value(host)'

# -----------------------------------------------------------------------------
# Step 5: Create Secrets in Secret Manager
# -----------------------------------------------------------------------------
Write-Host "Step 5: Setting up Secret Manager..." -ForegroundColor Yellow

function New-Secret {
    param([string]$SecretName, [string]$SecretValue)
    
    $exists = gcloud secrets describe $SecretName --project=$ProjectId 2>&1
    if ($LASTEXITCODE -ne 0) {
        $SecretValue | gcloud secrets create $SecretName --data-file=- --replication-policy="automatic" --project=$ProjectId
        Write-Host "✓ Created secret: $SecretName" -ForegroundColor Green
    } else {
        Write-Host "→ Secret $SecretName already exists" -ForegroundColor Yellow
    }
}

# Generate app secret
$AppSecret = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 64 | ForEach-Object {[char]$_})
New-Secret "app-secret-key" $AppSecret

# Generate JWT secret
$JwtSecret = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes((New-Guid).ToString()))
New-Secret "jwt-secret-key" $JwtSecret

# Placeholder secrets
New-Secret "gemini-api-key" "REPLACE_WITH_YOUR_GEMINI_API_KEY"
New-Secret "twilio-account-sid" "REPLACE_WITH_YOUR_TWILIO_SID"
New-Secret "twilio-auth-token" "REPLACE_WITH_YOUR_TWILIO_TOKEN"
New-Secret "twilio-phone-number" "REPLACE_WITH_YOUR_TWILIO_PHONE"
New-Secret "deepgram-api-key" "REPLACE_WITH_YOUR_DEEPGRAM_KEY"
New-Secret "stripe-secret-key" "REPLACE_WITH_YOUR_STRIPE_KEY"
New-Secret "razorpay-key-id" "REPLACE_WITH_YOUR_RAZORPAY_ID"
New-Secret "razorpay-key-secret" "REPLACE_WITH_YOUR_RAZORPAY_SECRET"

Write-Host "✓ Secrets configured" -ForegroundColor Green

# -----------------------------------------------------------------------------
# Step 6: Create Artifact Registry
# -----------------------------------------------------------------------------
Write-Host "Step 6: Setting up Artifact Registry..." -ForegroundColor Yellow

$repoExists = gcloud artifacts repositories describe $ArtifactRepo --location=$Region --project=$ProjectId 2>&1
if ($LASTEXITCODE -ne 0) {
    gcloud artifacts repositories create $ArtifactRepo --repository-format=docker --location=$Region --project=$ProjectId
    Write-Host "✓ Artifact Registry created" -ForegroundColor Green
} else {
    Write-Host "✓ Artifact Registry already exists" -ForegroundColor Green
}

# -----------------------------------------------------------------------------
# Step 7: Create Service Account
# -----------------------------------------------------------------------------
Write-Host "Step 7: Setting up service account..." -ForegroundColor Yellow

$SaName = "production-cloud-run-sa"
$SaEmail = "$SaName@$ProjectId.iam.gserviceaccount.com"

$saExists = gcloud iam service-accounts describe $SaEmail --project=$ProjectId 2>&1
if ($LASTEXITCODE -ne 0) {
    gcloud iam service-accounts create $SaName --display-name="Production Cloud Run Service Account" --project=$ProjectId
    Write-Host "✓ Service account created" -ForegroundColor Green
} else {
    Write-Host "✓ Service account already exists" -ForegroundColor Green
}

# Grant roles
$roles = @(
    "roles/secretmanager.secretAccessor",
    "roles/cloudsql.client",
    "roles/redis.viewer",
    "roles/aiplatform.user"
)

foreach ($role in $roles) {
    gcloud projects add-iam-policy-binding $ProjectId --member="serviceAccount:$SaEmail" --role=$role --quiet 2>$null
}
Write-Host "✓ Service account permissions configured" -ForegroundColor Green

# -----------------------------------------------------------------------------
# Step 8: Build and Push Docker Image
# -----------------------------------------------------------------------------
Write-Host "Step 8: Building and pushing Docker image..." -ForegroundColor Yellow

$ImageUrl = "$Region-docker.pkg.dev/$ProjectId/$ArtifactRepo/$ServiceName"

# Configure Docker
gcloud auth configure-docker "$Region-docker.pkg.dev" --quiet

# Build image
docker build -t "${ImageUrl}:latest" -f Dockerfile.production .

# Push image
docker push "${ImageUrl}:latest"

Write-Host "✓ Docker image pushed" -ForegroundColor Green

# -----------------------------------------------------------------------------
# Step 9: Deploy to Cloud Run
# -----------------------------------------------------------------------------
Write-Host "Step 9: Deploying to Cloud Run..." -ForegroundColor Yellow

$DatabaseUrl = "postgresql+asyncpg://leadgen_user:`$(gcloud secrets versions access latest --secret=db-password --project=$ProjectId)@${DbPrivateIp}:5432/leadgen_ai"

gcloud run deploy $ServiceName `
    --image="${ImageUrl}:latest" `
    --region=$Region `
    --platform=managed `
    --service-account=$SaEmail `
    --vpc-connector=$VpcConnectorName `
    --vpc-egress=private-ranges-only `
    --allow-unauthenticated `
    --min-instances=1 `
    --max-instances=100 `
    --cpu=2 `
    --memory=4Gi `
    --timeout=300s `
    --concurrency=80 `
    --port=8000 `
    --set-env-vars="APP_ENV=production" `
    --set-env-vars="DEBUG=false" `
    --set-env-vars="GOOGLE_CLOUD_PROJECT=$ProjectId" `
    --set-env-vars="REDIS_URL=redis://${RedisHost}:6379/0" `
    --set-secrets="SECRET_KEY=app-secret-key:latest" `
    --set-secrets="JWT_SECRET_KEY=jwt-secret-key:latest" `
    --set-secrets="GEMINI_API_KEY=gemini-api-key:latest" `
    --set-secrets="TWILIO_ACCOUNT_SID=twilio-account-sid:latest" `
    --set-secrets="TWILIO_AUTH_TOKEN=twilio-auth-token:latest" `
    --set-secrets="TWILIO_PHONE_NUMBER=twilio-phone-number:latest" `
    --set-secrets="DEEPGRAM_API_KEY=deepgram-api-key:latest" `
    --set-secrets="STRIPE_SECRET_KEY=stripe-secret-key:latest" `
    --set-secrets="RAZORPAY_KEY_ID=razorpay-key-id:latest" `
    --set-secrets="RAZORPAY_KEY_SECRET=razorpay-key-secret:latest" `
    --project=$ProjectId

Write-Host "✓ Cloud Run deployment complete" -ForegroundColor Green

# Get service URL
$ServiceUrl = gcloud run services describe $ServiceName --region=$Region --project=$ProjectId --format='value(status.url)'

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "================================================" -ForegroundColor Blue
Write-Host "   Deployment Complete!" -ForegroundColor Blue
Write-Host "================================================" -ForegroundColor Blue
Write-Host ""
Write-Host "Service URL: $ServiceUrl" -ForegroundColor Green
Write-Host "API Docs: $ServiceUrl/docs" -ForegroundColor Green
Write-Host "Health Check: $ServiceUrl/health" -ForegroundColor Green
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. Update secrets in Secret Manager with real API keys"
Write-Host "2. Configure Twilio webhook URL: $ServiceUrl/api/webhooks/twilio"
Write-Host "3. Set up custom domain (optional)"
Write-Host ""
Write-Host "Deployment successful!" -ForegroundColor Green
