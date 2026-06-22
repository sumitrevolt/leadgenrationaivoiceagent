/**
 * Monitoring Module
 * Alerts, dashboards, and observability
 */

# -----------------------------------------------------------------------------
# Notification Channel (Email)
# -----------------------------------------------------------------------------

resource "google_monitoring_notification_channel" "email" {
  for_each = toset(var.notification_emails)

  project      = var.project_id
  display_name = "Email - ${each.value}"
  type         = "email"

  labels = {
    email_address = each.value
  }
}

# -----------------------------------------------------------------------------
# Uptime Check
# -----------------------------------------------------------------------------

resource "google_monitoring_uptime_check_config" "main" {
  display_name = "${var.environment}-leadgen-api-uptime"
  project      = var.project_id
  timeout      = "10s"
  period       = "60s"

  http_check {
    path         = "/health"
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = replace(data.google_cloud_run_service.main.status[0].url, "https://", "")
    }
  }

  checker_type = "STATIC_IP_CHECKERS"
}

data "google_cloud_run_service" "main" {
  name     = var.cloud_run_service_name
  project  = var.project_id
  location = var.region
}

# -----------------------------------------------------------------------------
# Alert Policies
# -----------------------------------------------------------------------------

# High Error Rate Alert
resource "google_monitoring_alert_policy" "error_rate" {
  project      = var.project_id
  display_name = "${var.environment} - High Error Rate"
  combiner     = "OR"

  conditions {
    display_name = "Cloud Run Error Rate > 5%"

    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND metric.type = \"run.googleapis.com/request_count\" AND metric.labels.response_code_class = \"5xx\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.05

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [for ch in google_monitoring_notification_channel.email : ch.id]

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "Error rate exceeded 5% on LeadGen AI API. Check Cloud Run logs for details."
    mime_type = "text/markdown"
  }
}

# High Latency Alert
resource "google_monitoring_alert_policy" "latency" {
  project      = var.project_id
  display_name = "${var.environment} - High Latency"
  combiner     = "OR"

  conditions {
    display_name = "Cloud Run P99 Latency > 5s"

    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND metric.type = \"run.googleapis.com/request_latencies\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 5000  # 5 seconds

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_PERCENTILE_99"
        cross_series_reducer = "REDUCE_MEAN"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [for ch in google_monitoring_notification_channel.email : ch.id]

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "P99 latency exceeded 5 seconds. Voice calls may be affected."
    mime_type = "text/markdown"
  }
}

# Instance Scale Alert
resource "google_monitoring_alert_policy" "scaling" {
  project      = var.project_id
  display_name = "${var.environment} - High Instance Count"
  combiner     = "OR"

  conditions {
    display_name = "Cloud Run Instances > 80"

    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND metric.type = \"run.googleapis.com/container/instance_count\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 80

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_MAX"
        cross_series_reducer = "REDUCE_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [for ch in google_monitoring_notification_channel.email : ch.id]

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "Instance count nearing maximum. Consider increasing max instances or optimizing performance."
    mime_type = "text/markdown"
  }
}

# Database CPU Alert
resource "google_monitoring_alert_policy" "database_cpu" {
  project      = var.project_id
  display_name = "${var.environment} - Database High CPU"
  combiner     = "OR"

  conditions {
    display_name = "Cloud SQL CPU > 80%"

    condition_threshold {
      filter          = "resource.type = \"cloudsql_database\" AND metric.type = \"cloudsql.googleapis.com/database/cpu/utilization\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.8

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_MEAN"
        cross_series_reducer = "REDUCE_MEAN"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [for ch in google_monitoring_notification_channel.email : ch.id]

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "Database CPU utilization high. Consider scaling up or optimizing queries."
    mime_type = "text/markdown"
  }
}

# LLM Token Cost Alert
resource "google_monitoring_alert_policy" "llm_cost" {
  project      = var.project_id
  display_name = "${var.environment} - High LLM Token Usage"
  combiner     = "OR"

  conditions {
    display_name = "Custom Metric - LLM Tokens/Hour > Threshold"

    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND metric.type = \"custom.googleapis.com/llm/tokens_used\""
      duration        = "3600s"
      comparison      = "COMPARISON_GT"
      threshold_value = 1000000  # 1M tokens/hour

      aggregations {
        alignment_period     = "3600s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [for ch in google_monitoring_notification_channel.email : ch.id]

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "LLM token usage exceeding 1M tokens/hour. Review for cost optimization."
    mime_type = "text/markdown"
  }
}

# -----------------------------------------------------------------------------
# Custom Dashboard
# -----------------------------------------------------------------------------

resource "google_monitoring_dashboard" "main" {
  project        = var.project_id
  dashboard_json = jsonencode({
    displayName = "LeadGen AI Voice Agent - ${var.environment}"
    mosaicLayout = {
      columns = 12
      tiles = [
        {
          height = 4
          width  = 6
          widget = {
            title = "Request Count"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type = \"cloud_run_revision\" AND metric.type = \"run.googleapis.com/request_count\""
                  }
                }
                plotType = "LINE"
              }]
            }
          }
        },
        {
          xPos   = 6
          height = 4
          width  = 6
          widget = {
            title = "Request Latency (P50, P95, P99)"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type = \"cloud_run_revision\" AND metric.type = \"run.googleapis.com/request_latencies\""
                  }
                }
                plotType = "LINE"
              }]
            }
          }
        },
        {
          yPos   = 4
          height = 4
          width  = 6
          widget = {
            title = "Active Instances"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type = \"cloud_run_revision\" AND metric.type = \"run.googleapis.com/container/instance_count\""
                  }
                }
                plotType = "STACKED_AREA"
              }]
            }
          }
        },
        {
          xPos   = 6
          yPos   = 4
          height = 4
          width  = 6
          widget = {
            title = "Error Rate"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type = \"cloud_run_revision\" AND metric.type = \"run.googleapis.com/request_count\" AND metric.labels.response_code_class = \"5xx\""
                  }
                }
                plotType = "LINE"
              }]
            }
          }
        },
        {
          yPos   = 8
          height = 4
          width  = 6
          widget = {
            title = "Database CPU Utilization"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type = \"cloudsql_database\" AND metric.type = \"cloudsql.googleapis.com/database/cpu/utilization\""
                  }
                }
                plotType = "LINE"
              }]
            }
          }
        },
        {
          xPos   = 6
          yPos   = 8
          height = 4
          width  = 6
          widget = {
            title = "Redis Memory Usage"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type = \"redis_instance\" AND metric.type = \"redis.googleapis.com/stats/memory/usage_ratio\""
                  }
                }
                plotType = "LINE"
              }]
            }
          }
        }
      ]
    }
  })
}

# -----------------------------------------------------------------------------
# Log-based Metrics
# -----------------------------------------------------------------------------

resource "google_logging_metric" "voice_calls" {
  project     = var.project_id
  name        = "voice_calls_total"
  description = "Total voice calls initiated"
  filter      = "resource.type=\"cloud_run_revision\" AND jsonPayload.event=\"voice_call_initiated\""

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"

    labels {
      key         = "client_id"
      value_type  = "STRING"
      description = "Client tenant ID"
    }

    labels {
      key         = "industry"
      value_type  = "STRING"
      description = "Industry type"
    }
  }

  label_extractors = {
    "client_id" = "EXTRACT(jsonPayload.client_id)"
    "industry"  = "EXTRACT(jsonPayload.industry)"
  }
}

resource "google_logging_metric" "hot_leads" {
  project     = var.project_id
  name        = "hot_leads_detected"
  description = "Hot leads detected during calls"
  filter      = "resource.type=\"cloud_run_revision\" AND jsonPayload.event=\"hot_lead_detected\""

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_logging_metric" "llm_tokens" {
  project     = var.project_id
  name        = "llm_tokens_used"
  description = "LLM tokens consumed"
  filter      = "resource.type=\"cloud_run_revision\" AND jsonPayload.event=\"llm_response\""

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }

  value_extractor = "EXTRACT(jsonPayload.tokens_used)"
}
