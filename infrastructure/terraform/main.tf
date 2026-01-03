/**
 * LeadGen AI Voice Agent - Production GCP Infrastructure
 * Terraform main configuration
 * 
 * Architecture:
 * - Cloud Run (auto-scaling app tier)
 * - Cloud SQL PostgreSQL (managed database)
 * - Memorystore Redis (caching/queues)
 * - Vertex AI (LLM serving)
 * - Secret Manager (credentials)
 * - Cloud Monitoring (observability)
 */

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
  }

  backend "gcs" {
    bucket = "gen-lang-client-0363264165-terraform-state"
    prefix = "production"
  }
}

# -----------------------------------------------------------------------------
# Provider Configuration
# -----------------------------------------------------------------------------

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# -----------------------------------------------------------------------------
# Enable Required APIs
# -----------------------------------------------------------------------------

resource "google_project_service" "required_apis" {
  for_each = toset([
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "redis.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com",
    "sqladmin.googleapis.com",
    "storage.googleapis.com",
    "vpcaccess.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# -----------------------------------------------------------------------------
# Local Variables
# -----------------------------------------------------------------------------

locals {
  app_name    = "leadgen-ai"
  environment = var.environment

  labels = {
    app         = local.app_name
    environment = local.environment
    managed_by  = "terraform"
  }
}

# -----------------------------------------------------------------------------
# Module Imports
# -----------------------------------------------------------------------------

module "networking" {
  source = "./modules/networking"

  project_id  = var.project_id
  region      = var.region
  environment = local.environment
  labels      = local.labels

  depends_on = [google_project_service.required_apis]
}

module "security" {
  source = "./modules/security"

  project_id  = var.project_id
  region      = var.region
  environment = local.environment
  labels      = local.labels
  network_id  = module.networking.network_id

  depends_on = [google_project_service.required_apis]
}

module "database" {
  source = "./modules/database"

  project_id         = var.project_id
  region             = var.region
  environment        = local.environment
  labels             = local.labels
  network_id         = module.networking.network_id
  private_ip_address = module.networking.private_services_address

  db_name     = var.db_name
  db_username = var.db_username
  db_password = var.db_password

  depends_on = [module.networking]
}

module "redis" {
  source = "./modules/redis"

  project_id  = var.project_id
  region      = var.region
  environment = local.environment
  labels      = local.labels
  network_id  = module.networking.network_id

  depends_on = [module.networking]
}

module "storage" {
  source = "./modules/storage"

  project_id  = var.project_id
  region      = var.region
  environment = local.environment
  labels      = local.labels

  cloud_run_sa_email = module.security.cloud_run_sa_email
  vertex_ai_sa_email = module.security.vertex_ai_sa_email

  depends_on = [module.security]
}

module "secrets" {
  source = "./modules/secrets"

  project_id  = var.project_id
  region      = var.region
  environment = local.environment
  labels      = local.labels

  # Database credentials
  db_host     = module.database.private_ip
  db_name     = var.db_name
  db_username = var.db_username
  db_password = var.db_password

  # Redis
  redis_host = module.redis.host
  redis_port = module.redis.port

  # API keys
  openai_api_key     = var.openai_api_key
  gemini_api_key     = var.gemini_api_key
  anthropic_api_key  = var.anthropic_api_key
  elevenlabs_api_key = var.elevenlabs_api_key
  twilio_account_sid = var.twilio_account_sid
  twilio_auth_token  = var.twilio_auth_token
  exotel_api_key     = var.exotel_api_key
  exotel_api_token   = var.exotel_api_token

  cloud_run_sa_email = module.security.cloud_run_sa_email

  depends_on = [module.database, module.redis]
}

module "artifact_registry" {
  source = "./modules/artifact_registry"

  project_id  = var.project_id
  region      = var.region
  environment = local.environment
  labels      = local.labels

  cloud_run_sa_email     = module.security.cloud_run_sa_email
  github_actions_sa_email = module.security.github_actions_sa_email

  depends_on = [module.security]
}

module "cloud_run" {
  source = "./modules/cloud_run"

  project_id  = var.project_id
  region      = var.region
  environment = local.environment
  labels      = local.labels

  # Service configuration
  service_name = "${local.app_name}-api"
  image_url    = "${var.region}-docker.pkg.dev/${var.project_id}/${module.artifact_registry.repository_id}/${local.app_name}:${var.app_version}"

  # Scaling
  min_instances = var.min_instances
  max_instances = var.max_instances

  # Resources
  cpu    = var.cloud_run_cpu
  memory = var.cloud_run_memory

  # Networking
  vpc_connector_id = module.networking.vpc_connector_id

  # Service account
  service_account_email = module.security.cloud_run_sa_email

  # Secrets
  secrets = module.secrets.secret_refs

  # Environment
  env_vars = {
    GOOGLE_CLOUD_PROJECT   = var.project_id
    VERTEX_AI_LOCATION     = var.region
    APP_ENV                = local.environment
    DEFAULT_LLM            = "vertex-gemini"
    DEFAULT_TTS            = "edge"
    DEFAULT_STT            = "deepgram"
    DEFAULT_TELEPHONY      = var.telephony_provider
    ENABLE_DND_CHECK       = "true"
    MAX_CONCURRENT_CALLS   = tostring(var.max_concurrent_calls)
    TIMEZONE               = "Asia/Kolkata"
    LOG_LEVEL              = var.log_level
  }

  depends_on = [
    module.networking,
    module.security,
    module.secrets,
    module.artifact_registry,
  ]
}

module "monitoring" {
  source = "./modules/monitoring"

  project_id  = var.project_id
  region      = var.region
  environment = local.environment
  labels      = local.labels

  cloud_run_service_name = module.cloud_run.service_name
  notification_emails    = var.alert_notification_emails

  depends_on = [module.cloud_run]
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "cloud_run_url" {
  description = "Cloud Run service URL"
  value       = module.cloud_run.service_url
}

output "cloud_sql_connection" {
  description = "Cloud SQL connection name"
  value       = module.database.connection_name
}

output "redis_host" {
  description = "Redis host"
  value       = module.redis.host
}

output "artifact_registry_url" {
  description = "Artifact Registry URL"
  value       = module.artifact_registry.repository_url
}

output "service_account_email" {
  description = "Cloud Run service account"
  value       = module.security.cloud_run_sa_email
}
