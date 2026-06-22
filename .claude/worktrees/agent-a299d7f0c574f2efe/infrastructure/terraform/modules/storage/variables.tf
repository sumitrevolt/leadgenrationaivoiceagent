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

variable "cloud_run_sa_email" {
  type = string
}

variable "vertex_ai_sa_email" {
  type = string
}
