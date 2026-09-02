/**
 * Security Module
 * Service Accounts, IAM, Workload Identity
 */

# -----------------------------------------------------------------------------
# Service Accounts
# -----------------------------------------------------------------------------

# Cloud Run Service Account
resource "google_service_account" "cloud_run" {
  account_id   = "${var.environment}-cloud-run-sa"
  display_name = "Cloud Run AI Application"
  project      = var.project_id
  description  = "Service account for Cloud Run AI voice agent application"
}

# Vertex AI Service Account
resource "google_service_account" "vertex_ai" {
  account_id   = "${var.environment}-vertex-ai-sa"
  display_name = "Vertex AI Workload"
  project      = var.project_id
  description  = "Service account for Vertex AI training and prediction"
}

# GitHub Actions Service Account (for CI/CD)
resource "google_service_account" "github_actions" {
  account_id   = "${var.environment}-github-actions-sa"
  display_name = "GitHub Actions Deployment"
  project      = var.project_id
  description  = "Service account for GitHub Actions CI/CD deployments"
}

# Cloud Build Service Account
resource "google_service_account" "cloud_build" {
  account_id   = "${var.environment}-cloud-build-sa"
  display_name = "Cloud Build"
  project      = var.project_id
  description  = "Service account for Cloud Build"
}

# -----------------------------------------------------------------------------
# Cloud Run IAM Bindings
# -----------------------------------------------------------------------------

# Vertex AI User (for Gemini API calls)
resource "google_project_iam_member" "cloud_run_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# Secret Manager Secret Accessor
resource "google_project_iam_member" "cloud_run_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# Cloud SQL Client
resource "google_project_iam_member" "cloud_run_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# Logging Writer
resource "google_project_iam_member" "cloud_run_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# Monitoring Metric Writer
resource "google_project_iam_member" "cloud_run_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# Cloud Trace Agent
resource "google_project_iam_member" "cloud_run_trace_agent" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# Storage Object Viewer (for ML models)
resource "google_project_iam_member" "cloud_run_storage_viewer" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# -----------------------------------------------------------------------------
# Vertex AI IAM Bindings
# -----------------------------------------------------------------------------

# AI Platform Admin
resource "google_project_iam_member" "vertex_ai_admin" {
  project = var.project_id
  role    = "roles/aiplatform.admin"
  member  = "serviceAccount:${google_service_account.vertex_ai.email}"
}

# Storage Object Admin (for model artifacts)
resource "google_project_iam_member" "vertex_ai_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.vertex_ai.email}"
}

# BigQuery Data Editor (for training data)
resource "google_project_iam_member" "vertex_ai_bigquery" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.vertex_ai.email}"
}

# Service Account User (for running jobs)
resource "google_project_iam_member" "vertex_ai_sa_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.vertex_ai.email}"
}

# -----------------------------------------------------------------------------
# GitHub Actions IAM Bindings
# -----------------------------------------------------------------------------

# Cloud Run Admin
resource "google_project_iam_member" "github_actions_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

# Artifact Registry Writer
resource "google_project_iam_member" "github_actions_artifact_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

# Service Account User
resource "google_project_iam_member" "github_actions_sa_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

# Cloud Build Editor
resource "google_project_iam_member" "github_actions_build_editor" {
  project = var.project_id
  role    = "roles/cloudbuild.builds.editor"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

# -----------------------------------------------------------------------------
# Cloud Build IAM Bindings
# -----------------------------------------------------------------------------

resource "google_project_iam_member" "cloud_build_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.cloud_build.email}"
}

resource "google_project_iam_member" "cloud_build_artifact_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.cloud_build.email}"
}

resource "google_project_iam_member" "cloud_build_sa_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.cloud_build.email}"
}

resource "google_project_iam_member" "cloud_build_logs_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.cloud_build.email}"
}

# -----------------------------------------------------------------------------
# Workload Identity (for GitHub Actions OIDC)
# -----------------------------------------------------------------------------

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = "${var.environment}-github-pool"
  display_name              = "GitHub Actions Pool"
  description               = "Workload Identity Pool for GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub Provider"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  # Required condition to validate the token
  attribute_condition = "assertion.repository_owner == 'leadgen-ai'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Allow GitHub Actions to impersonate service account
resource "google_service_account_iam_member" "github_workload_identity" {
  service_account_id = google_service_account.github_actions.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/*"
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "cloud_run_sa_email" {
  value = google_service_account.cloud_run.email
}

output "vertex_ai_sa_email" {
  value = google_service_account.vertex_ai.email
}

output "github_actions_sa_email" {
  value = google_service_account.github_actions.email
}

output "cloud_build_sa_email" {
  value = google_service_account.cloud_build.email
}

output "workload_identity_pool_name" {
  value = google_iam_workload_identity_pool.github.name
}

output "workload_identity_provider" {
  value = google_iam_workload_identity_pool_provider.github.name
}
