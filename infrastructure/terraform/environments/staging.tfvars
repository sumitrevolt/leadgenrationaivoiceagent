# ============================================================================
# LeadGen AI Voice Agent - Staging Terraform Values
# ============================================================================

project_id  = "gen-lang-client-0363264165"
region      = "asia-south1"
environment = "staging"

# Database Configuration (smaller for staging)
db_name     = "leadgen_ai_staging"
db_username = "leadgen_staging"
db_password = ""
db_tier     = "db-custom-1-3840"  # 1 vCPU, 3.75GB RAM

# Cloud Run Scaling (reduced for staging)
app_version  = "latest"
min_instances = 0          # Scale to zero when idle
max_instances = 10
cloud_run_cpu    = "1"
cloud_run_memory = "2Gi"
max_concurrent_calls = 10
log_level = "DEBUG"

# Telephony
telephony_provider = "twilio"  # Twilio for testing

# Alerts
alert_notification_emails = [
  "staging-alerts@yourdomain.com",
]

# VPC Service Controls
enable_vpc_sc = false
