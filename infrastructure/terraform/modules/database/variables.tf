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

variable "network_id" {
  type = string
}

variable "private_ip_address" {
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

variable "db_tier" {
  type    = string
  default = "db-custom-2-4096"
}

variable "db_disk_size" {
  type    = number
  default = 50
}
