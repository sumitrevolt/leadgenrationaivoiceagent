variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "environment" {
  type = string
}

variable "labels" {
  type    = map(string)
  default = {}
}

variable "cloud_run_service_name" {
  type = string
}

variable "notification_emails" {
  type    = list(string)
  default = []
}
