# ============================================================================
# AuraLeads Production Deployment Script for Windows
# ============================================================================
# Usage: .\deploy.ps1 -ProjectId "your-gcp-project" -Region "asia-south1"
# ============================================================================

param(
    [Parameter(Mandatory=$true)]
    [string]$ProjectId,
    
    [string]$Region = "asia-south1",
    [string]$ServiceName = "auraleads-api",
    [string]$FrontendBucket = "auraleads-frontend",
    [switch]$SkipBuild,
    [switch]$SkipFrontend,
    [switch]$SkipBackend
)

$ErrorActionPreference = "Stop"

# Colors for output
function Write-Success { param($Message) Write-Host $Message -ForegroundColor Green }
function Write-Info { param($Message) Write-Host $Message -ForegroundColor Cyan }
function Write-Warning { param($Message) Write-Host $Message -ForegroundColor Yellow }
function Write-Error { param($Message) Write-Host $Message -ForegroundColor Red }

Write-Host ""
Write-Host "============================================" -ForegroundColor Magenta
Write-Host "   AuraLeads Production Deployment" -ForegroundColor Magenta
Write-Host "============================================" -ForegroundColor Magenta
Write-Host ""

# Check prerequisites
Write-Info "Checking prerequisites..."

# Check gcloud
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    Write-Error "Error: gcloud CLI is not installed"
    Write-Host "Please install from: https://cloud.google.com/sdk/docs/install"
    exit 1
}

# Check docker
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Error: Docker is not installed"
    Write-Host "Please install Docker Desktop from: https://www.docker.com/products/docker-desktop"
    exit 1
}

# Check node (for frontend)
if (-not $SkipFrontend) {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        Write-Error "Error: Node.js is not installed"
        Write-Host "Please install from: https://nodejs.org/"
        exit 1
    }
}

Write-Success "All prerequisites found!"

# Set GCP project
Write-Info "Setting GCP project to: $ProjectId"
gcloud config set project $ProjectId

# Enable required APIs
Write-Info "Enabling required GCP APIs..."
$apis = @(
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "sqladmin.googleapis.com",
    "redis.googleapis.com",
    "aiplatform.googleapis.com",
    "storage.googleapis.com"
)

foreach ($api in $apis) {
    Write-Host "  Enabling $api..."
    gcloud services enable $api --quiet
}

Write-Success "APIs enabled!"

# Create Artifact Registry if not exists
$registryName = "auraleads"
Write-Info "Setting up Artifact Registry..."

$registryExists = gcloud artifacts repositories list --location=$Region --format="value(name)" 2>$null | Select-String -Pattern $registryName
if (-not $registryExists) {
    Write-Host "  Creating Artifact Registry repository..."
    gcloud artifacts repositories create $registryName `
        --repository-format=docker `
        --location=$Region `
        --description="AuraLeads Docker images"
}
Write-Success "Artifact Registry ready!"

# Configure Docker auth
Write-Info "Configuring Docker authentication..."
gcloud auth configure-docker "$Region-docker.pkg.dev" --quiet

# Build and push Docker image
if (-not $SkipBuild -and -not $SkipBackend) {
    Write-Info "Building Docker image..."
    
    $imageTag = Get-Date -Format "yyyyMMdd-HHmmss"
    $imageName = "$Region-docker.pkg.dev/$ProjectId/$registryName/$ServiceName"
    $fullImage = "${imageName}:${imageTag}"
    $latestImage = "${imageName}:latest"
    
    Write-Host "  Building: $fullImage"
    docker build -f Dockerfile.production -t $fullImage -t $latestImage .
    
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Docker build failed!"
        exit 1
    }
    
    Write-Info "Pushing Docker image..."
    docker push $fullImage
    docker push $latestImage
    
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Docker push failed!"
        exit 1
    }
    
    Write-Success "Docker image pushed: $fullImage"
}

# Deploy to Cloud Run
if (-not $SkipBackend) {
    Write-Info "Deploying to Cloud Run..."
    
    $imageName = "$Region-docker.pkg.dev/$ProjectId/$registryName/${ServiceName}:latest"
    
    gcloud run deploy $ServiceName `
        --image=$imageName `
        --region=$Region `
        --platform=managed `
        --allow-unauthenticated `
        --memory=2Gi `
        --cpu=2 `
        --min-instances=1 `
        --max-instances=10 `
        --timeout=300 `
        --concurrency=80 `
        --set-env-vars="GCP_PROJECT=$ProjectId,ENVIRONMENT=production,LOG_LEVEL=INFO,TIMEZONE=Asia/Kolkata" `
        --set-secrets="DATABASE_URL=DATABASE_URL:latest" `
        --set-secrets="REDIS_URL=REDIS_URL:latest" `
        --set-secrets="SECRET_KEY=SECRET_KEY:latest" `
        --set-secrets="JWT_SECRET_KEY=JWT_SECRET_KEY:latest" `
        --set-secrets="GEMINI_API_KEY=GEMINI_API_KEY:latest" `
        --set-secrets="DEEPGRAM_API_KEY=DEEPGRAM_API_KEY:latest" `
        --set-secrets="TWILIO_ACCOUNT_SID=TWILIO_ACCOUNT_SID:latest" `
        --set-secrets="TWILIO_AUTH_TOKEN=TWILIO_AUTH_TOKEN:latest" `
        --set-secrets="SENTRY_DSN=SENTRY_DSN:latest" `
        --quiet
    
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Cloud Run deployment failed!"
        exit 1
    }
    
    # Get service URL
    $serviceUrl = gcloud run services describe $ServiceName --region=$Region --format="value(status.url)"
    Write-Success "Backend deployed: $serviceUrl"
}

# Build and deploy frontend
if (-not $SkipFrontend) {
    Write-Info "Building frontend..."
    
    Push-Location frontend
    
    # Install dependencies
    Write-Host "  Installing dependencies..."
    npm ci
    
    # Build
    Write-Host "  Building production bundle..."
    $env:VITE_API_URL = "$serviceUrl/api"
    npm run build
    
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Frontend build failed!"
        Pop-Location
        exit 1
    }
    
    Pop-Location
    
    Write-Info "Deploying frontend to Cloud Storage..."
    
    # Create bucket if not exists
    $bucketUrl = "gs://${FrontendBucket}-${ProjectId}"
    $bucketExists = gsutil ls $bucketUrl 2>$null
    
    if (-not $bucketExists) {
        Write-Host "  Creating storage bucket..."
        gsutil mb -l $Region $bucketUrl
        gsutil web set -m index.html -e index.html $bucketUrl
        gsutil iam ch allUsers:objectViewer $bucketUrl
    }
    
    # Upload files
    Write-Host "  Uploading frontend files..."
    gsutil -m rsync -r -d frontend/dist $bucketUrl
    
    # Set cache headers
    gsutil -m setmeta -h "Cache-Control:public,max-age=31536000" "${bucketUrl}/assets/**"
    gsutil -m setmeta -h "Cache-Control:no-cache,no-store" "${bucketUrl}/index.html"
    
    $frontendUrl = "https://storage.googleapis.com/${FrontendBucket}-${ProjectId}/index.html"
    Write-Success "Frontend deployed: $frontendUrl"
}

# Run database migrations
if (-not $SkipBackend) {
    Write-Info "Running database migrations..."
    
    gcloud run jobs execute auraleads-migrate `
        --region=$Region `
        --wait `
        --quiet 2>$null
    
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Migration job not found or failed. You may need to run migrations manually."
    } else {
        Write-Success "Migrations complete!"
    }
}

# Summary
Write-Host ""
Write-Host "============================================" -ForegroundColor Magenta
Write-Host "   Deployment Complete!" -ForegroundColor Magenta
Write-Host "============================================" -ForegroundColor Magenta
Write-Host ""

if (-not $SkipBackend) {
    Write-Host "Backend API: $serviceUrl" -ForegroundColor Green
    Write-Host "API Docs:    $serviceUrl/docs" -ForegroundColor Green
    Write-Host "Health:      $serviceUrl/health" -ForegroundColor Green
}

if (-not $SkipFrontend) {
    Write-Host "Frontend:    $frontendUrl" -ForegroundColor Green
}

Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. Verify API health: curl $serviceUrl/health"
Write-Host "2. Create first admin user via API or database"
Write-Host "3. Configure custom domain in Cloud Run"
Write-Host "4. Set up Cloud Armor for DDoS protection"
Write-Host ""

# Create secrets reminder
Write-Host "Required Secrets (if not already set):" -ForegroundColor Yellow
Write-Host "  gcloud secrets create DATABASE_URL --data-file=-"
Write-Host "  gcloud secrets create REDIS_URL --data-file=-"
Write-Host "  gcloud secrets create SECRET_KEY --data-file=-"
Write-Host "  gcloud secrets create TWILIO_ACCOUNT_SID --data-file=-"
Write-Host "  gcloud secrets create TWILIO_AUTH_TOKEN --data-file=-"
Write-Host ""
