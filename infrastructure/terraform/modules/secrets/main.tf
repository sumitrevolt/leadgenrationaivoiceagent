/**
 * Secrets Module
 * Secret Manager for all sensitive configuration
 */

# -----------------------------------------------------------------------------
# Database Connection String
# -----------------------------------------------------------------------------

resource "google_secret_manager_secret" "database_url" {
  secret_id = "${var.environment}-database-url"
  project   = var.project_id

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  labels = var.labels
}

resource "google_secret_manager_secret_version" "database_url" {
  secret      = google_secret_manager_secret.database_url.id
  secret_data = "postgresql://${var.db_username}:${var.db_password}@${var.db_host}:5432/${var.db_name}"
}

# -----------------------------------------------------------------------------
# Redis URL
# -----------------------------------------------------------------------------

resource "google_secret_manager_secret" "redis_url" {
  secret_id = "${var.environment}-redis-url"
  project   = var.project_id

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  labels = var.labels
}

resource "google_secret_manager_secret_version" "redis_url" {
  secret      = google_secret_manager_secret.redis_url.id
  secret_data = "redis://${var.redis_host}:${var.redis_port}/0"
}

# -----------------------------------------------------------------------------
# LLM API Keys
# -----------------------------------------------------------------------------

resource "google_secret_manager_secret" "openai_api_key" {
  secret_id = "${var.environment}-openai-api-key"
  project   = var.project_id

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  labels = var.labels
}

resource "google_secret_manager_secret_version" "openai_api_key" {
  count       = var.openai_api_key != "" ? 1 : 0
  secret      = google_secret_manager_secret.openai_api_key.id
  secret_data = var.openai_api_key
}

resource "google_secret_manager_secret" "gemini_api_key" {
  secret_id = "${var.environment}-gemini-api-key"
  project   = var.project_id

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  labels = var.labels
}

resource "google_secret_manager_secret_version" "gemini_api_key" {
  count       = var.gemini_api_key != "" ? 1 : 0
  secret      = google_secret_manager_secret.gemini_api_key.id
  secret_data = var.gemini_api_key
}

resource "google_secret_manager_secret" "anthropic_api_key" {
  secret_id = "${var.environment}-anthropic-api-key"
  project   = var.project_id

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  labels = var.labels
}

resource "google_secret_manager_secret_version" "anthropic_api_key" {
  count       = var.anthropic_api_key != "" ? 1 : 0
  secret      = google_secret_manager_secret.anthropic_api_key.id
  secret_data = var.anthropic_api_key
}

# -----------------------------------------------------------------------------
# TTS API Keys
# -----------------------------------------------------------------------------

resource "google_secret_manager_secret" "elevenlabs_api_key" {
  secret_id = "${var.environment}-elevenlabs-api-key"
  project   = var.project_id

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  labels = var.labels
}

resource "google_secret_manager_secret_version" "elevenlabs_api_key" {
  count       = var.elevenlabs_api_key != "" ? 1 : 0
  secret      = google_secret_manager_secret.elevenlabs_api_key.id
  secret_data = var.elevenlabs_api_key
}

# -----------------------------------------------------------------------------
# Telephony Credentials
# -----------------------------------------------------------------------------

resource "google_secret_manager_secret" "twilio_account_sid" {
  secret_id = "${var.environment}-twilio-account-sid"
  project   = var.project_id

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  labels = var.labels
}

resource "google_secret_manager_secret_version" "twilio_account_sid" {
  count       = var.twilio_account_sid != "" ? 1 : 0
  secret      = google_secret_manager_secret.twilio_account_sid.id
  secret_data = var.twilio_account_sid
}

resource "google_secret_manager_secret" "twilio_auth_token" {
  secret_id = "${var.environment}-twilio-auth-token"
  project   = var.project_id

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  labels = var.labels
}

resource "google_secret_manager_secret_version" "twilio_auth_token" {
  count       = var.twilio_auth_token != "" ? 1 : 0
  secret      = google_secret_manager_secret.twilio_auth_token.id
  secret_data = var.twilio_auth_token
}

resource "google_secret_manager_secret" "exotel_api_key" {
  secret_id = "${var.environment}-exotel-api-key"
  project   = var.project_id

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  labels = var.labels
}

resource "google_secret_manager_secret_version" "exotel_api_key" {
  count       = var.exotel_api_key != "" ? 1 : 0
  secret      = google_secret_manager_secret.exotel_api_key.id
  secret_data = var.exotel_api_key
}

resource "google_secret_manager_secret" "exotel_api_token" {
  secret_id = "${var.environment}-exotel-api-token"
  project   = var.project_id

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  labels = var.labels
}

resource "google_secret_manager_secret_version" "exotel_api_token" {
  count       = var.exotel_api_token != "" ? 1 : 0
  secret      = google_secret_manager_secret.exotel_api_token.id
  secret_data = var.exotel_api_token
}

# -----------------------------------------------------------------------------
# Speech-to-Text API Keys
# -----------------------------------------------------------------------------

resource "google_secret_manager_secret" "deepgram_api_key" {
  secret_id = "${var.environment}-deepgram-api-key"
  project   = var.project_id

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  labels = var.labels
}

resource "google_secret_manager_secret_version" "deepgram_api_key" {
  count       = var.deepgram_api_key != "" ? 1 : 0
  secret      = google_secret_manager_secret.deepgram_api_key.id
  secret_data = var.deepgram_api_key
}

# -----------------------------------------------------------------------------
# Monitoring
# -----------------------------------------------------------------------------

resource "google_secret_manager_secret" "sentry_dsn" {
  secret_id = "${var.environment}-sentry-dsn"
  project   = var.project_id

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  labels = var.labels
}

resource "google_secret_manager_secret_version" "sentry_dsn" {
  count       = var.sentry_dsn != "" ? 1 : 0
  secret      = google_secret_manager_secret.sentry_dsn.id
  secret_data = var.sentry_dsn
}

# -----------------------------------------------------------------------------
# IAM Bindings for Cloud Run
# -----------------------------------------------------------------------------

resource "google_secret_manager_secret_iam_member" "cloud_run_access" {
  for_each = toset([
    google_secret_manager_secret.database_url.secret_id,
    google_secret_manager_secret.redis_url.secret_id,
    google_secret_manager_secret.openai_api_key.secret_id,
    google_secret_manager_secret.gemini_api_key.secret_id,
    google_secret_manager_secret.anthropic_api_key.secret_id,
    google_secret_manager_secret.elevenlabs_api_key.secret_id,
    google_secret_manager_secret.deepgram_api_key.secret_id,
    google_secret_manager_secret.sentry_dsn.secret_id,
    google_secret_manager_secret.twilio_account_sid.secret_id,
    google_secret_manager_secret.twilio_auth_token.secret_id,
    google_secret_manager_secret.exotel_api_key.secret_id,
    google_secret_manager_secret.exotel_api_token.secret_id,
  ])

  project   = var.project_id
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.cloud_run_sa_email}"
}

# -----------------------------------------------------------------------------
# Output Secret References for Cloud Run
# -----------------------------------------------------------------------------

output "secret_refs" {
  description = "Secret references for Cloud Run"
  value = {
    DATABASE_URL       = "${google_secret_manager_secret.database_url.secret_id}:latest"
    REDIS_URL          = "${google_secret_manager_secret.redis_url.secret_id}:latest"
    OPENAI_API_KEY     = "${google_secret_manager_secret.openai_api_key.secret_id}:latest"
    GEMINI_API_KEY     = "${google_secret_manager_secret.gemini_api_key.secret_id}:latest"
    ANTHROPIC_API_KEY  = "${google_secret_manager_secret.anthropic_api_key.secret_id}:latest"
    ELEVENLABS_API_KEY = "${google_secret_manager_secret.elevenlabs_api_key.secret_id}:latest"
    DEEPGRAM_API_KEY   = "${google_secret_manager_secret.deepgram_api_key.secret_id}:latest"
    SENTRY_DSN         = "${google_secret_manager_secret.sentry_dsn.secret_id}:latest"
    TWILIO_ACCOUNT_SID = "${google_secret_manager_secret.twilio_account_sid.secret_id}:latest"
    TWILIO_AUTH_TOKEN  = "${google_secret_manager_secret.twilio_auth_token.secret_id}:latest"
    EXOTEL_API_KEY     = "${google_secret_manager_secret.exotel_api_key.secret_id}:latest"
    EXOTEL_API_TOKEN   = "${google_secret_manager_secret.exotel_api_token.secret_id}:latest"
  }
}
