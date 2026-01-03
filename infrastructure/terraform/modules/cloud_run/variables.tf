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

variable "service_name" {
  type = string
}

variable "image_url" {
  type = string
}

variable "min_instances" {
  type    = number
  default = 1
}

variable "max_instances" {
  type    = number
  default = 100
}

variable "cpu" {
  type    = string
  default = "2"
}

variable "memory" {
  type    = string
  default = "4Gi"
}

variable "vpc_connector_id" {
  type = string
}

variable "service_account_email" {
  type = string
}

variable "secrets" {
  type    = map(string)
  default = {}
}

variable "env_vars" {
  type    = map(string)
  default = {}
}

variable "allow_public_access" {
  type    = bool
  default = true
}

variable "custom_domain" {
  type    = string
  default = ""
}
