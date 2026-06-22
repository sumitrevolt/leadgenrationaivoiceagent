/**
 * Storage Module
 * Cloud Storage buckets for ML models, audio files, training data
 */

# -----------------------------------------------------------------------------
# ML Models Bucket
# -----------------------------------------------------------------------------

resource "google_storage_bucket" "ml_models" {
  name          = "${var.project_id}-${var.environment}-ml-models"
  project       = var.project_id
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 5
    }
    action {
      type = "Delete"
    }
  }

  labels = var.labels
}

# -----------------------------------------------------------------------------
# Training Data Bucket
# -----------------------------------------------------------------------------

resource "google_storage_bucket" "training_data" {
  name          = "${var.project_id}-${var.environment}-training-data"
  project       = var.project_id
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  # Retain training data for 90 days
  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }

  labels = var.labels
}

# -----------------------------------------------------------------------------
# Audio Files Bucket (call recordings)
# -----------------------------------------------------------------------------

resource "google_storage_bucket" "audio_files" {
  name          = "${var.project_id}-${var.environment}-audio-files"
  project       = var.project_id
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  # Move to nearline after 30 days
  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  # Move to coldline after 90 days
  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }

  # Delete after 365 days
  lifecycle_rule {
    condition {
      age = 365
    }
    action {
      type = "Delete"
    }
  }

  labels = var.labels
}

# -----------------------------------------------------------------------------
# Vertex AI Pipeline Artifacts
# -----------------------------------------------------------------------------

resource "google_storage_bucket" "vertex_pipelines" {
  name          = "${var.project_id}-${var.environment}-vertex-pipelines"
  project       = var.project_id
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  versioning {
    enabled = false
  }

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }

  labels = var.labels
}

# -----------------------------------------------------------------------------
# IAM Bindings - Cloud Run
# -----------------------------------------------------------------------------

resource "google_storage_bucket_iam_member" "cloud_run_ml_models" {
  bucket = google_storage_bucket.ml_models.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${var.cloud_run_sa_email}"
}

resource "google_storage_bucket_iam_member" "cloud_run_audio_files" {
  bucket = google_storage_bucket.audio_files.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.cloud_run_sa_email}"
}

# -----------------------------------------------------------------------------
# IAM Bindings - Vertex AI
# -----------------------------------------------------------------------------

resource "google_storage_bucket_iam_member" "vertex_ai_ml_models" {
  bucket = google_storage_bucket.ml_models.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.vertex_ai_sa_email}"
}

resource "google_storage_bucket_iam_member" "vertex_ai_training_data" {
  bucket = google_storage_bucket.training_data.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.vertex_ai_sa_email}"
}

resource "google_storage_bucket_iam_member" "vertex_ai_pipelines" {
  bucket = google_storage_bucket.vertex_pipelines.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.vertex_ai_sa_email}"
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "ml_models_bucket" {
  value = google_storage_bucket.ml_models.name
}

output "training_data_bucket" {
  value = google_storage_bucket.training_data.name
}

output "audio_files_bucket" {
  value = google_storage_bucket.audio_files.name
}

output "vertex_pipelines_bucket" {
  value = google_storage_bucket.vertex_pipelines.name
}
