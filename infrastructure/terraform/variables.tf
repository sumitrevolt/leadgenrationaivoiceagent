/**
 * Terraform Variables
 * Production configuration for LeadGen AI Voice Agent
 */

# -----------------------------------------------------------------------------
# Project Configuration
# -----------------------------------------------------------------------------

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "asia-south1"  # Mumbai - closest to Indian users
}

variable "environment" {
  description = "Environment (production, staging, development)"
  type        = string
  default     = "production"

  validation {
    condition     = contains(["production", "staging", "development"], var.environment)
    error_message = "Environment must be production, staging, or development."
  }
}

# -----------------------------------------------------------------------------
# Database Configuration
# -----------------------------------------------------------------------------

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "leadgen_ai"
}

variable "db_username" {
  description = "Database username"
  type        = string
  sensitive   = true
}

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}

variable "db_tier" {
  description = "Cloud SQL machine tier"
  type        = string
  default     = "db-custom-2-4096"  # 2 vCPU, 4GB RAM
}

# -----------------------------------------------------------------------------
# Cloud Run Configuration
# -----------------------------------------------------------------------------

variable "app_version" {
  description = "Application version/tag to deploy"
  type        = string
  default     = "latest"
}

variable "min_instances" {
  description = "Minimum Cloud Run instances"
  type        = number
  default     = 1
}

variable "max_instances" {
  description = "Maximum Cloud Run instances"
  type        = number
  default     = 100
}

variable "cloud_run_cpu" {
  description = "Cloud Run CPU allocation"
  type        = string
  default     = "2"
}

variable "cloud_run_memory" {
  description = "Cloud Run memory allocation"
  type        = string
  default     = "4Gi"
}

variable "max_concurrent_calls" {
  description = "Maximum concurrent voice calls"
  type        = number
  default     = 50
}

variable "log_level" {
  description = "Application log level"
  type        = string
  default     = "INFO"
}

# -----------------------------------------------------------------------------
# Telephony Configuration
# -----------------------------------------------------------------------------

variable "telephony_provider" {
  description = "Default telephony provider (twilio or exotel)"
  type        = string
  default     = "exotel"

  validation {
    condition     = contains(["twilio", "exotel"], var.telephony_provider)
    error_message = "Telephony provider must be twilio or exotel."
  }
}

# -----------------------------------------------------------------------------
# API Keys (Sensitive)
# -----------------------------------------------------------------------------

variable "openai_api_key" {
  description = "OpenAI API Key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "gemini_api_key" {
  description = "Google Gemini API Key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "anthropic_api_key" {
  description = "Anthropic API Key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "elevenlabs_api_key" {
  description = "ElevenLabs API Key for TTS"
  type        = string
  sensitive   = true
  default     = ""
}

variable "twilio_account_sid" {
  description = "Twilio Account SID"
  type        = string
  sensitive   = true
  default     = ""
}

variable "twilio_auth_token" {
  description = "Twilio Auth Token"
  type        = string
  sensitive   = true
  default     = ""
}

variable "exotel_api_key" {
  description = "Exotel API Key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "exotel_api_token" {
  description = "Exotel API Token"
  type        = string
  sensitive   = true
  default     = ""
}

variable "deepgram_api_key" {
  description = "Deepgram API Key for Speech-to-Text"
  type        = string
  sensitive   = true
  default     = ""
}

variable "sentry_dsn" {
  description = "Sentry DSN for error monitoring"
  type        = string
  sensitive   = true
  default     = ""
}

# -----------------------------------------------------------------------------
# Monitoring & Alerts
# -----------------------------------------------------------------------------

variable "alert_notification_emails" {
  description = "Email addresses for alert notifications"
  type        = list(string)
  default     = []
}

# -----------------------------------------------------------------------------
# Organization (for VPC-SC)
# -----------------------------------------------------------------------------

variable "org_id" {
  description = "GCP Organization ID (optional, for VPC Service Controls)"
  type        = string
  default     = ""
}

variable "enable_vpc_sc" {
  description = "Enable VPC Service Controls"
  type        = bool
  default     = false
}
