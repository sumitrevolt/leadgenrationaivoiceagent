# ============================================================================
# LeadGen AI Voice Agent - Production Terraform Values
# Mumbai Region (asia-south1) for Indian market
# ============================================================================

# Project Configuration
project_id  = "gen-lang-client-0363264165"
region      = "asia-south1"
environment = "production"

# Database Configuration
db_name     = "leadgen_ai"
db_username = "leadgen_admin"
# db_password is set via environment variable TF_VAR_db_password
db_tier     = "db-custom-4-8192"  # 4 vCPU, 8GB RAM for production

# Cloud Run Scaling
app_version  = "latest"
min_instances = 2          # Always-on for voice calls
max_instances = 100        # Scale up for peak hours
cloud_run_cpu    = "2"
cloud_run_memory = "4Gi"
max_concurrent_calls = 50
log_level = "INFO"

# Telephony (Exotel for India)
telephony_provider = "exotel"

# Alert Notifications
alert_notification_emails = [
  "admin@yourdomain.com",
  "devops@yourdomain.com",
]

# API Keys - Set via environment variables:
# TF_VAR_openai_api_key
# TF_VAR_gemini_api_key
# TF_VAR_anthropic_api_key
# TF_VAR_elevenlabs_api_key
# TF_VAR_deepgram_api_key
# TF_VAR_sentry_dsn
# TF_VAR_twilio_account_sid
# TF_VAR_twilio_auth_token
# TF_VAR_exotel_api_key
# TF_VAR_exotel_api_token

# VPC Service Controls (optional - requires organization)
enable_vpc_sc = false
org_id        = ""
