# ============================================================================
# LeadGen AI Voice Agent - Deployment Instructions
# ============================================================================

## Prerequisites

1. GCP Project with billing enabled
2. gcloud CLI installed and authenticated
3. Terraform >= 1.5.0 installed
4. GitHub repository with secrets configured

## Step 1: Create Terraform State Bucket

```bash
# Set your project ID
export PROJECT_ID="your-gcp-project-id"
export REGION="asia-south1"

# Create state bucket
gsutil mb -p $PROJECT_ID -l $REGION gs://${PROJECT_ID}-terraform-state
gsutil versioning set on gs://${PROJECT_ID}-terraform-state
```

## Step 2: Initialize Terraform

```bash
cd infrastructure/terraform

# Update backend bucket name in main.tf
# Then initialize
terraform init -backend-config="bucket=${PROJECT_ID}-terraform-state"
```

## Step 3: Create terraform.tfvars

```hcl
# infrastructure/terraform/terraform.tfvars
project_id = "your-gcp-project-id"
region     = "asia-south1"
environment = "production"

db_username = "leadgen_admin"
# db_password set via TF_VAR_db_password

alert_notification_emails = [
  "your-email@example.com"
]
```

## Step 4: Set Sensitive Variables

```bash
# Set API keys as environment variables
export TF_VAR_db_password="your-secure-password"
export TF_VAR_openai_api_key="sk-..."
export TF_VAR_gemini_api_key="..."
export TF_VAR_twilio_account_sid="..."
export TF_VAR_twilio_auth_token="..."
export TF_VAR_exotel_api_key="..."
export TF_VAR_exotel_api_token="..."
```

## Step 5: Deploy Infrastructure

```bash
# Plan
terraform plan -var-file="environments/production.tfvars"

# Apply
terraform apply -var-file="environments/production.tfvars"
```

## Step 6: Configure GitHub Actions

Add these repository variables in GitHub Settings > Secrets and Variables:

**Variables:**
- `GCP_PROJECT_ID`: Your GCP project ID
- `WORKLOAD_IDENTITY_PROVIDER`: From Terraform output
- `GCP_SERVICE_ACCOUNT`: From Terraform output (github-actions SA email)

## Step 7: Initial Deployment

```bash
# Build and push initial image
gcloud builds submit --config=cloudbuild.yaml

# Or push to main branch to trigger GitHub Actions
git push origin main
```

## Step 8: Verify Deployment

```bash
# Get Cloud Run URL
gcloud run services describe leadgen-ai-api \
  --region asia-south1 \
  --format='value(status.url)'

# Health check
curl https://your-service-url/health

# Check logs
gcloud logging read "resource.type=cloud_run_revision" --limit 50
```

## Monitoring

- Cloud Monitoring Dashboard: https://console.cloud.google.com/monitoring
- Cloud Run Metrics: https://console.cloud.google.com/run
- Error Reporting: https://console.cloud.google.com/errors

## Rollback

```bash
# List revisions
gcloud run revisions list --service=leadgen-ai-api --region=asia-south1

# Rollback to previous revision
gcloud run services update-traffic leadgen-ai-api \
  --region=asia-south1 \
  --to-revisions=REVISION_NAME=100
```

## Cost Optimization

1. **Cloud Run**: Set min-instances=0 for staging
2. **Cloud SQL**: Use smaller tier for non-production
3. **Vertex AI**: Use Flash instead of Pro for most calls
4. **Batch Prediction**: 50% cheaper for non-real-time tasks

## Security Checklist

- [x] VPC with private subnets
- [x] Cloud SQL with private IP only
- [x] Secrets in Secret Manager
- [x] Workload Identity for CI/CD
- [x] IAM least privilege
- [x] Container scanning
- [ ] VPC Service Controls (requires organization)
- [ ] Cloud Armor WAF (for production traffic)
