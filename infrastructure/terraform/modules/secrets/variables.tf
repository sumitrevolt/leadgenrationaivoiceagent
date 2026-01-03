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

# Database
variable "db_host" {
  type = string
}

variable "db_name" {
  type = string
}

variable "db_username" {
  type      = string
  sensitive = true
}

variable "db_password" {
  type      = string
  sensitive = true
}

# Redis
variable "redis_host" {
  type = string
}

variable "redis_port" {
  type = number
}

# API Keys
variable "openai_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "gemini_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "anthropic_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "elevenlabs_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "twilio_account_sid" {
  type      = string
  sensitive = true
  default   = ""
}

variable "twilio_auth_token" {
  type      = string
  sensitive = true
  default   = ""
}

variable "exotel_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "exotel_api_token" {
  type      = string
  sensitive = true
  default   = ""
}
