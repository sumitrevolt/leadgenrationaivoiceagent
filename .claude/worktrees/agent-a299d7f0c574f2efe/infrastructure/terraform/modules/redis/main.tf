/**
 * Redis Module
 * Memorystore Redis for caching and Celery broker
 */

# -----------------------------------------------------------------------------
# Memorystore Redis Instance
# -----------------------------------------------------------------------------

resource "google_redis_instance" "main" {
  name           = "${var.environment}-leadgen-redis"
  project        = var.project_id
  region         = var.region
  tier           = var.environment == "production" ? "STANDARD_HA" : "BASIC"
  memory_size_gb = var.redis_memory_gb

  # Redis version
  redis_version = "REDIS_7_0"

  # Networking
  authorized_network = var.network_id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"

  # Persistence
  persistence_config {
    persistence_mode    = var.environment == "production" ? "RDB" : "DISABLED"
    rdb_snapshot_period = var.environment == "production" ? "ONE_HOUR" : null
  }

  # Maintenance
  maintenance_policy {
    weekly_maintenance_window {
      day = "SUNDAY"
      start_time {
        hours   = 3
        minutes = 0
        seconds = 0
        nanos   = 0
      }
    }
  }

  # Display name
  display_name = "LeadGen AI Redis - ${var.environment}"

  labels = var.labels
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------

output "host" {
  value = google_redis_instance.main.host
}

output "port" {
  value = google_redis_instance.main.port
}

output "instance_name" {
  value = google_redis_instance.main.name
}
